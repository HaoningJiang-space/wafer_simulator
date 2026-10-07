"""Collective intent from explicit c10d operands and parameter records.

Never use autograd seq_id as a communication sequence, tensor-size ratios as a
communicator identity, or a returned opaque Work object as output completion.
"""
from collections import defaultdict
import json

from wafer_sim.workloads.chakra_effects import tensor_leaves
from wafer_sim.workloads.spatial import natural


KINDS = {
    "c10d::broadcast_": ("broadcast", 6),
    "c10d::allreduce_": ("allreduce", 5),
    "c10d::_allgather_base_": ("allgather", 5),
    "c10d::allgather_into_tensor_coalesced_": ("allgather", 3),
    "c10d::reduce_scatter_tensor_coalesced_": ("reduce_scatter", 5),
    "c10d::barrier": ("barrier", 4),
}
PARAM_KINDS = {"broadcast": "broadcast", "allreduce": "allreduce", "_allgather_base": "allgather",
               "allgather_into_tensor_coalesced": "allgather",
               "reduce_scatter_tensor_coalesced": "reduce_scatter", "barrier": "barrier"}
GPU_TYPES = {"allreduce": 0, "allgather": 2, "broadcast": 5, "reduce_scatter": 7}


def descriptor(ref):
    return {k: v for k, v in ref.items() if k != "path"}


