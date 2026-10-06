import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.adapters import booksim, wow
from wafer_sim.analysis.audit import audit
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.dag import lower_to_booksim, summary
from wafer_sim.workloads.training import make_training


def run_campaign(config_path, upstream, binary, output):
    config = read_json(config_path)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "config.json", config)
    provenance = dict(host=platform.node(), python=platform.python_version(),
                      upstream_commit=wow.UPSTREAM_COMMIT, binary_sha256=digest(binary),
                      config_sha256=digest(config_path),
                      source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                      source_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()))
    write_json(output / "provenance.json", provenance)
    rows = []
    networks = {}
    for placement in config["placements"]:
        networks[placement] = wow.export_placement(upstream, output / "networks" / placement,
                                                  placement, config["diameter_mm"], config["utilization"])
    # Count equality is checked before simulation, not silently repaired by
    # changing ranks, batch sizes, or the application per placement.
    counts = {resources["compute_reticles"] for _, _, resources in networks.values()}
    if len(counts) != 1 or min(counts) < config["ranks"]:
        raise ValueError("This controlled campaign requires equal compute-reticle counts")
    for case in config["workloads"]:
        workload = make_training(ranks=config["ranks"], **case["parameters"])
        workload_path = output / "workloads" / (case["name"] + ".json")
        write_json(workload_path, workload)
        identity = summary(workload)
        for mapping_policy in config["mappings"]:
            for seed in config["seeds"]:
                for placement, (inputs, endpoints, resources) in networks.items():
                    run_dir = output / "cases" / case["name"] / mapping_policy / str(seed) / placement
                    run_dir.mkdir(parents=True)
                    import shutil
                    shutil.copytree(output / "networks" / placement / "rapidchiplet", run_dir / "rapidchiplet")
                    mapping = wow.rank_mapping(endpoints, config["ranks"], mapping_policy, config["mapping_seed"])
                    trace = lower_to_booksim(workload, mapping)
                    write_json(run_dir / "trace.json", trace)
                    write_json(run_dir / "contract.json", dict(work=identity, mapping=mapping, resources=resources,
                                                               workload_sha256=digest(workload_path)))
                    native_config = booksim.prepare_config(inputs, run_dir, run_dir / "trace.json", seed,
                                                          config["timeout_seconds"])
                    execution = booksim.run(binary, native_config, run_dir, config["timeout_seconds"])
                    checked = audit(workload, read_json(run_dir / "trace_report.json"))
                    write_json(run_dir / "audit.json", checked)
                    row = dict(workload=case["name"], mapping=mapping_policy, seed=seed, placement=placement,
                               application_cycles=checked["application_cycles"],
                               compute_only_bound_cycles=checked["compute_only_bound_cycles"],
                               exposed_network_cycles=checked["exposed_network_cycles"],
                               mean_message_cycles=checked["mean_message_ready_to_complete"],
                               mean_injection_wait_cycles=checked["mean_message_injection_wait"],
                               mean_packet_cycles=execution["network_metrics"].get("Packet latency average"),
                               mean_hops=execution["network_metrics"].get("Hops average"),
                               wall_seconds=execution["wall_seconds"],
                               critical_compute_cycles=checked["critical_chain"]["compute"],
                               critical_message_cycles=checked["critical_chain"]["message"],
                               **identity)
                    rows.append(row)
                    write_json(output / "progress.json", rows)
                    print(f"{case['name']} {mapping_policy} seed={seed} {placement}: "
                          f"{checked['application_cycles']} cycles; audit passed", flush=True)
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / "results.json", rows)
    from wafer_sim.analysis.comparison import compare
    compare(rows, output)
    return rows
