"""Full-source collective extraction and independent raw/normalized readback."""
from collections import Counter
import gzip
from itertools import zip_longest
import json

from wafer_sim.workloads.chakra import nodes, read_metadata, decode_io, attribute_values
from wafer_sim.workloads.chakra_collectives import resolve_rank


def extract(path, schema, output, rank):
    selected, counts = [], Counter()
    with path.open("rb") as stream, gzip.open(output, "wt", compresslevel=1) as ledger:
        read_metadata(stream, schema)
        for offset, node in nodes(stream, schema):
            counts["source_nodes"] += 1
            counts["source_ctrl_entries"] += len(node.ctrl_deps)
            counts["source_data_entries"] += len(node.data_deps)
            gpu = node.type == schema.COMM_COLL_NODE
            relevant = (gpu or node.name.startswith(("c10d::", "nccl:")) or node.name == "record_param_comms"
                        or "process_group:init" in node.name)
            if not relevant:
                continue
            row = dict(rank=rank, node_id=node.id, byte_offset=offset, name=node.name, type=node.type,
                       source_ctrl_deps=list(node.ctrl_deps), source_data_deps=list(node.data_deps),
                       attrs=attribute_values(node), inputs=decode_io(node.inputs), outputs=decode_io(node.outputs),
                       is_gpu_collective=gpu)
            selected.append(row)
            counts["selected_records"] += 1
            counts["gpu_collective_records"] += gpu
            ledger.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        size = stream.tell()
    report = resolve_rank(selected, rank)
    report.update(counts=dict(counts), input_bytes=size, full_source_read=True)
    return report


def validate(path, schema, ledger_path, report):
    """Reread every raw node; independently check operand paths and byte counts."""
    counts = Counter()
    saved = {}
    with path.open("rb") as stream, gzip.open(ledger_path, "rt") as ledger:
        read_metadata(stream, schema)
        for offset, node in nodes(stream, schema):
            counts["source_nodes"] += 1
            counts["source_ctrl_entries"] += len(node.ctrl_deps)
            counts["source_data_entries"] += len(node.data_deps)
            if not (node.name.startswith("c10d::") or node.name.startswith("nccl:") or
                    node.name == "record_param_comms" or "process_group:init" in node.name or node.type == schema.COMM_COLL_NODE):
                continue
            line = next(ledger, None)
            if line is None:
                raise ValueError("Missing collective source record")
            row = json.loads(line)
            wanted = dict(rank=report["rank"], node_id=node.id, byte_offset=offset, name=node.name, type=node.type,
                source_ctrl_deps=list(node.ctrl_deps), source_data_deps=list(node.data_deps),
                attrs=attribute_values(node), inputs=list(decode_io(node.inputs)), outputs=list(decode_io(node.outputs)),
                is_gpu_collective=node.type == schema.COMM_COLL_NODE)
            if row != wanted or node.id in saved:
                raise ValueError("Collective source identity/IO/dependencies changed")
            saved[node.id] = row
            counts["selected_records"] += 1
            counts["gpu_collective_records"] += node.type == schema.COMM_COLL_NODE
        if next(ledger, None) is not None or stream.tell() != report["input_bytes"] or dict(counts) != report["counts"]:
            raise ValueError("Incomplete source readback")
    expected_cpu = {n for n, r in saved.items() if r["name"].startswith("c10d::") and r["attrs"].get("is_cpu_op")}
    if len(report["calls"]) != len(expected_cpu) or {c["node_id"] for c in report["calls"]} != expected_cpu:
        raise ValueError("A CPU collective was silently lost")
    def raw_tensor(row, path):
        side, indices = path.split(":")
        values, shapes, _ = row["inputs" if side == "i" else "outputs"]
        for index in map(int, indices.split(".")):
            values, shapes = values[index], shapes[index]
        return values, shapes
    for call in report["calls"]:
        row = saved[call["node_id"]]
        if call["source_data_deps"] != row["source_data_deps"] or call["source_ctrl_deps"] != row["source_ctrl_deps"]:
            raise ValueError("Normalized collective changed original dependencies")
        intent = call["intent"]
        if intent is None:
            if not call["issues"]:
                raise ValueError("Unexplained unsupported collective")
            continue
        totals = Counter()
        for slot in intent["slots"]:
            for side, role in (("source", "input"), ("destination", "output")):
                ref = slot[side]
                value, shape = raw_tensor(row, ref["path"])
                if value != [ref[k] for k in ("tensor_id", "storage_id", "source_offset", "num_elements", "element_bytes", "source_device")] or shape != ref["shape"]:
                    raise ValueError("Tensor role no longer refers to the original operand")
                if slot[role + "_bytes"] != value[3]*value[4] or slot[role + "_elements"] != value[3]:
                    raise ValueError("Wrong logical collective volume")
                totals[role] += value[3]*value[4]
            # Destination is an INPUT argument for these c10d APIs.
            if not slot["destination"]["path"].startswith("i:0"):
                raise ValueError("Collective destination moved to opaque Work output")
            if intent["kind"] in {"allgather", "reduce_scatter"} and not slot["source"]["path"].startswith("i:1"):
                raise ValueError("Collective source/destination roles reversed")
        if (intent["logical_input_bytes"], intent["logical_output_bytes"]) != (totals["input"], totals["output"]):
            raise ValueError("Collective aggregate volume differs")
        if intent["cpu_return_completes_output"] or intent["source_duration_used"]:
            raise ValueError("Source return/duration became data completion")
        identity = call["identity"]
        if identity:
            raw = saved[identity["source_node"]]["inputs"][0][-9:]
            if (identity["sequence"], identity["group"], identity["local_rank"], identity["group_size"]) != (raw[0], raw[1][0], raw[2], raw[8]):
                raise ValueError("Communication identity changed")
            for node in call["source_wait_nodes"]:
                wait = saved[node]["inputs"][0][-9:]
                if wait[3] != "wait" or (wait[0], wait[1][0]) != (raw[0], raw[1][0]):
                    raise ValueError("Wait attached to another collective")
        counts["cpu_collectives_with_operand_roles"] += 1
        counts["cpu_collectives_with_explicit_identity"] += identity is not None
        counts["cpu_collectives_with_source_wait"] += bool(call["source_wait_nodes"])
        counts["gpu_comm_size_differs_from_logical_input"] += sum(
            size != intent["logical_input_bytes"] for size in call.get("source_comm_sizes", []))
    return dict(rank=report["rank"], counts=dict(counts), passed=True,
                every_source_node_read=True, all_cpu_collectives_accounted_for=True)
