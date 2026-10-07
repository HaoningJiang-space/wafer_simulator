"""Full effect-ledger to call-region serialization; no execution filtering."""
from collections import Counter
import gzip
import json

from wafer_sim.io import digest, write_json
from wafer_sim.workloads.call_regions import Call, partition_calls


MATRIX_FIELDS = ("node_id", "operator", "byte_offset", "work_amount", "work_unit", "extra_scalar_adds",
                 "input_logical_bytes", "output_logical_bytes", "source_profiler_step", "direct_gpu_children")


def matrix_index(path):
    ranks = {}
    with path.open() as stream:
        for line in stream:
            row = json.loads(line)
            per_rank = ranks.setdefault(row["rank"], {})
            if row["node_id"] in per_rank or row["source_time_used"] or row["work_unit"] != "mac":
                raise ValueError("Invalid or duplicate accepted matrix record")
            per_rank[row["node_id"]] = {key: row[key] for key in MATRIX_FIELDS}
    return ranks


def write_partition(source, output, rank, matrix_records):
    calls, positions = {}, {}
    with gzip.open(source, "rt") as stream:
        for line in stream:
            row = json.loads(line)
            node = row["node_id"]
            if row["rank"] != rank or node in calls:
                raise ValueError("Duplicate source identity or mixed ranks")
            calls[node] = Call.from_row(row, matrix_records)
            positions[node] = row["byte_offset"]
            if node in matrix_records and any(matrix_records[node][key] != row[value]
                                              for key, value in (("operator", "name"), ("byte_offset", "byte_offset"))):
                raise ValueError("Matrix work and source call differ")
    if not matrix_records.keys() <= calls.keys():
        raise ValueError("Accepted matrix work missing from source")
    partition = partition_calls(calls)
    sizes = Counter(partition.owners.values())
    paths = {kind: output / f"rank-{rank:02}-{kind}.jsonl.gz" for kind in ("owners", "regions", "edges")}
    def emit(stream, row):
        stream.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
    with gzip.open(paths["owners"], "wt", compresslevel=1) as mapping, \
            gzip.open(paths["regions"], "wt", compresslevel=1) as regions, \
            gzip.open(paths["edges"], "wt", compresslevel=1) as edges:
        for node, call in calls.items():
            owner = partition.owners[node]
            emit(mapping, dict(rank=rank, node_id=node, byte_offset=positions[node], owner=owner))
            if node == owner:
                rule = partition.rules[node]
                emit(regions, dict(rank=rank, owner=owner, name=call.name, source_category=call.category,
                    members=sizes[owner], rule=rule, refinement_reason=partition.rejected.get(owner),
                    matrix_work=matrix_records[node] if rule == "matrix_with_device_implementation" else None,
                    complete_target_operation=False, source_duration_used=False, source_order_is_target_order=False,
                    access_ports="Original source nodes retain all tensor and dependency identities"))
            for kind, deps in (("ctrl", (call.parent,)), ("data", call.dependencies)):
                for index, dep in enumerate(deps):
                    predecessor_owner = None if kind == "ctrl" and dep == 0 else partition.owners[dep]
                    emit(edges, dict(rank=rank, node_id=node, kind=kind, index=index, predecessor=dep,
                                    owner=owner, predecessor_owner=predecessor_owner, internal=owner == predecessor_owner))
    report = dict(rank=rank, nodes=len(calls), regions=len(sizes),
        proposed_multi_record_regions=partition.proposed_regions,
        refined_regions=len(partition.rejected),
        rules=dict(sorted(Counter(rule or "unresolved" for node, rule in partition.rules.items()
                                  if partition.owners[node] == node).items())),
        source_sha256=digest(source), artifacts_sha256={p.name: digest(p) for p in paths.values()},
        all_source_nodes_owned_once=True, complete_target_workload=False,
        simulated_application_time=None)
    write_json(output / f"rank-{rank:02}.json", report)
    return report
