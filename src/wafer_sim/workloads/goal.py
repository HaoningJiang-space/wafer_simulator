"""Lossless GOAL ingestion and dependency checks, before simulator lowering.

CPU lanes, NICs and host ranks remain separate identifiers. In particular,
neither host ranks nor CPU lane numbers are silently treated as GPU ranks.
"""
from collections import Counter
import hashlib
from pathlib import Path
import re

from wafer_sim.io import read_json, write_json

OPERATION = re.compile(r"l(\d+): (calc|send|recv) (\d+)(b?)(.*)")
DEPENDENCY = re.compile(r"l(\d+) (requires|irequires) l(\d+)")
CPU = re.compile(r"cpu\s+(\d+)")
NIC = re.compile(r"nic\s+(\d+)")
PEER = re.compile(r"(?:to|from)\s+(\d+)\s+tag\s+(\d+)")


def ingest(source, preliminary_audit, output):
    """Preserve every operation and edge, then include message-arrival edges.

    A receive cannot complete before its matching send is issued. The edge
    send->recv here is a necessary order, not an eager/rendezvous timing model.
    This check never deletes a dependency to make an invalid trace runnable.
    """
    import numpy as np
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    audit = read_json(preliminary_audit)
    counts = audit["counts"]
    n = sum(counts.get(k, 0) for k in ("calc", "send", "recv"))
    m = sum(counts.get(k, 0) for k in ("requires", "irequires"))
    dtype = [("rank", "u4"), ("label", "u4"), ("kind", "u1"),
             ("amount", "u8"), ("cpu", "i4"), ("nic", "i4"),
             ("peer", "i4"), ("tag", "u8"), ("line", "u4")]
    ops = np.lib.format.open_memmap(output / "operations.npy", mode="w+", dtype=dtype, shape=(n,))
    refs = np.lib.format.open_memmap(output / "dependency_refs.npy", mode="w+", dtype="u8", shape=(m, 4))
    op_count = dep_count = 0
    rank = None
    declared = None
    sha = hashlib.sha256()
    for line_number, raw in enumerate(source.open("rb"), 1):
        sha.update(raw)
        line = raw.decode().strip()
        if not line or line == "}":
            continue
        if line.startswith("num_ranks "):
            declared = int(line.split()[1])
            continue
        if line.startswith("rank "):
            rank = int(line.split()[1])
            continue
        if rank is None or declared is None or not 0 <= rank < declared:
            raise ValueError(f"Operation outside a declared rank at line {line_number}")
        dep = DEPENDENCY.fullmatch(line)
        if dep:
            child, relation, parent = dep.groups()
            if dep_count >= m:
                raise ValueError("Dependency count exceeds preliminary audit")
            refs[dep_count] = (rank << 32 | int(parent), rank << 32 | int(child),
                               relation == "irequires", line_number)
            dep_count += 1
            continue
        match = OPERATION.fullmatch(line)
        if not match:
            raise ValueError(f"Unsupported GOAL syntax at line {line_number}: {line}")
        label, kind, amount, suffix, extra = match.groups()
        if (kind == "calc" and suffix) or (kind != "calc" and suffix != "b"):
            raise ValueError(f"Invalid work unit at line {line_number}")
        cpu, nic, peer = CPU.search(extra), NIC.search(extra), PEER.search(extra)
        if kind != "calc" and not peer:
            raise ValueError(f"Missing communication peer at line {line_number}")
        if op_count >= n:
            raise ValueError("Operation count exceeds preliminary audit")
        ops[op_count] = (rank, int(label), {"calc": 0, "send": 1, "recv": 2}[kind],
                         int(amount), int(cpu[1]) if cpu else 0,
                         int(nic[1]) if nic else -1, int(peer[1]) if peer else -1,
                         int(peer[2]) if peer else 0, line_number)
        op_count += 1
    if op_count != n or dep_count != m or sha.hexdigest() != audit["source_sha256"]:
        raise ValueError("Full input count/hash differs from preliminary audit")
    ops.flush()
    refs.flush()
    print(f"Parsed all {n} operations and {m} dependencies", flush=True)

    keys = ops["rank"].astype("u8") << 32 | ops["label"]
    order = np.argsort(keys)
    sorted_keys = keys[order]
    if np.any(sorted_keys[1:] == sorted_keys[:-1]):
        raise ValueError("Duplicate rank/label operation")
    positions = np.searchsorted(sorted_keys, refs[:, :2])
    if np.any(positions >= n) or np.any(sorted_keys[np.minimum(positions, n-1)] != refs[:, :2]):
        raise ValueError("Dependency refers to an absent operation")
    if np.any(refs[:, 2]):
        raise ValueError("Start dependencies require a separate event graph; not silently converted")
    edges = order[positions].astype("i4")
    if np.any(edges[:, 0] == edges[:, 1]):
        raise ValueError("Self dependency")
    sends, recvs = {}, {}
    for i in np.flatnonzero(ops["kind"]):
        op = ops[i]
        key = (int(op["rank"]), int(op["peer"]), int(op["tag"]))
        table = sends if op["kind"] == 1 else recvs
        if op["kind"] == 2:
            key = (key[1], key[0], key[2])
        if key in table:
            raise ValueError(f"Ambiguous communication identity: {key}")
        table[key] = int(i)
    if sends.keys() != recvs.keys():
        raise ValueError("Unmatched communication")
    pairs = np.array([(s, recvs[key]) for key, s in sends.items()], dtype="i4")
    if np.any(ops["amount"][pairs[:, 0]] != ops["amount"][pairs[:, 1]]):
        raise ValueError("Message size mismatch")
    all_edges = np.concatenate((edges, pairs))
    # Preserve duplicate input relations on disk; count them explicitly.
    graph = coo_matrix((np.ones(len(all_edges), dtype="i4"),
                        (all_edges[:, 0], all_edges[:, 1])), shape=(n, n)).tocsr()
    duplicates = len(all_edges) - graph.nnz
    component_count, labels = connected_components(graph, directed=True, connection="strong")
    sizes = np.bincount(labels)
    cyclic = np.flatnonzero(sizes > 1)
    np.save(output / "dependencies.npy", edges)
    np.save(output / "message_pairs.npy", pairs)
    np.save(output / "components.npy", labels)
    result = dict(source=str(source), source_sha256=sha.hexdigest(),
                  operations=n, input_dependencies=m, matched_messages=len(pairs),
                  duplicate_relations=int(duplicates), components=component_count,
                  cyclic_components=len(cyclic), nodes_in_cyclic_components=int(sizes[cyclic].sum()),
                  largest_cyclic_component=int(sizes[cyclic].max()) if len(cyclic) else 0,
                  complete_graph_checked=True, truncated=False, removed_dependencies=0,
                  dependency_gate_passed=not len(cyclic), execution_claim=False)
    if len(cyclic):
        component = int(cyclic[np.argmin(sizes[cyclic])])
        members = np.flatnonzero(labels == component)
        # In an SCC every node has an internal successor. Following one must
        # produce a closed, independently inspectable cycle witness.
        walk, seen = [], {}
        current = int(members[0])
        while current not in seen:
            seen[current] = len(walk)
            walk.append(current)
            adjacent = graph.indices[graph.indptr[current]:graph.indptr[current+1]]
            current = int(next(x for x in adjacent if labels[x] == component))
        cycle = walk[seen[current]:] + [current]
        result["cycle_witness"] = [dict(id=i, **{field: int(ops[i][field]) for field in ops.dtype.names})
                                   for i in cycle]
        result["cycle_witness_edges"] = []
        needed = set(zip(cycle[:-1], cycle[1:]))
        for index, (parent, child) in enumerate(edges):
            if (int(parent), int(child)) in needed:
                result["cycle_witness_edges"].append(dict(parent=int(parent), child=int(child),
                                                           type="requires", line=int(refs[index, 3])))
        for parent, child in pairs:
            if (int(parent), int(child)) in needed:
                result["cycle_witness_edges"].append(dict(parent=int(parent), child=int(child), type="message_match"))
    write_json(output / "graph_audit.json", result)
    print({k: v for k, v in result.items() if not k.startswith("cycle_witness")}, flush=True)
    return result
