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


def materialize(original, graph, regenerated, extracted, provenance, output):
    """M0 remains the original file; M1 changes only verified transfer calcs.

    Both transfer endpoint costs are removed. The send becomes target network
    service and its paired receive becomes a zero-service dependency marker.
    All existing requires lines are retained verbatim, including send->receive.
    """
    import pickle
    original, graph, regenerated, extracted, provenance, output = map(Path, (
        original, graph, regenerated, extracted, provenance, output))
    association = read_json(provenance / "SOURCE_CORRESPONDENCE.json")
    transfers = read_json(provenance / "LOCAL_TRANSFERS.json")
    regeneration = read_json(regenerated / "REGENERATION.json")
    extraction = read_json(extracted / "EXTRACTED.json")
    if not association["source_correspondence_passed"] or not transfers["all_transfers_paired"]:
        raise ValueError("M1 requires complete source association and transfer pairing")
    if digest(original) != association["original_goal_sha256"]:
        raise ValueError("M0 source changed")
    for record in (association["input_sha256"], transfers["input_sha256"]):
        for path, sha in record.items():
            if digest(path) != sha:
                raise ValueError(f"Accepted provenance changed: {path}")
    for name, sha in transfers["artifact_sha256"].items():
        if digest(provenance / name) != sha:
            raise ValueError(f"Transfer pairing changed: {name}")
    if (digest(extracted / "EXTRACTED.json") != regeneration["extracted_manifest_sha256"] or
            digest(extracted / "events.pkl") != extraction["bundle_sha256"]):
        raise ValueError("Source GPU identities changed")
    with (extracted / "events.pkl").open("rb") as f:
        bundle = pickle.load(f)  # Only our hash-checked, locally extracted file.
    gpu_to_nic = {int(gpu): (rank, nic) for rank, host in enumerate(regeneration["source_host_order"])
                  for nic, gpu in enumerate(bundle["groups"][host])}
    ops = np.load(graph / "operations.npy", mmap_mode="r")
    source = np.memmap(regenerated / "calc_provenance.bin", dtype=DTYPE, mode="r")
    if digest(regenerated / "calc_provenance.bin") != read_json(regenerated / "CALC_PROVENANCE.json")["binary_sha256"]:
        raise ValueError("Source records changed")
    calc_ids = np.flatnonzero(ops["kind"] == 0)
    position = np.full(len(ops), -1, dtype="i8")
    position[calc_ids] = np.arange(len(calc_ids))
    pairs = np.load(provenance / "local_transfer_pairs.npy", mmap_mode="r")
    sizes = np.load(provenance / "local_transfer_bytes.npy", mmap_mode="r")
    role, peer, nic = np.zeros(len(ops), dtype="i1"), np.full(len(ops), -1, dtype="i4"), np.full(len(ops), -1, dtype="i4")
    amounts, tags = np.zeros(len(ops), dtype="u8"), np.zeros(len(ops), dtype="u8")
    first_tag = int(ops["tag"].max()) + 1
    for index, (send, recv) in enumerate(pairs):
        send, recv = int(send), int(recv)
        a, b = source[position[send]], source[position[recv]]
        source_host, source_nic = gpu_to_nic[int(a["gpu"])]
        target_host, target_nic = gpu_to_nic[int(b["gpu"])]
        if source_host != int(ops[send]["rank"]) or target_host != int(ops[recv]["rank"]) or (source_host, source_nic) == (target_host, target_nic):
            raise ValueError("Source GPU does not match distinct target endpoints")
        role[send], role[recv] = 1, 2
        peer[send], peer[recv] = target_host, source_host
        nic[send], nic[recv] = source_nic, target_nic
        amounts[send] = amounts[recv] = int(sizes[index])
        tags[send] = tags[recv] = first_tag + index
    output.mkdir(parents=True, exist_ok=False)
    destination = output / "M1.goal"
    op_id = changed = 0
    with original.open() as inp, destination.open("w") as out:
        for number, line in enumerate(inp, 1):
            if ": " in line:
                if number != int(ops[op_id]["line"]):
                    raise ValueError("Source operation line mapping changed")
                if role[op_id]:
                    kind, direction = ("send", "to") if role[op_id] == 1 else ("recv", "from")
                    line = (f"l{ops[op_id]['label']}: {kind} {amounts[op_id]}b {direction} {peer[op_id]} "
                            f"tag {tags[op_id]} cpu {ops[op_id]['cpu']} nic {nic[op_id]}\n")
                    changed += 1
                op_id += 1
            out.write(line)
    if op_id != len(ops) or changed != 2 * len(pairs):
        raise ValueError("Transfer substitution did not conserve operation identities")
    result = dict(model="M1", m0_source=str(original.resolve()), m0_source_sha256=digest(original),
        source_goal=str(destination.resolve()), source_sha256=digest(destination),
        operation_count=op_id, changed_transfer_operations=changed, explicit_local_messages=len(pairs),
        added_message_bytes=int(sizes.sum()), added_flits=int(((sizes + 1999) // 2000).sum()),
        original_nontransfer_lines_unchanged=True, removed_dependencies=0,
        retained_local_costs="All measured intervals, reduction/copy and zero synchronization costs remain byte-identical",
        transfer_costs="Replace both fixed endpoint costs with one target network message; no double charging",
        gpu_to_host_nic={str(k): list(v) for k, v in gpu_to_nic.items()},
        source_correspondence_sha256=digest(provenance / "SOURCE_CORRESPONDENCE.json"),
        transfer_pairing_sha256=digest(provenance / "LOCAL_TRANSFERS.json"),
        m0_regenerated=False, new_simulations_launched=0)
    write_json(output / "TRANSFORMATION.json", result)
    return result


def audit_target_graph(original_graph, target_graph, provenance):
    """Independently check every rewritten operation and all original relations."""
    original_graph, target_graph, provenance = map(Path, (original_graph, target_graph, provenance))
    before = np.load(original_graph / "operations.npy", mmap_mode="r")
    after = np.load(target_graph / "operations.npy", mmap_mode="r")
    pairs = np.load(provenance / "local_transfer_pairs.npy", mmap_mode="r")
    sizes = np.load(provenance / "local_transfer_bytes.npy", mmap_mode="r")
    if len(before) != len(after):
        raise ValueError("Operation count changed")
    replaced = np.zeros(len(before), dtype=bool)
    replaced[pairs.ravel()] = True
    if not np.array_equal(before[~replaced], after[~replaced]):
        raise ValueError("A non-transfer operation changed")
    for field in ("rank", "label", "cpu", "line"):
        if not np.array_equal(before[field], after[field]):
            raise ValueError(f"Original operation identity/resource changed: {field}")
    sends, recvs = pairs.T
    if (np.any(after["kind"][sends] != 1) or np.any(after["kind"][recvs] != 2) or
            not np.array_equal(after["amount"][sends], sizes) or
            not np.array_equal(after["amount"][recvs], sizes) or
            not np.array_equal(after["tag"][sends], after["tag"][recvs])):
        raise ValueError("Recovered transfer identity or size changed")
    if digest(original_graph / "dependencies.npy") != digest(target_graph / "dependencies.npy"):
        raise ValueError("Original dependencies changed")
    expected = np.concatenate((np.load(original_graph / "message_pairs.npy", mmap_mode="r"), pairs))
    actual = np.load(target_graph / "message_pairs.npy", mmap_mode="r")
    if len(expected) != len(actual) or not np.array_equal(expected[np.argsort(expected[:, 0])], actual[np.argsort(actual[:, 0])]):
        raise ValueError("Matched transfer relations do not conserve original and recovered messages")
    from scipy.sparse import coo_matrix
    def predicates(path):
        edges = np.concatenate([np.load(path / name, mmap_mode="r") for name in (
            "dependencies.npy", "message_pairs.npy")])
        return coo_matrix((np.ones(len(edges), dtype="i1"), (edges[:, 0], edges[:, 1])),
                          shape=(len(before), len(before))).tocsr()
    old_pred, new_pred = predicates(original_graph), predicates(target_graph)
    if (not np.array_equal(old_pred.indptr, new_pred.indptr) or
            not np.array_equal(old_pred.indices, new_pred.indices)):
        raise ValueError("Native predecessor predicates differ from original complete M0")
    old_cost = int(before["amount"][before["kind"] == 0].sum())
    new_cost = int(after["amount"][after["kind"] == 0].sum())
    removed = int(before["amount"][replaced].sum())
    if old_cost - new_cost != removed:
        raise ValueError("Fixed cost removal does not equal both transfer endpoint costs")
    result = dict(passed=True, all_operations_checked=len(before), transfer_operations=int(replaced.sum()),
        original_local_cycles=old_cost, remaining_local_cycles=new_cost, replaced_transfer_cycles=removed,
        original_dependencies_byte_identical=True, original_message_pairs_retained=True,
        nontransfer_operations_byte_identical=True, no_transfer_double_charge=True,
        native_predecessor_graph_identical_to_M0=True, native_dependency_edges=new_pred.nnz,
        target_artifacts_sha256={name: digest(target_graph / name) for name in (
            "operations.npy", "dependencies.npy", "message_pairs.npy", "graph_audit.json")})
    write_json(target_graph.parent / "TRANSFORMATION_AUDIT.json", result)
    return result
