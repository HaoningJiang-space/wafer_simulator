"""Registered complete-capture experiment; no synthetic or prefix fallback."""
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import multiprocessing
from pathlib import Path
import platform
import subprocess

from wafer_sim.adapters import booksim, wow
from wafer_sim.adapters.goal_booksim import lower
from wafer_sim.analysis.goal_completion import audit
from wafer_sim.io import digest, read_json, write_json


def _execute(placement, binary, native_config, run_directory, graph_directory, timeout):
    record = booksim.run(binary, native_config, run_directory, timeout)
    checked = audit(graph_directory, run_directory)
    resources = read_json(Path(run_directory) / "resources.json")
    return dict(placement=placement, **checked, network_metrics=record["network_metrics"],
                wall_seconds=record["wall_seconds"], resources=resources,
                report_sha256=digest(Path(run_directory) / "trace_report.json"))


def run_campaign(config_path, upstream, binary, output):
    if platform.node().split(".")[0] != "eex005":
        raise RuntimeError("Run the complete experiment on eex005")
    config = read_json(config_path)
    if config["truncate_input"] or config["remove_dependencies"] or config["thermal_feedback"]:
        raise ValueError("This campaign requires complete input at fixed running state")
    if config["network_frequency_hz"] != 1000000000 or config["flit_bytes"] != 2000:
        raise ValueError("No implicit rescaling of the published nanosecond workload")
    if digest(config["source_goal"]) != config["source_sha256"]:
        raise ValueError("Downloaded workload identity changed")
    graph_audit = read_json(Path(config["graph_directory"]) / "graph_audit.json")
    if graph_audit["source_sha256"] != config["source_sha256"] or not graph_audit["dependency_gate_passed"]:
        raise ValueError("Full graph gate missing or belongs to another input")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "config.json", config)
    provenance = dict(host=platform.node(), python=platform.python_version(),
                      upstream_commit=wow.UPSTREAM_COMMIT, binary_sha256=digest(binary),
                      patch_sha256=digest("patches/booksim-completion.patch"),
                      config_sha256=digest(config_path), source_sha256=config["source_sha256"],
                      source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                      source_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()))
    if provenance["source_dirty"]:
        raise ValueError("Commit the experiment implementation before the formal run")
    write_json(output / "provenance.json", provenance)
    networks, jobs = {}, []
    for placement in config["placements"]:
        directory = output / placement
        networks[placement] = wow.export_placement(upstream, directory, placement,
                                                   config["diameter_mm"], config["utilization"])
    counts = {resources["compute_reticles"] for _, _, resources in networks.values()}
    if len(counts) != 1 or min(counts) < config["active_endpoints"]:
        raise ValueError("Unequal compute capacity across placement arms")
    identity = None
    for placement, (inputs, endpoints, resources) in networks.items():
        directory = output / placement
        if resources["network_frequency_hz"] != config["network_frequency_hz"]:
            raise ValueError("Network frequency differs from registered control")
        mapping = wow.rank_mapping(endpoints, config["active_endpoints"], config["mapping"])
        print(f"Lowering ALL operations for {placement}", flush=True)
        contract = lower(config["graph_directory"], directory / "trace.json", mapping, config["flit_bytes"])
        if identity is not None and identity != contract["work"]:
            raise ValueError("Work differs across placement arms")
        identity = contract["work"]
        write_json(directory / "resources.json", resources)
        inputs["booksim_config"]["trace_events_file"] = str(directory / "events.jsonl")
        native = booksim.prepare_config(inputs, directory, directory / "trace.json", config["seed"],
                                         config["timeout_seconds"])
        jobs.append((placement, str(Path(binary).resolve()), str(native), str(directory),
                     config["graph_directory"], config["timeout_seconds"]))
    write_json(output / "registration.json", dict(work=identity, arm_names=config["placements"],
                all_work_matched=True, physical_cost_matched=False, status="registered_before_execution"))
    print("Full-input equality gate passed; launching registered placement arms", flush=True)
    rows, failures = [], []
    with ProcessPoolExecutor(max_workers=config["parallel_placements"],
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = {pool.submit(_execute, *job): job[0] for job in jobs}
        for future in as_completed(futures):
            placement = futures[future]
            try:
                row = future.result()
                rows.append(row)
                write_json(output / "progress.json", rows)
                print(f"{placement}: ALL operations audited; {row['application_cycles']} cycles", flush=True)
            except Exception as exc:
                failures.append(dict(placement=placement, error=str(exc)))
                write_json(output / "failures.json", failures)
    if failures or len(rows) != len(jobs):
        raise RuntimeError("Incomplete/failed arm: no valid placement conclusion")
    rows.sort(key=lambda row: config["placements"].index(row["placement"]))
    write_json(output / "results.json", rows)
    baseline = rows[0]
    flat = [dict(placement=row["placement"], application_cycles=row["application_cycles"],
                 speedup_vs_baseline=baseline["application_cycles"]/row["application_cycles"],
                 critical_local_work_cycles=row["critical_local_work_cycles"],
                 critical_message_cycles=row["critical_message_cycles"],
                 mean_message_ready_to_complete=row["mean_message_ready_to_complete"],
                 mean_injection_wait=row["mean_message_injection_wait"],
                 mean_packet_cycles=row["network_metrics"].get("Packet latency average"),
                 mean_hops=row["network_metrics"].get("Hops average"),
                 wall_seconds=row["wall_seconds"]) for row in rows]
    with (output / "summary.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(flat[0]))
        writer.writeheader()
        writer.writerows(flat)
    explanation = ["# Complete ATLAHS capture: fixed-state WoW comparison", "",
                   "Every original operation and dependency was retained. Local `calc` work includes",
                   "opaque intra-host transfers; this is a conditional replay, not native wafer timing.", ""]
    for row, compact in zip(rows, flat):
        explanation.append(f"- {row['placement']}: {row['application_cycles']} cycles; "
                           f"{compact['speedup_vs_baseline']:.6f}x baseline speed. "
                           f"Critical chain = {row['critical_local_work_cycles']} local-work cycles + "
                           f"{row['critical_message_cycles']} message-service cycles.")
    explanation += ["", "Average packet latency and hop count are network metrics. Application time follows",
                    "the checked dependency/resource critical chain; averages alone do not determine it.",
                    "Topology resource counts differ and are recorded per arm. One seed and mapping",
                    "establish this paired case only; they do not establish a general placement ranking."]
    (output / "comparison.md").write_text("\n".join(explanation)+"\n")
    write_json(output / "COMPLETE.json", dict(all_arms_audited=True, comparisons=flat))
    return rows
