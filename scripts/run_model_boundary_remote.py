"""Run the one registered complete M1 pair, then read both models' results."""
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.model_boundary import compare
from wafer_sim.experiments.runner import run_campaign
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.local_transfers import audit_target_graph
from wafer_sim.adapters.goal_booksim import lower

def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("M0/M1 runs on eex005")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Commit registered study code before launch")
    study = read_json("configs/llama16_model_boundary.json")
    prepared = Path(study["prepared_inputs"])
    record = read_json(prepared / "PREPARED.json")
    if not record["passed"] or digest(record["config"]) != record["config_sha256"]:
        raise SystemExit("Complete input preparation missing or changed")
    if digest(record["binary"]) != study["binary_sha256"] or record["binary_sha256"] != study["binary_sha256"]:
        raise SystemExit("Native binary differs from frozen 006")
    for name, key in (("M0_IDENTITY.json", "m0_identity_sha256"),
                      ("TRANSFORMATION.json", "transformation_sha256"),
                      ("graph/graph_audit.json", "graph_audit_sha256")):
        if digest(prepared / name) != record[key]:
            raise SystemExit(f"Prepared evidence changed: {name}")
    m0 = Path(study["m0_campaign"])
    original_graph = read_json(m0 / "config.json")["graph_directory"]
    audit_target_graph(original_graph, prepared / "graph", study["source_provenance"])
    # Recheck both complete M0 serializations with this adapter revision. No M0
    # simulation is launched, and all failed/full earlier inputs remain intact.
    recheck = prepared / ("m0_recheck_" + Path(study["m1_campaign"]).name)
    proofs = {}
    for arm in study["new_placements"]:
        print(f"Rechecking unchanged complete M0 lowering: {arm}", flush=True)
        expected = read_json(m0 / arm / "contract.json")
        current = lower(original_graph, recheck / arm / "trace.json",
                        [row["node"] for row in expected["endpoint_mapping"]])
        if current != expected:
            raise ValueError(f"Current adapter changed complete M0: {arm}")
        proofs[arm] = current["trace_sha256"]
    write_json(recheck / "M0_IDENTITY.json", dict(passed=True, trace_sha256=proofs,
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    write_json(prepared / "LAUNCH_VALIDATION.json", dict(passed=True,
        study_sha256=digest("configs/llama16_model_boundary.json"),
        transformation_audit_sha256=digest(prepared / "TRANSFORMATION_AUDIT.json"),
        current_m0_identity_sha256=digest(recheck / "M0_IDENTITY.json"),
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()))
    run_campaign(record["config"], "/home/wangziheng/wafer_simulator/upstream/nw-design-for-wsi",
                 record["binary"], study["m1_campaign"], reference_campaign=m0)
    compare(m0, study["m1_campaign"], prepared, study["source_provenance"], study["analysis_output"])


if __name__ == "__main__":
    main()
