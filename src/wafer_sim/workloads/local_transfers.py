"""Recover explicit intra-host transfer pairs from source and original edges.

No timing conversion is permitted before all source writes correspond to the
published workload and every local send/receive has a unique compatible peer.
"""
from pathlib import Path
import numpy as np

from wafer_sim.adapters.atlahs_observer import DTYPE
from wafer_sim.io import digest, read_json, write_json


def pair_transfers(ops, dependencies, source):
    ids = np.flatnonzero(ops["kind"] == 0)
    if len(source) != len(ids) or any(not np.array_equal(source[a], ops[b][ids])
            for a, b in (("rank", "rank"), ("label", "label"), ("cpu", "cpu"))):
        raise ValueError("Source identities are not identical to original calc operations")
    role = np.zeros(len(ops), dtype="i1")
    gpu = np.full(len(ops), -1, dtype="i2")
    peer = gpu.copy()
    size = np.zeros(len(ops), dtype="i8")
    transfer = source["category"] == 5
    role[ids[transfer]] = source["role"][transfer]
    gpu[ids[transfer]] = source["gpu"][transfer]
    peer[ids[transfer]] = source["peer_gpu"][transfer]
    size[ids[transfer]] = source["model_bytes"][transfer]
    parent, child = dependencies.T
    selected = ((role[parent] == 1) & (role[child] == 2) & (gpu[parent] != gpu[child])
                & (peer[parent] == gpu[child]) & (peer[child] == gpu[parent]))
    pairs = np.asarray(dependencies[selected], dtype="i4")
    sends, recvs = pairs.T if len(pairs) else (np.array([], dtype="i4"), np.array([], dtype="i4"))
    expected_sends, expected_recvs = np.flatnonzero(role == 1), np.flatnonzero(role == 2)
    send_ids, send_counts = np.unique(sends, return_counts=True)
    recv_ids, recv_counts = np.unique(recvs, return_counts=True)
    missing_sends = np.setdiff1d(expected_sends, send_ids)
    missing_recvs = np.setdiff1d(expected_recvs, recv_ids)
    invalid_size = size[sends] != size[recvs]
    host_mismatch = ops["rank"][sends] != ops["rank"][recvs]
    zero_size = size[sends] <= 0
    result = dict(source_send_calcs=len(expected_sends), source_recv_calcs=len(expected_recvs),
        pairs=len(pairs), missing_send_count=len(missing_sends), missing_recv_count=len(missing_recvs),
        multiply_paired_send_count=int((send_counts != 1).sum()),
        multiply_paired_recv_count=int((recv_counts != 1).sum()),
        size_mismatch_count=int(invalid_size.sum()), host_mismatch_count=int(host_mismatch.sum()),
        nonpositive_size_count=int(zero_size.sum()),
        missing_send_examples=missing_sends[:10].tolist(), missing_recv_examples=missing_recvs[:10].tolist(),
        represented_transfer_bytes=int(size[sends].sum()),
        replaced_send_calc_cycles=int(ops["amount"][expected_sends].sum()),
        replaced_recv_calc_cycles=int(ops["amount"][expected_recvs].sum()),
        all_original_dependencies_retained=True, durations_modified=False)
    result["all_transfers_paired"] = not any(result[k] for k in (
        "missing_send_count", "missing_recv_count", "multiply_paired_send_count", "multiply_paired_recv_count",
        "size_mismatch_count", "host_mismatch_count", "nonpositive_size_count"))
    return pairs, size[sends], result


def recover(graph, regenerated, provenance):
    graph, regenerated, provenance = map(Path, (graph, regenerated, provenance))
    association = read_json(provenance / "SOURCE_CORRESPONDENCE.json")
    if not association["source_correspondence_passed"]:
        raise ValueError("Complete source correspondence is required")
    observed = read_json(regenerated / "CALC_PROVENANCE.json")
    if digest(regenerated / "calc_provenance.bin") != observed["binary_sha256"]:
        raise ValueError("Source records changed")
    ops = np.load(graph / "operations.npy", mmap_mode="r")
    deps = np.load(graph / "dependencies.npy", mmap_mode="r")
    source = np.memmap(regenerated / "calc_provenance.bin", dtype=DTYPE, mode="r")
    pairs, sizes, result = pair_transfers(ops, deps, source)
    np.save(provenance / "local_transfer_pairs.npy", pairs)
    np.save(provenance / "local_transfer_bytes.npy", sizes)
    result["input_sha256"] = {str(p.resolve()): digest(p) for p in (
        graph / "operations.npy", graph / "dependencies.npy", provenance / "SOURCE_CORRESPONDENCE.json",
        regenerated / "CALC_PROVENANCE.json")}
    result["artifact_sha256"] = {name: digest(provenance / name) for name in (
        "local_transfer_pairs.npy", "local_transfer_bytes.npy")}
    result["scope"] = "Source transfer model byte arguments and original cross-GPU dependency pairing; no M1 execution"
    write_json(provenance / "LOCAL_TRANSFERS.json", result)
    return result
