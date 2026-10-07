"""Read complete existing source metadata and actual WoW exports; no simulation."""
import argparse
from collections import Counter
import json
from pathlib import Path
import platform
import sqlite3
import subprocess

import networkx as nx

from wafer_sim.adapters.spatial import network_from_wow
from wafer_sim.io import digest, read_json, write_json


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Source metadata and validation stay on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise SystemExit("Use a new absolute output directory on eex005")
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path("/home/wangziheng/wafer_simulator")
    extracted = root / "runs/local-source-events-20250324-merged-001"
    manifest = read_json(extracted / "EXTRACTED.json")
    source = extracted / "grouped_events.json"
    if digest(source) != manifest["artifacts_sha256"][source.name]:
        raise ValueError("Accepted grouped source changed")
    keys, types = Counter(), Counter()

    def visit(value):
        if isinstance(value, dict):
            keys.update(value.keys())
            if isinstance(value.get("event_type"), str):
                types[value["event_type"]] += 1
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(read_json(source))
    schemas = {}
    for filename, expected in manifest["sqlite_sha256"].items():
        p = Path(filename)
        if digest(p) != expected:
            raise ValueError("Source SQLite identity changed")
        with sqlite3.connect(p.as_uri() + "?mode=ro", uri=True) as conn:
            tables = sorted(row[0] for row in conn.execute("select name from sqlite_master where type='table'"))
        schemas[p.name] = dict(sha256=expected, table_count=len(tables),
            memory_tensor_allocation_tables=[n for n in tables if any(k in n.lower() for k in ("memory", "tensor", "alloc"))])
    networks = {}
    for placement in ("baseline", "ours_rotated"):
        p = root / "runs/llama16-model-boundary-M1-002" / placement / "network.json"
        export = read_json(p)
        network = network_from_wow(export)
        graph = nx.Graph(network.router_links)
        graph.add_nodes_from(router for _, router in network.endpoint_routers)
        assert graph.number_of_nodes() == export["resources"]["routers"]
        assert graph.number_of_edges() == export["resources"]["undirected_links"]
        assert len(network.endpoint_routers) == export["resources"]["compute_reticles"]
        assert nx.is_connected(graph)
        networks[placement] = dict(export_sha256=digest(p), resource_graph_provenance=network.provenance,
            endpoints=len(network.endpoint_routers), routers=graph.number_of_nodes(), links=graph.number_of_edges(),
            physically_connected=True, memory_capacities_inferred=False, timing_evaluated=False)
    interesting = ("tensor", "storage", "alloc", "buff", "data_size", "type_size", "flop", "shape", "workcount", "offset")
    result = dict(source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        source_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        python=platform.python_version(), networkx=nx.__version__,
        grouped_source_sha256=digest(source), extraction_manifest_sha256=digest(extracted / "EXTRACTED.json"),
        extraction_counts=manifest["counts"], event_type_counts=dict(sorted(types.items())),
        observed_semantic_field_counts={k: keys[k] for k in sorted(keys) if any(s in k.lower() for s in interesting)},
        sqlite_schema_checks=schemas, reused_wow_exports=networks,
        unresolved_inputs=["Versioned tensor/storage identity and alias/lifetime semantics",
            "Complete producer/consumer semantics outside captured communication",
            "Compute work amounts and target service calibration",
            "Target local-memory capacity and port service calibration"],
        scope="Presence of source fields and compatibility of resource graph import; not absence proof for every raw event",
        full_capture_spatial_execution_ready=False, new_simulations_launched=0)
    write_json(args.output / "SOURCE_SUPPORT.json", result)
    print(json.dumps(dict(output=str(args.output), networks=networks,
                         full_capture_spatial_execution_ready=False, new_simulations_launched=0)))


if __name__ == "__main__":
    main()
