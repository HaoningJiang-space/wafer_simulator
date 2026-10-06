"""Accepted four-cell comparison and common-message observations."""
import csv
from pathlib import Path
import shutil

import numpy as np

from wafer_sim.analysis.campaign_acceptance import accept, ARMS
from wafer_sim.analysis.critical_chain import message_timings
from wafer_sim.analysis.placement_attribution import analyze
from wafer_sim.analysis.local_stages import classify
from wafer_sim.io import digest, read_json, write_json


def compare(m0, m1, prepared, provenance, output):
    m0, m1, prepared, provenance, output = map(Path, (m0, m1, prepared, provenance, output))
    a, b = accept(m0), accept(m1)
    if not read_json(prepared / "M0_IDENTITY.json")["passed"] or not read_json(prepared / "TRANSFORMATION_AUDIT.json")["passed"]:
        raise ValueError("Model boundary preparation gate missing")
    if a["provenance"]["binary_sha256"] != b["provenance"]["binary_sha256"]:
        raise ValueError("M0/M1 native binaries differ")
    for key in ("mapping", "seed", "flit_bytes", "network_frequency_hz", "diameter_mm", "utilization"):
        if a["config"][key] != b["config"][key]:
            raise ValueError(f"Unregistered cross-model control change: {key}")
    for arm in ARMS:
        if (a["arms"][arm]["network"] != b["arms"][arm]["network"] or
                a["arms"][arm]["contract"]["endpoint_mapping"] != b["arms"][arm]["contract"]["endpoint_mapping"]):
            raise ValueError(f"Cross-model network or endpoint assignment differs: {arm}")
    output.mkdir(parents=True, exist_ok=False)
    analyze(m1, output / "M1")
    classification = output / "M1_local_stages"
    classification.mkdir()
    shutil.copy2(provenance / "SOURCE_CORRESPONDENCE.json", classification)
    regenerated = Path(read_json(provenance / "SOURCE_CORRESPONDENCE.json")["reconstruction_directory"])
    classify(a["config"]["graph_directory"], regenerated, output / "M1", classification)
    original_ops = np.load(Path(a["config"]["graph_directory"]) / "operations.npy", mmap_mode="r")
    common_ids = np.flatnonzero(original_ops["kind"] == 1)
    rows, common = [], {}
    for model, accepted in (("M0", a), ("M1", b)):
        for arm in ARMS:
            info = accepted["arms"][arm]
            audit = info["audit"]
            rows.append(dict(model=model, placement=arm, application_cycles=audit["application_cycles"],
                application_seconds=audit["application_cycles"] / 1e9,
                mean_packet_cycles=info["execution"]["network_metrics"]["Packet latency average"],
                mean_message_ready_to_complete=audit["mean_message_ready_to_complete"],
                critical_local_cycles=audit["critical_local_work_cycles"], critical_message_cycles=audit["critical_message_cycles"]))
            events = np.load(info["path"] / "checked_events.npy", mmap_mode="r")
            times = message_timings(events, common_ids)
            common[f"{model}/{arm}"] = dict(messages=len(common_ids), **{
                name: float(times[name].mean()) for name in (
                    "cpu_wait", "injection_wait", "first_inject_to_complete", "ready_to_complete")})
    effects = {}
    for model, accepted in (("M0", a), ("M1", b)):
        x, y = (accepted["arms"][arm]["audit"]["application_cycles"] for arm in ARMS)
        effects[model] = dict(baseline_minus_rotated_cycles=x-y, speedup=x/y, reduction_percent=100*(x-y)/x)
    with (output / "model_comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    result = dict(passed=True, model_effects=effects, rows=rows, common_interhost_messages=common,
        delta_m1_minus_delta_m0_cycles=effects["M1"]["baseline_minus_rotated_cycles"]-effects["M0"]["baseline_minus_rotated_cycles"],
        limitation="Conditional replay with unchanged source intervals and reduction/copy; expanded message population makes across-model all-message means incomparable",
        input_sha256={str(p.resolve()): digest(p) for p in (
            prepared / "M0_IDENTITY.json", prepared / "TRANSFORMATION_AUDIT.json",
            m0 / "COMPLETE.json", m1 / "COMPLETE.json", output / "M1/ANALYZED.json")})
    write_json(output / "MODEL_COMPARISON.json", result)
    lines = ["# M0/M1 placement comparison", "", "Both full placement pairs passed completion audits. The native binary and per-placement network/mapping are identical across models.", "",
             "| Model | Baseline (s) | Rotated (s) | Baseline minus Rotated (ms) | Placement speedup |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for model in ("M0", "M1"):
        values = [row["application_seconds"] for row in rows if row["model"] == model]
        effect = effects[model]
        lines.append(f"| {model} | {values[0]:.9f} | {values[1]:.9f} | {effect['baseline_minus_rotated_cycles']/1e6:.6f} | {effect['speedup']:.9f} |")
    lines += ["", "The comparison changes only source-verified local transfers. Both original endpoint costs are replaced by target-network service; remaining local costs and every original dependency are preserved.", "",
              "See M1/attribution.md for both actual critical chains and message phases; M1_local_stages/LOCAL_STAGES.json classifies the retained local stages. MODEL_COMPARISON.json additionally compares the same original inter-host messages across models. All-message means span different populations after expansion.", "",
              "This is not calibrated native WoW training time, thermal evidence, matched physical cost, or a universal placement ranking. Message records do not identify internal router/port/VC causes."]
    (output / "REPORT.md").write_text("\n".join(lines)+"\n")
    write_json(output / "COMPLETE.json", dict(passed=True, result_sha256=digest(output / "MODEL_COMPARISON.json"),
        report_sha256=digest(output / "REPORT.md"), artifacts_sha256={str(p.relative_to(output)): digest(p)
        for p in output.rglob("*") if p.is_file()}))
    return result
