"""Lower a fully audited GOAL graph to the author's native trace format."""
import json
from pathlib import Path

from wafer_sim.io import digest, read_json, write_json


def lower(graph_directory, destination, mapping, flit_bytes=2000):
    import numpy as np
    from scipy.sparse import coo_matrix
    graph_directory, destination = Path(graph_directory), Path(destination)
    checked = read_json(graph_directory / "graph_audit.json")
    if not checked["dependency_gate_passed"] or checked["removed_dependencies"] or checked["truncated"]:
        raise ValueError("Only complete, unmodified acyclic inputs can be lowered")
    ops = np.load(graph_directory / "operations.npy", mmap_mode="r")
    deps = np.load(graph_directory / "dependencies.npy", mmap_mode="r")
    pairs = np.load(graph_directory / "message_pairs.npy", mmap_mode="r")
    edges = np.concatenate((deps, pairs))
    reverse = coo_matrix((np.ones(len(edges), dtype="i4"), (edges[:, 0], edges[:, 1])),
                         shape=(len(ops), len(ops))).tocsr()
    indegree = np.bincount(edges[:, 1], minlength=len(ops))
    parallel_relations = reverse.nnz != len(edges)
    identities = sorted(set((int(op["rank"]), int(op["nic"])) for op in ops if op["kind"]))
    if len(identities) != len(mapping) or len(set(mapping)) != len(mapping):
        raise ValueError("Endpoint mapping must be injective and cover every host/NIC pair")
    endpoints = dict(zip(identities, mapping))
    recv_for_send = dict(map(lambda pair: (int(pair[0]), int(pair[1])), pairs))
    cpu_stride = int(ops["cpu"].max())+1
    if np.any(ops["cpu"] < 0):
        raise ValueError("Negative CPU resource")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w") as stream:
        stream.write("[\n")
        for i, op in enumerate(ops):
            network = int(op["kind"]) == 1
            src = dst = -1
            if network:
                recv = ops[recv_for_send[i]]
                src = endpoints[int(op["rank"]), int(op["nic"])]
                dst = endpoints[int(recv["rank"]), int(recv["nic"])]
                if src == dst or not op["amount"]:
                    raise ValueError("Zero-byte or same-endpoint communication needs an explicit model")
            begin, end = reverse.indptr[i:i+2]
            successors = reverse.indices[begin:end]
            if parallel_relations:
                # A recovered local receive has both its original requires
                # edge and the matching arrival relation. Preserve both in
                # native counters, rather than merging only the successors.
                successors = np.repeat(successors, reverse.data[begin:end])
            entry = dict(id=i, cycle=0, src=src, dst=dst,
                         num_deps=int(indegree[i]),
                         rev_deps=successors.tolist(),
                         num_flits=(int(op["amount"])+flit_bytes-1)//flit_bytes if network else 0,
                         duration=int(op["amount"]) if op["kind"] == 0 else 0,
                         ignore=not network, cpu_resource=int(op["rank"])*cpu_stride+int(op["cpu"]))
            stream.write(("," if i else "")+json.dumps(entry, separators=(",", ":"))+"\n")
        stream.write("]\n")
    sends = ops["kind"] == 1
    work = dict(source_sha256=checked["source_sha256"], instructions=len(ops),
                original_dependencies=len(deps), arrival_dependencies=len(pairs),
                messages=int(sends.sum()), payload_bytes=int(ops["amount"][sends].sum()),
                flits=int(((ops["amount"][sends]+flit_bytes-1)//flit_bytes).sum()),
                compute_cycles=int(ops["amount"][ops["kind"] == 0].sum()),
                cpu_lanes=len(set(zip(ops["rank"].tolist(), ops["cpu"].tolist()))),
                endpoints=len(identities), cpu_stride=cpu_stride,
                flit_bytes=flit_bytes, input_truncated=False, removed_dependencies=0)
    contract = dict(work=work, trace_sha256=digest(destination),
                    endpoint_mapping=[dict(host=h, nic=nic, node=node) for (h, nic), node in endpoints.items()],
                    cpu_policy="FCFS in deterministic dependency-ready callback order",
                    send_policy="zero CPU issue overhead; complete after every network flit arrives",
                    receive_policy="complete after local prerequisites, matched send, and CPU availability",
                    calc_policy="unscaled published nanoseconds at 1 GHz; includes opaque local transfers")
    write_json(destination.parent / "contract.json", contract)
    return contract
