"""Independent readback of call ownership and every original dependency port."""
from collections import Counter, deque
import gzip
from itertools import zip_longest
import json


def json_rows(path):
    with gzip.open(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


def check_acyclic(predecessors):
    """Kahn readback, independent of the frontend's quotient/SCC construction."""
    successors = {node: [] for node in predecessors}
    pending = {}
    for node, deps in predecessors.items():
        pending[node] = len(deps)
        for dep in deps:
            if dep not in successors:
                raise ValueError("Dependency endpoint missing")
            successors[dep].append(node)
    ready = deque(node for node, count in pending.items() if count == 0)
    seen = 0
    while ready:
        node = ready.popleft(); seen += 1
        for successor in successors[node]:
            pending[successor] -= 1
            if pending[successor] == 0:
                ready.append(successor)
    if seen != len(pending):
        raise ValueError("Readback graph contains a cycle")


def _signature(ref):
    return tuple(ref[k] for k in ("tensor_id", "storage_id", "source_offset", "num_elements",
                                  "element_bytes", "source_device")) + (tuple(ref["shape"]), ref["dtype"])


def validate_partition(source_path, mapping_path, region_path, edge_path, rank, matrix_records):
    nodes, ownership, group_sizes, counts = {}, {}, Counter(), Counter()
    expected_edges = []
    for source, mapped in zip_longest(json_rows(source_path), json_rows(mapping_path)):
        if source is None or mapped is None:
            raise ValueError("Missing or extra source ownership row")
        node = source["node_id"]
        if (source["rank"] != rank or mapped["rank"] != rank or mapped["node_id"] != node
                or mapped["byte_offset"] != source["byte_offset"] or node in nodes
                or len(source["source_ctrl_deps"]) != 1):
            raise ValueError("Source identity mismatch")
        effect = source["effects"]
        refs = effect.get("inputs", []) + effect.get("outputs", [])
        nodes[node] = dict(parent=source["source_ctrl_deps"][0], deps=source["source_data_deps"],
            category=effect["category"], name=source["name"], domain=source["source_domain"],
            storages={(r["storage_id"], r["source_device"]) for r in refs},
            outputs=tuple(_signature(r) for r in effect.get("outputs", [])),
            has_meta=source.get("contains_meta_tensors", False))
        ownership[node] = mapped["owner"]
        group_sizes[mapped["owner"]] += 1
        for kind in ("ctrl", "data"):
            expected_edges.extend((node, kind, index, dep) for index, dep in enumerate(source[f"source_{kind}_deps"]))
        counts["nodes"] += 1
    if 0 in nodes or any(n < 1 for n in nodes):
        raise ValueError("External root sentinel became an operation")
    check_acyclic({n: r["deps"] for n, r in nodes.items()})
    check_acyclic({n: [] if r["parent"] == 0 else [r["parent"]] for n, r in nodes.items()})
    children = Counter(r["parent"] for r in nodes.values())
    # Ownership must be a complete connected call subtree. An unresolved parent
    # remains singleton, and therefore cannot silently consume unknown children.
    for node, owner in ownership.items():
        if owner not in nodes or ownership[owner] != owner:
            raise ValueError("Missing region root or multiply nested ownership")
        if node != owner and ownership.get(nodes[node]["parent"]) != owner:
            raise ValueError("Region not connected to its own source parent")
        if group_sizes[owner] > 1 and node != owner and nodes[node]["parent"] == 0:
            raise ValueError("Region crossed source roots")
    regions = {}
    for region in json_rows(region_path):
        owner = region["owner"]
        if owner in regions or owner not in group_sizes or region["rank"] != rank:
            raise ValueError("Missing or repeated region identity")
        if region["members"] != group_sizes[owner] or region["complete_target_operation"] is not False:
            raise ValueError("Region size or completeness claim invalid")
        if region["name"] != nodes[owner]["name"] or region["source_category"] != nodes[owner]["category"]:
            raise ValueError("Region root description changed")
        if region["source_duration_used"] or region["source_order_is_target_order"]:
            raise ValueError("Source timing or ordering promoted to target execution")
        rule, root = region["rule"], nodes[owner]
        if rule is None and group_sizes[owner] != 1:
            raise ValueError("Unresolved scope absorbed children")
        if rule is not None and root["domain"] != "CPU":
            raise ValueError("GPU implementation charged as another logical operator")
        if rule == "matrix_with_device_implementation":
            if region["matrix_work"] != matrix_records.get(owner) or not region["matrix_work"]:
                raise ValueError("Matrix work source changed")
            if root["name"] not in {"tex_ts::te_gemm_ts", "aten::mm", "aten::bmm"} or root["has_meta"]:
                raise ValueError("Unsupported matrix root")
        elif region["matrix_work"] is not None:
            raise ValueError("Unresolved call charged matrix work")
        if rule == "write_with_device_implementation" and (root["category"] != "write" or
                root["name"] not in {"aten::copy_", "aten::fill_", "aten::zero_", "aten::add_", "aten::mul_", "aten::div_"}
                or root["has_meta"]):
            raise ValueError("Unsupported write root")
        if rule not in {None, "alias_metadata", "same_allocation", "matrix_with_device_implementation",
                        "write_with_device_implementation"}:
            raise ValueError("Unknown region recipe")
        regions[owner] = region
        counts["rule:" + (rule or "unresolved")] += 1
    if set(regions) != set(group_sizes):
        raise ValueError("Some source nodes have no region")
    for node, owner in ownership.items():
        region, row, root = regions[owner], nodes[node], nodes[owner]
        rule = region["rule"]
        if rule == "alias_metadata":
            if row["domain"] != "CPU" or row["category"] != "alias" or not row["outputs"] or not row["storages"] <= root["storages"]:
                raise ValueError("Alias region contains another activity")
        elif rule == "same_allocation":
            if (row["domain"] != "CPU" or row["category"] != "allocate_uninitialized"
                    or not row["outputs"] or row["outputs"] != root["outputs"] or children[node] > 1):
                raise ValueError("Allocation region does not retain one exact output chain")
        elif rule in {"matrix_with_device_implementation", "write_with_device_implementation"} and node != owner:
            if row["domain"] != "GPU" or row["category"] != "device_implementation" or "nccl" in row["name"].lower():
                raise ValueError("Operator absorbed unsupported implementation")
        # Every selected rule covers the entire subtree, even for singleton rules.
        if row["parent"] != 0:
            parent_owner = ownership[row["parent"]]
            if parent_owner != owner and regions[parent_owner]["rule"] is not None:
                raise ValueError("Selected parent lost part of its subtree")
    graph = {owner: set() for owner in regions}
    for expected, recorded in zip_longest(expected_edges, json_rows(edge_path)):
        if expected is None or recorded is None:
            raise ValueError("Missing or extra dependency entry")
        node, kind, index, dep = expected
        wanted = dict(rank=rank, node_id=node, kind=kind, index=index, predecessor=dep,
                      owner=ownership[node], predecessor_owner=None if kind == "ctrl" and dep == 0 else ownership[dep])
        wanted["internal"] = wanted["owner"] == wanted["predecessor_owner"]
        if recorded != wanted:
            raise ValueError("Original dependency port or multiplicity changed")
        counts[kind + "_dependencies"] += 1
        counts[kind + ("_internal" if wanted["internal"] else "_boundary")] += 1
        if kind == "data" and not wanted["internal"]:
            graph[wanted["owner"]].add(wanted["predecessor_owner"])
    check_acyclic(graph)
    counts["regions"] = len(regions)
    counts["multi_record_regions"] = sum(size > 1 for size in group_sizes.values())
    counts["records_owned_by_multi_record_regions"] = sum(size for size in group_sizes.values() if size > 1)
    counts["absorbed_records"] = len(nodes) - len(regions)
    return dict(rank=rank, passed=True, counts=dict(sorted(counts.items())),
                source_and_quotient_acyclic=True, all_source_nodes_owned_once=True,
                exact_dependency_entries_retained=True, complete_target_workload=False)