def operands(name, schema, inputs, outputs):
    if name not in KINDS:
        raise ValueError("Unsupported c10d operator")
    kind, arity = KINDS[name]
    if len(inputs[0]) != arity or not schema.startswith(name + "(") or "c10d.Work" not in schema:
        raise ValueError("Collective ABI/schema mismatch")
    refs = tensor_leaves(inputs, "i")
    returned = tensor_leaves(outputs, "o")
    def arg(index):
        return [r for r in refs if r["path"] == f"i:{index}" or r["path"].startswith(f"i:{index}.")]
    if kind in {"allgather", "reduce_scatter"}:
        dest, src = arg(0), arg(1)
    elif kind in {"allreduce", "broadcast"}:
        src = dest = arg(0)
    else:
        # The barrier's device-selection tensor is not logical payload.
        src, dest = [], []
    if kind != "barrier" and (not src or len(src) != len(dest)):
        raise ValueError("Collective tensor pair arity mismatch")
    ratios = set()
    slots = []
    for source, destination in zip(src, dest):
        if source["source_device"] == "meta" or destination["source_device"] == "meta":
            raise ValueError("Meta collective has no target data")
        if (source["dtype"], source["element_bytes"]) != (destination["dtype"], destination["element_bytes"]):
            raise ValueError("Collective operand types differ")
        i, o = source["num_elements"], destination["num_elements"]
        if i <= 0 or o <= 0:
            raise ValueError("Empty collective needs an explicit zero-payload rule")
        big, small = (o, i) if kind == "allgather" else (i, o)
        if kind in {"allgather", "reduce_scatter"}:
            if big % small or big < small:
                raise ValueError("Collective input/output ratio inconsistent")
            ratios.add(big // small)
        elif i != o:
            raise ValueError("In-place collective changed extent")
        slots.append(dict(source=source, destination=destination, input_elements=i, output_elements=o,
                          element_bytes=source["element_bytes"], dtype=source["dtype"],
                          input_bytes=i*source["element_bytes"], output_bytes=o*source["element_bytes"]))
    if len(ratios) > 1:
        raise ValueError("Coalesced tensors require inconsistent group sizes")
    if returned and [descriptor(r) for r in returned] != [descriptor(r) for r in dest]:
        raise ValueError("Returned tensors differ from destination arguments")
    if name.endswith("coalesced_") and returned:
        raise ValueError("Expected only Work return for coalesced ABI")
    root = inputs[0][2] if kind == "broadcast" else None
    if root is not None:
        natural(root, "broadcast group-local root")
        if inputs[0][3] != 0 or len(slots) != 1:
            raise ValueError("Multi-device/root-tensor broadcast needs a separate rule")
    if name == "c10d::allreduce_" and inputs[2][3] != "None":
        raise ValueError("Sparse allreduce needs a separate rule")
    return dict(kind=kind, slots=slots, required_group_size=next(iter(ratios), None), root_local_rank=root,
                reduction=None, completion="destination writes after required communication/reduction",
                cpu_return_completes_output=False, source_work_handle_identity=None,
                logical_input_bytes=sum(s["input_bytes"] for s in slots),
                logical_output_bytes=sum(s["output_bytes"] for s in slots),
                source_duration_used=False)


def parameter_record(inputs):
    values, shapes, types = inputs
    if len(values) not in {9, 10} or len(shapes) != len(values) or len(types) != len(values):
        raise ValueError("Unknown record_param_comms ABI")
    start = len(values) - 9  # DATA variant adds InputTensors before the nine metadata arguments.
    seq, group, local_rank, kind, insplit, outsplit, first, stride, size = values[start:]
    for value in (seq, local_rank):
        natural(value, "collective sequence/local rank")
    natural(size, "communicator size", positive=True)
    if (not isinstance(group, list) or len(group) != 2 or not all(isinstance(s, str) for s in group)
            or (kind != "wait" and (local_rank >= size or not all(group))) or not isinstance(kind, str)
            or any(type(v) is not int for v in (first, stride))
            or not isinstance(insplit, list) or not isinstance(outsplit, list)):
        raise ValueError("Invalid collective identity record")
    for split in insplit + outsplit:
        natural(split, "split size")
    members = None
    if kind == "wait":
        # WorkNCCL::wait records a device-count placeholder (1), not the
        # communicator size. Its rank can therefore exceed that placeholder.
        # Retain it verbatim, but never use it to declare membership.
        pass
    elif first >= 0 and stride >= 0:
        if size > 1 and stride == 0:
            raise ValueError("Nonunique affine communicator")
        members = [first + i*stride for i in range(size)]
    elif (first, stride) != (-1, -1):
        raise ValueError("Partial communicator rank description")
    return dict(sequence=seq, group=group[0], description=group[1], local_rank=local_rank,
                kind=kind, group_size=None if kind == "wait" else size, recorded_size_field=size,
                members=members, input_splits=insplit, output_splits=outsplit,
                identity_source="record_param_comms input arguments, not autograd seq_id")


def init_groups(inputs):
    if len(inputs[0]) != 1 or inputs[2] != ["String"]:
        raise ValueError("Process-group metadata format changed")
    groups = json.loads(inputs[0][0])
    if not isinstance(groups, list):
        raise ValueError("Process-group table required")
    seen = set()
    for group in groups:
        name, size, ranks = group["pg_name"], group["group_size"], group["ranks"]
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("Invalid/duplicate process group")
        natural(size, "group size", positive=True)
        if not isinstance(ranks, list) or (ranks and len(ranks) != size) or len(set(ranks)) != len(ranks):
            raise ValueError("Invalid explicit group membership")
        for rank in ranks:
            natural(rank, "global rank")
        seen.add(name)
    return groups


def resolve_rank(rows, rank):
    """Join only explicit parent links; retain unidentifiable c10d calls."""
    by_id = {r["node_id"]: r for r in rows}
    params, groups, errors, calls = {}, [], [], []
    for row in rows:
        try:
            if row["name"] == "record_param_comms":
                params[row["node_id"]] = parameter_record(row["inputs"])
            elif "process_group:init" in row["name"]:
                groups.extend(init_groups(row["inputs"]))
        except ValueError as error:
            errors.append(dict(rank=rank, node_id=row["node_id"], reason=str(error)))
    def c10d_ancestor(node):
        seen = set()
        while node in by_id:
            if node in seen:
                raise ValueError("Collective source parent cycle")
            seen.add(node)
            row = by_id[node]
            if row["name"].startswith("c10d::"):
                return node
            parents = row["source_ctrl_deps"]
            node = parents[0] if len(parents) == 1 else 0
        return None
    children, devices = defaultdict(list), defaultdict(list)
    wait_index = defaultdict(list)
    for node, param in params.items():
        if param["kind"] == "wait" and param["group"]:
            wait_index[(param["group"], param["sequence"])].append(node)
        root = c10d_ancestor(by_id[node]["source_ctrl_deps"][0])
        if root is not None:
            children[root].append((node, param))
    for row in rows:
        if row["is_gpu_collective"]:
            root = c10d_ancestor(row["source_ctrl_deps"][0])
            if root is not None:
                devices[root].append(row)
    for row in rows:
        if not row["name"].startswith("c10d::") or not row["attrs"].get("is_cpu_op"):
            continue
        call = dict(rank=rank, node_id=row["node_id"], name=row["name"], byte_offset=row["byte_offset"],
                    source_ctrl_deps=row["source_ctrl_deps"], source_data_deps=row["source_data_deps"],
                    identity=None, intent=None, issues=[], gpu_nodes=[], source_wait_nodes=[],
                    complete_target_operation=False)
        try:
            intent = operands(row["name"], row["attrs"].get("op_schema", ""), row["inputs"], row["outputs"])
            call["intent"] = intent
            matches = [(node, p) for node, p in children[row["node_id"]] if PARAM_KINDS.get(p["kind"]) == intent["kind"]]
            if len(matches) == 1:
                node, identity = matches[0]
                call["identity"] = dict(identity, source_node=node)
            else:
                call["issues"].append("missing_or_ambiguous_group_sequence")
            gpu = devices[row["node_id"]]
            call["gpu_nodes"] = [g["node_id"] for g in gpu]
            call["source_comm_sizes"] = [g["attrs"].get("comm_size") for g in gpu]
            if intent["kind"] in {"allreduce", "reduce_scatter"} and gpu and all(
                    g["attrs"].get("comm_type") == GPU_TYPES[intent["kind"]] and
                    ("_AllReduce_Sum_" if intent["kind"] == "allreduce" else "_ReduceScatter_Sum_") in g["name"] for g in gpu):
                intent["reduction"] = "sum"
                intent["reduction_evidence"] = "attached source GPU kernel symbols"
            identity = call["identity"]
            if identity is not None:
                call["source_wait_nodes"] = wait_index[(identity["group"], identity["sequence"])]
                if intent["required_group_size"] not in {None, identity["group_size"]}:
                    call["issues"].append("operand_ratio_disagrees_with_group_size")
        except (ValueError, TypeError, KeyError) as error:
            call["issues"].append(str(error))
        calls.append(call)
    return dict(rank=rank, groups=groups, parameters=[dict(node_id=node, **p) for node, p in params.items()],
                calls=calls, errors=errors,
                gpu_collectives=[dict(node_id=r["node_id"], owner=c10d_ancestor(r["source_ctrl_deps"][0]))
                                 for r in rows if r["is_gpu_collective"]])


def match_collectives(rank_reports):
    """Cross-rank matching requires explicit group + sequence, never list order."""
    groups, buckets = {}, defaultdict(list)
    ranks = {r["rank"] for r in rank_reports}
    if len(ranks) != len(rank_reports):
        raise ValueError("Duplicate rank reports")
    def declare(name, size, members, description, evidence):
        entry = groups.setdefault(name, dict(group=name, size=size, members=None, description=description,
                                             evidence=[], issues=[]))
        if (entry["size"], entry["description"]) != (size, description):
            entry["issues"].append("group_metadata_conflict")
        if members:
            if entry["members"] is not None and entry["members"] != members:
                entry["issues"].append("group_member_order_conflict")
            entry["members"] = members
        entry["evidence"].append(evidence)
    for report in rank_reports:
        rank = report["rank"]
        for group in report["groups"]:
            declare(group["pg_name"], group["group_size"], group["ranks"], group["pg_desc"], dict(rank=rank, kind="init_table"))
        for param in report["parameters"]:
            if param["kind"] == "wait":
                continue
            declare(param["group"], param["group_size"], param["members"], param["description"],
                    dict(rank=rank, node_id=param["node_id"], kind="parameter_record"))
            if param["members"] is not None and param["members"][param["local_rank"]] != rank:
                groups[param["group"]]["issues"].append("local_rank_does_not_name_capture_rank")
        for call in report["calls"]:
            if call["identity"] is not None:
                key = call["identity"]["group"], call["identity"]["sequence"]
                buckets[key].append(call)
    matches = []
    for (group, sequence), calls in sorted(buckets.items()):
        declaration = groups[group]
        members = declaration["members"]
        issues = list(declaration["issues"])
        participants = {c["rank"] for c in calls}
        if members is None or not set(members) <= ranks or participants != set(members) or len(calls) != len(participants):
            issues.append("incomplete_or_duplicate_participants")
        signatures = []
        for c in calls:
            issues.extend(c["issues"])
            intent = c["intent"]
            if intent is None:
                issues.append("unresolved_operands"); continue
            signatures.append((intent["kind"], intent["root_local_rank"], tuple(
                (s["input_elements"], s["output_elements"], s["element_bytes"], s["dtype"]) for s in intent["slots"])))
        if len(set(signatures)) != 1:
            issues.append("collective_kind_or_operand_mismatch")
        reductions = {c["intent"]["reduction"] for c in calls if c["intent"]}
        kind = signatures[0][0] if signatures else None
        participant_match = not issues
        if kind in {"allreduce", "reduce_scatter"} and reductions != {"sum"}:
            issues.append("reduction_operator_unresolved")
        matched = dict(group=group, sequence=sequence, members=members, kind=kind,
            calls=[dict(rank=c["rank"], node_id=c["node_id"]) for c in sorted(calls, key=lambda c:c["rank"])],
            issues=sorted(set(issues)), participant_and_volume_match=participant_match,
            logical_semantics_supported=not issues,
            target_data_versions_bound=False, target_execution_complete=False)
        matches.append(matched)
    return dict(groups=list(groups.values()), collectives=matches, complete_target_workload=False)
