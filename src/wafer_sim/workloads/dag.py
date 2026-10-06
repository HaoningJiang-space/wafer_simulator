"""Strict completion DAG. Dependencies refer to completion, not issue."""
from collections import deque

from wafer_sim.io import object_digest


def validate(workload):
    nodes = workload["nodes"]
    ranks = workload["ranks"]
    if type(ranks) is not int or ranks <= 0 or not nodes:
        raise ValueError("A workload needs positive ranks and nonempty nodes")
    by_id = {n["id"]: n for n in nodes}
    if len(by_id) != len(nodes) or set(by_id) != set(range(len(nodes))):
        raise ValueError("Node IDs must be unique and contiguous from zero")
    reverse = {i: [] for i in by_id}
    degrees = {}
    for node in nodes:
        if node["kind"] not in {"compute", "message", "join"}:
            raise ValueError("Unknown operation kind")
        for field in ("duration_cycles", "bytes", "release_cycle"):
            if type(node[field]) is not int or node[field] < 0:
                raise ValueError(f"Invalid {field}")
        if len(node["deps"]) != len(set(node["deps"])):
            raise ValueError("Duplicate dependency")
        if not 0 <= node["rank"] < ranks:
            raise ValueError("Invalid rank")
        if node["kind"] == "message":
            if not 0 <= node["dst"] < ranks or node["dst"] == node["rank"]:
                raise ValueError("Message must have a different valid destination")
            if node["bytes"] <= 0 or node["duration_cycles"]:
                raise ValueError("Messages need positive bytes and zero duration")
        elif node["bytes"] or (node["kind"] == "join" and node["duration_cycles"]):
            raise ValueError("Invalid compute/join work")
        degrees[node["id"]] = len(node["deps"])
        for dep in node["deps"]:
            if dep not in by_id or dep == node["id"]:
                raise ValueError("Missing or self dependency")
            reverse[dep].append(node["id"])
    queue = deque(i for i in by_id if degrees[i] == 0)
    order = []
    while queue:
        i = queue.popleft()
        order.append(i)
        for nxt in reverse[i]:
            degrees[nxt] -= 1
            if degrees[nxt] == 0:
                queue.append(nxt)
    if len(order) != len(nodes):
        raise ValueError("Cyclic workload; dependencies will not be removed")
    # A single compute lane per rank is guaranteed by an explicit ordering
    # contract in generated workloads; imported DAGs must declare their model.
    return order, reverse


def summary(workload, flit_bytes=2000):
    validate(workload)
    messages = [n for n in workload["nodes"] if n["kind"] == "message"]
    return {
        "workload_sha256": object_digest(workload),
        "ranks": workload["ranks"], "instructions": len(workload["nodes"]),
        "messages": len(messages), "payload_bytes": sum(n["bytes"] for n in messages),
        "flits": sum((n["bytes"] + flit_bytes - 1) // flit_bytes for n in messages),
        "compute_cycles": sum(n["duration_cycles"] for n in workload["nodes"]),
    }


def lower_to_booksim(workload, rank_to_node, flit_bytes=2000):
    _, reverse = validate(workload)
    if len(rank_to_node) != workload["ranks"] or len(set(rank_to_node)) != len(rank_to_node):
        raise ValueError("Rank mapping must be injective and cover all ranks")
    return [{
        "id": n["id"], "cycle": n["release_cycle"],
        "src": rank_to_node[n["rank"]] if n["kind"] == "message" else -1,
        "dst": rank_to_node[n["dst"]] if n["kind"] == "message" else -1,
        "num_deps": len(n["deps"]), "rev_deps": reverse[n["id"]],
        "num_flits": (n["bytes"] + flit_bytes - 1) // flit_bytes,
        "duration": n["duration_cycles"], "ignore": n["kind"] != "message",
        "cpu_resource": n.get("cpu_resource", -1),
    } for n in workload["nodes"]]


def compute_only_bound(workload):
    """Zero-time network critical path under the same declared dependencies."""
    order, _ = validate(workload)
    by_id = {n["id"]: n for n in workload["nodes"]}
    finish = {}
    for i in order:
        n = by_id[i]
        finish[i] = max([n["release_cycle"]] + [finish[d] for d in n["deps"]]) + n["duration_cycles"]
    return max(finish.values())
