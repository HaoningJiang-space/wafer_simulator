"""Whole-input topology inspection; no execution, workload truncation or timing model."""
from pathlib import Path

from wafer_sim.io import digest, read_json


def inspect(graph_directory):
    import numpy as np
    graph_directory = Path(graph_directory)
    gate = read_json(graph_directory / "graph_audit.json")
    if not gate["dependency_gate_passed"] or gate["truncated"] or gate["removed_dependencies"]:
        raise ValueError("An audited complete graph is required")
    operations = np.load(graph_directory / "operations.npy", mmap_mode="r")
    count = len(operations)
    fanout = np.zeros(count, dtype=np.int64)
    has_predecessor = np.zeros(count, dtype=bool)
    edges = 0
    hashes = {"operations.npy": digest(graph_directory / "operations.npy")}
    for name in ("dependencies.npy", "message_pairs.npy"):
        array = np.load(graph_directory / name, mmap_mode="r")
        if array.ndim != 2 or array.shape[1] != 2 or (len(array) and (array.min() < 0 or array.max() >= count)):
            raise ValueError(f"Invalid complete graph edges: {name}")
        fanout += np.bincount(array[:, 0], minlength=count)
        has_predecessor[array[:, 1]] = True
        edges += len(array)
        hashes[name] = digest(graph_directory / name)
    if count != gate["operations"] or edges != gate["input_dependencies"] + gate["matched_messages"]:
        raise ValueError("Graph counts differ from the complete-input audit")
    widths, frequencies = np.unique(fanout, return_counts=True)
    return dict(complete_input=True, instructions=count, edges=edges,
                initial_roots=int(np.count_nonzero(~has_predecessor)),
                maximum_successors=int(fanout.max()) if count else 0,
                successors_per_instruction={str(int(w)): int(f) for w, f in zip(widths, frequencies)},
                source_sha256=gate["source_sha256"], graph_file_sha256=hashes,
                scope="Static fanout bounds readiness from one completion; not concurrent work or execution time")
