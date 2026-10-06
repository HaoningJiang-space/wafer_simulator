"""Materialize one source-supported M1 and prove unchanged complete M0 lowering."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.adapters.goal_booksim import lower
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.local_transfers import materialize
from wafer_sim.workloads.goal import ingest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full M0/M1 preparation runs on eex005")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Commit preparation code first")
    root = Path("/home/wangziheng/wafer_simulator")
    original = root / "downloads/atlahs/llama16/llama.goal"
    graph = original.parent / "graph-001"
    output = args.output.resolve()
    transformed = materialize(original, graph, root / "runs/local-source-regeneration-20250324-merged-001",
        root / "runs/local-source-events-20250324-merged-001", root / "runs/local-stage-provenance-001", output)
    campaign = root / "runs/llama16-full-006-csr-frontier"
    if not read_json(campaign / "COMPLETE.json")["all_arms_audited"]:
        raise ValueError("Frozen M0 pair is incomplete")
    reference = read_json(campaign / "provenance.json")
    binary = root / "build/booksim-csr-frontier/rapidchiplet/booksim2/src/booksim"
    if digest(binary) != reference["binary_sha256"]:
        raise ValueError("Frozen native 006 binary changed")
    checks = {}
    for arm in ("baseline", "ours_rotated"):
        saved = read_json(campaign / arm / "contract.json")
        destination = output / "m0_lowering" / arm / "trace.json"
        contract = lower(graph, destination, [row["node"] for row in saved["endpoint_mapping"]])
        if contract != saved:
            raise ValueError(f"Complete M0 lowered contract differs: {arm}")
        checks[arm] = dict(trace_sha256=contract["trace_sha256"], contract_equal=True,
                           instructions=contract["work"]["instructions"])
    write_json(output / "M0_IDENTITY.json", dict(passed=True, checks=checks,
        binary_sha256=digest(binary), source_goal_sha256=digest(original),
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        scope="Both complete lowered traces and contracts unchanged; native binary is exactly frozen 006",
        new_m0_simulations=0))
    subprocess.run([sys.executable, "scripts/audit_goal.py", str(output / "M1.goal"),
                    str(output / "input_audit.json")], check=True)
    checked = ingest(output / "M1.goal", output / "input_audit.json", output / "graph")
    if not checked["dependency_gate_passed"]:
        raise ValueError("Complete M1 graph failed dependency audit")
    original_checked = read_json(graph / "graph_audit.json")
    if checked["operations"] != original_checked["operations"] or checked["input_dependencies"] != original_checked["input_dependencies"]:
        raise ValueError("M1 lost or added original operations/dependencies")
    if digest(output / "graph/dependencies.npy") != digest(graph / "dependencies.npy"):
        raise ValueError("M1 original dependency array differs")
    config = read_json("configs/llama16_fixed_state.json")
    old_config = read_json(campaign / "config.json")
    for key in ("placements", "active_endpoints", "mapping", "seed", "flit_bytes", "network_frequency_hz",
                "diameter_mm", "utilization", "truncate_input", "remove_dependencies", "thermal_feedback"):
        if config[key] != old_config[key]:
            raise ValueError(f"Fixed control differs from 006: {key}")
    config.update(workload="ATLAHS_complete_capture_M1_explicit_local_transfers",
        source_goal=transformed["source_goal"], source_sha256=transformed["source_sha256"],
        graph_directory=str(output / "graph"), local_transfer_model="explicit_wow",
        transformation_sha256=digest(output / "TRANSFORMATION.json"))
    write_json(output / "config.json", config)
    write_json(output / "PREPARED.json", dict(passed=True, source_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip(), binary=str(binary), binary_sha256=digest(binary),
        config=str(output / "config.json"), m0_identity_sha256=digest(output / "M0_IDENTITY.json"),
        graph_audit_sha256=digest(output / "graph/graph_audit.json"), config_sha256=digest(output / "config.json"),
        transformation_sha256=digest(output / "TRANSFORMATION.json"), new_simulations_launched=0))
    print("Complete M0 identity and M1 input preparation passed", flush=True)


if __name__ == "__main__":
    main()
