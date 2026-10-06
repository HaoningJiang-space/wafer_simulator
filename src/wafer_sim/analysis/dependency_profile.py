"""Readback of complete dependency profiles; never infer GPU speed from widths."""
from pathlib import Path

from wafer_sim.io import read_json, write_json


def _histogram(record):
    bins = record["bins"]
    if len(bins) != 65 or any(type(n) is not int or n < 0 for n in bins):
        raise ValueError("Invalid dependency histogram bins")
    samples, total, maximum = (record[k] for k in ("samples", "total", "maximum"))
    if any(type(n) is not int or n < 0 for n in (samples, total, maximum)):
        raise ValueError("Invalid dependency histogram counters")
    if sum(bins) != samples:
        raise ValueError("Dependency histogram sample mismatch")
    lower = sum(n * (1 << (k - 1)) for k, n in enumerate(bins) if k)
    upper = sum(n * ((1 << k) - 1) for k, n in enumerate(bins) if k)
    if not lower <= total <= upper or maximum > total:
        raise ValueError("Dependency histogram total mismatch")
    if samples:
        last = max(k for k, n in enumerate(bins) if n)
        if maximum.bit_length() != last:
            raise ValueError("Dependency histogram maximum mismatch")
    elif total or maximum:
        raise ValueError("Nonempty counters without samples")


def validate(profile, instructions, edges, initial_roots):
    if profile.get("schema_version") != 1 or profile.get("complete") is not True:
        raise ValueError("A complete dependency profile is required")
    expected = dict(instructions_expected=instructions, instructions_completed=instructions,
                    static_edges=edges, initial_roots=initial_roots)
    for name, value in expected.items():
        if profile[name] != value:
            raise ValueError(f"Dependency profile mismatch: {name}")
    edge_hist = profile["successor_edges_per_completion"]
    ready_hist = profile["newly_ready_per_completion"]
    cycle_hist = profile["completions_per_active_cycle"]
    for histogram in (edge_hist, ready_hist, cycle_hist):
        _histogram(histogram)
    if edge_hist["samples"] != instructions or edge_hist["total"] != edges:
        raise ValueError("Dependency edge accounting mismatch")
    if ready_hist["samples"] != instructions or ready_hist["total"] + initial_roots != instructions:
        raise ValueError("Dependency readiness accounting mismatch")
    if cycle_hist["total"] != instructions or cycle_hist["bins"][0]:
        raise ValueError("Dependency completion accounting mismatch")
    storage = (instructions + 1) * profile["row_offset_bytes"] + edges * profile["successor_id_bytes"]
    if storage != profile["csr_storage_bytes"]:
        raise ValueError("Dependency CSR storage accounting mismatch")
    return dict(passed=True, instructions=instructions, edges=edges,
                initial_roots=initial_roots, csr_storage_bytes=storage,
                max_newly_ready_per_completion=ready_hist["maximum"],
                max_completions_per_active_cycle=cycle_hist["maximum"],
                scope="Dependency widths only; same-cycle events need not be independent")


def audit(graph_directory, run_directory):
    import numpy as np
    graph_directory, run_directory = Path(graph_directory), Path(run_directory)
    work = read_json(run_directory / "contract.json")["work"]
    has_predecessor = np.zeros(work["instructions"], dtype=bool)
    edge_count = 0
    for name in ("dependencies.npy", "message_pairs.npy"):
        edges = np.load(graph_directory / name, mmap_mode="r")
        has_predecessor[edges[:, 1]] = True
        edge_count += len(edges)
    source_relations = edge_count
    if "native_dependency_edges" in work:
        from scipy.sparse import coo_matrix
        relations = [np.load(graph_directory / name, mmap_mode="r") for name in (
            "dependencies.npy", "message_pairs.npy")]
        all_edges = np.concatenate(relations)
        graph = coo_matrix((np.ones(len(all_edges), dtype="i1"), (all_edges[:, 0], all_edges[:, 1])),
                           shape=(work["instructions"], work["instructions"])).tocsr()
        edge_count = graph.nnz
        if (edge_count != work["native_dependency_edges"] or
                source_relations-edge_count != work["shared_requires_arrival_predicates"]):
            raise ValueError("Native predicates do not represent all source relation kinds")
    checked = validate(read_json(run_directory / "dependency_profile.json"), work["instructions"],
                       edge_count, int(np.count_nonzero(~has_predecessor)))
    if "native_dependency_edges" in work:
        checked.update(source_relation_occurrences=source_relations,
                       shared_requires_arrival_predicates=source_relations-edge_count)
    write_json(run_directory / "dependency_profile_audit.json", checked)
    return checked
