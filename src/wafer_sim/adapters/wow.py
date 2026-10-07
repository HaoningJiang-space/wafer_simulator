"""Use the pinned author's placement construction and RapidChiplet exporters."""
import contextlib
import importlib
import os
from pathlib import Path
import subprocess
import sys

from wafer_sim.io import write_json

UPSTREAM_COMMIT = "9470042fb2d8b5368556e46cc75ac818dbf31522"


@contextlib.contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_upstream(path):
    path = Path(path).resolve()
    actual = subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    if actual != UPSTREAM_COMMIT:
        raise ValueError(f"Upstream pin mismatch: {actual}")
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    # Author modules use flat absolute imports. Keep their names in this adapter,
    # and reject mixing two checkouts in one process.
    if "config" in sys.modules and Path(sys.modules["config"].__file__).parent != path:
        raise RuntimeError("An incompatible flat upstream config module is loaded")
    return importlib.import_module("run_experiment"), importlib.import_module("export_to_rapidchiplet")


def export_placement(upstream, output, method, diameter=200, utilization="rectangular"):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    run, export = load_upstream(upstream)
    import config as cfg
    import analyze_topology as topology
    from rapidchiplet import booksim_wrapper, run_rapidchiplet

    design = dict(integration_level="logic_and_interconnect", wafer_diameter=diameter,
                  wafer_utilization=utilization, method=method,
                  routing_function="simple_cycle_breaking_set",
                  selection_function="adaptive", traffic="trace-llama7B")
    # The author trace-mode flag selects one endpoint per compute reticle.
    # No Llama data are loaded: the actual trace path is supplied by our runner.
    system = run.construct_system_for_single_design(design, cfg.parameters)
    topology.add_global_reticle_ids(system)
    topology.add_neighbor_information(system)
    inputs = dict(chiplets=export.export_chiplets_to_rapidchiplet(system))
    inputs["placement"] = export.export_placement_to_rapidchiplet(system)
    inputs["links"] = export.export_links_to_rapidchiplet(system)
    inputs["booksim_config"] = export.export_booksim_config(system, {})
    inputs["routing_table"] = {"type": "default"}
    inputs["verbose"] = False
    if any(link["latency"] < 1 for link in inputs["links"]):
        raise ValueError("Unexpected nonpositive physical link latency")
    edge_pairs = [(min(l["src"], l["dst"]), max(l["src"], l["dst"])) for l in inputs["links"]]
    if len(edge_pairs) != len(set(edge_pairs)):
        raise ValueError("Parallel links would be collapsed by the author exporter")
    for directory in ("rc_topologies", "rc_configs", "rc_stats", "rc_xy_info"):
        (output / "rapidchiplet/booksim2/src" / directory).mkdir(parents=True, exist_ok=True)
    with working_directory(output):
        latencies = run_rapidchiplet.compute_link_latencies(inputs)
        booksim_wrapper.export_booksim_topology(inputs, latencies, "network")
    endpoints = []
    for router, placed in enumerate(inputs["placement"]["chiplets"]):
        chiplet = inputs["chiplets"][placed["name"]]
        for _ in range(chiplet["unit_count"]):
            endpoints.append(dict(node=len(endpoints), router=router,
                                  position=placed["position"], layer=placed["layer"]))
    resources = dict(compute_reticles=len(endpoints), routers=len(inputs["placement"]["chiplets"]),
                     undirected_links=len(inputs["links"]),
                     aggregate_directed_link_bits_per_cycle=sum(2*l["bandwidth"] for l in inputs["links"]),
                     physical_cost_matched=False,
                     network_frequency_hz=cfg.network_frequency_hz,
                     link_bits_per_cycle=int(cfg.link_bandwidth_bit_per_sec / cfg.network_frequency_hz),
                     buffer_flits_per_vc=cfg.buffer_size_per_vc_flits,
                     virtual_channels=cfg.number_of_virtual_channels,
                     router_latency_cycles=cfg.router_latency_cycles)
    write_json(output / "network.json", dict(upstream_commit=UPSTREAM_COMMIT, design=design,
                                             inputs=inputs, endpoints=endpoints, resources=resources))
    return inputs, endpoints, resources


def rank_mapping(endpoints, ranks, policy="row_major", seed=1234):
    import random
    ordered = sorted(endpoints, key=lambda e: (e["layer"], e["position"]["y"], e["position"]["x"]))
    if len(ordered) < ranks:
        raise ValueError("Not enough compute reticles for the same workload")
    mapping = [e["node"] for e in ordered[:ranks]]
    if policy == "nearest_root":
        root = ordered[0]
        if len({e["layer"] for e in ordered}) != 1:
            raise ValueError("Planar nearest-root mapping requires one compute layer")
        ordered = sorted(ordered, key=lambda e: (
            (e["position"]["x"]-root["position"]["x"])**2 +
            (e["position"]["y"]-root["position"]["y"])**2,
            e["position"]["y"], e["position"]["x"], e["node"]))
        mapping = [e["node"] for e in ordered[:ranks]]
    elif policy == "permuted":
        random.Random(seed).shuffle(mapping)
    elif policy != "row_major":
        raise ValueError("Unknown mapping policy")
    return mapping
