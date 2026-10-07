"""Disjoint source-call ownership, before target scheduling or tensor binding.

A region owns source records, not a timed completion event. Its original ports
and every dependency remain in the output. Even an acyclic quotient does not
prove that source ordering is target dataflow or that asynchronous work has
finished when its CPU caller returns.
"""
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
import sys


def tensor_identity(ref):
    return tuple(ref[k] for k in ("tensor_id", "storage_id", "source_offset", "num_elements",
                                  "element_bytes", "source_device")) + (tuple(ref["shape"]), ref["dtype"])


@dataclass(frozen=True, slots=True)
class Call:
    node_id: int
    parent: int
    dependencies: tuple[int, ...]
    name: str
    domain: str
    category: str
    storages: frozenset
    outputs: tuple
    has_meta: bool
    matrix_record: bool

    @classmethod
    def from_row(cls, row, matrix_ids=()):
        parents = row["source_ctrl_deps"]
        if len(parents) != 1:
            raise ValueError("Exactly one source parent, including explicit root 0, required")
        effect = row["effects"]
        refs = effect.get("inputs", []) + effect.get("outputs", [])
        return cls(row["node_id"], parents[0], tuple(row["source_data_deps"]),
                   sys.intern(row["name"]), sys.intern(row["source_domain"]), sys.intern(effect["category"]),
                   frozenset((r["storage_id"], r["source_device"]) for r in refs),
                   tuple(tensor_identity(r) for r in effect.get("outputs", [])),
                   row.get("contains_meta_tensors", False), row["node_id"] in matrix_ids)


@dataclass
class Partition:
    owners: dict[int, int]
    rules: dict[int, str | None]
    rejected: dict[int, str]
    proposed_regions: int


def source_forest(calls):
    if not calls or 0 in calls or any(key != c.node_id or key < 1 for key, c in calls.items()):
        raise ValueError("Positive unique source identities required; 0 is an external parent sentinel")
    children = {node: [] for node in calls}
    roots = []
    for node, call in calls.items():
        if call.domain not in {"CPU", "GPU"}:
            raise ValueError("Unknown source domain")
        if call.parent == 0:
            roots.append(node)
        elif call.parent in calls:
            children[call.parent].append(node)
        else:
            raise ValueError("Missing source parent")
        if any(dep not in calls for dep in call.dependencies):
            raise ValueError("Missing source dependency")
    order, pending = [], sorted(roots, reverse=True)
    while pending:
        node = pending.pop()
        order.append(node)
        pending.extend(sorted(children[node], reverse=True))
    if len(order) != len(calls):
        raise ValueError("Source parent cycle")
    try:
        tuple(TopologicalSorter({n: c.dependencies for n, c in calls.items()}).static_order())
    except CycleError as error:
        raise ValueError("Source dependency cycle") from error
    return children, order


def candidate_rules(calls, children, order):
    """Only whole subtrees with a checked, limited implementation recipe."""
    rules, device_subtree = {}, {}
    for node in reversed(order):
        call, kids = calls[node], children[node]
        device_subtree[node] = (call.domain == "GPU" and call.category == "device_implementation"
                                and "nccl" not in call.name.lower()
                                and all(device_subtree[k] for k in kids))
        rule = None
        if call.domain == "CPU":
            if (call.category == "alias" and call.outputs and all(
                    rules[k] == "alias_metadata" and calls[k].storages <= call.storages for k in kids)):
                rule = "alias_metadata"
            elif (call.category == "allocate_uninitialized" and call.outputs and len(kids) <= 1 and all(
                    rules[k] == "same_allocation" and calls[k].outputs == call.outputs for k in kids)):
                rule = "same_allocation"
            elif all(device_subtree[k] for k in kids) and not call.has_meta:
                if call.matrix_record and call.name in {"tex_ts::te_gemm_ts", "aten::mm", "aten::bmm"}:
                    rule = "matrix_with_device_implementation"
                elif call.category == "write" and call.name in {
                        "aten::copy_", "aten::fill_", "aten::zero_", "aten::add_", "aten::mul_", "aten::div_"}:
                    rule = "write_with_device_implementation"
        rules[node] = rule
    return rules


def quotient(calls, owners):
    result = {owner: set() for owner in owners.values()}
    for node, call in calls.items():
        owner = owners[node]
        result[owner].update(owners[dep] for dep in call.dependencies if owners[dep] != owner)
    return result


def partition_calls(calls):
    children, order = source_forest(calls)
    candidates = candidate_rules(calls, children, order)
    owners, rules = {}, {}
    # A selected ancestor owns its entire subtree; unsupported parents retain a
    # residual source record and do not consume independently supported children.
    for node in order:
        parent = calls[node].parent
        if parent in owners and rules[owners[parent]] is not None:
            owners[node] = owners[parent]
        else:
            owners[node] = node
            rules[node] = candidates[node]
    groups = {}
    for node, owner in owners.items():
        groups.setdefault(owner, []).append(node)
    proposed = sum(len(members) > 1 for members in groups.values())
    rejected = {}
    graph = quotient(calls, owners)
    try:
        tuple(TopologicalSorter(graph).static_order())
    except CycleError:
        # Independent source work may interleave with a call's implementation.
        # Expand every nontrivial region in a cyclic SCC, keeping downstream
        # regions intact. NetworkX is an existing project dependency.
        import networkx as nx
        directed = nx.DiGraph()
        directed.add_nodes_from(graph)
        directed.add_edges_from((dep, node) for node, deps in graph.items() for dep in deps)
        for component in nx.strongly_connected_components(directed):
            if len(component) <= 1:
                continue
            for owner in sorted(component):
                if len(groups[owner]) > 1:
                    rejected[owner] = "source_dependency_interleaves_region"
                    for node in groups[owner]:
                        owners[node] = node
                        # Retain ports; no claim that the residual parent and
                        # child can independently be charged as logical work.
                        rules[node] = None
        tuple(TopologicalSorter(quotient(calls, owners)).static_order())
    return Partition(owners, rules, rejected, proposed)
