"""Register (never execute) one diagnostic pair from accepted analysis results."""
from pathlib import Path

from wafer_sim.adapters.wow import rank_mapping
from wafer_sim.io import digest, read_json, write_json


def register_mapping_check(info, summary, output):
    # Descriptive triage thresholds, not statistical significance or a new metric.
    local_shares = {name: chain["critical_local_work_cycles"] / chain["application_cycles"]
                    for name, chain in summary["chains"].items()}
    matches = (abs(summary["application_time_reduction_percent"]) < 1 and
               summary["packet_latency_reduction_percent"] > 0 and min(local_shares.values()) > .95 and
               info["config"].get("mapping") == "row_major")
    if not matches:
        decision = dict(status="needs_result_review", registered_groups=0,
                        reason="Result differs from the preregistered small-application/local-work-dominated pattern")
        write_json(Path(output) / "next_experiment_decision.json", decision)
        return decision
    project = Path(__file__).resolve().parents[3]
    config = read_json(project / "configs/llama16_fixed_state.json")
    for key, value in info["config"].items():
        if key != "implementation_patch_files" and config.get(key) != value:
            raise ValueError(f"Active controls changed before next-pair registration: {key}")
    config["mapping"] = "permuted"
    maps = {}
    for name, arm in info["arms"].items():
        endpoints = arm["network"]["endpoints"]
        actual = rank_mapping(endpoints, config["active_endpoints"], "permuted")
        explicit = rank_mapping(endpoints, config["active_endpoints"], "permuted", seed=1234)
        original = rank_mapping(endpoints, config["active_endpoints"], "row_major")
        if actual != explicit or sorted(actual) != sorted(original) or actual == original:
            raise ValueError("Existing mapping consumer does not implement the registered permutation")
        maps[name] = actual
    remote_root = Path(info["campaign"]).parent.parent
    binary = remote_root / "build/booksim/rapidchiplet/booksim2/src/booksim"
    preserved = read_json(remote_root / "runs/fastest-consolidation-001/acceptance.json")
    if preserved.get("passed") is not True or digest(binary) != preserved["binary_sha256"]:
        raise ValueError("Next study must use the preserved selected implementation")
    output = Path(output)
    config_path = output / "next_experiment_config.json"
    write_json(config_path, config)
    registration = dict(status="registered_not_executed", registered_groups=1, arms=config["placements"],
        question="Does packet-latency improvement with small application benefit persist under one fixed endpoint permutation?",
        observation=dict(application_time_reduction_percent=summary["application_time_reduction_percent"],
                         packet_latency_reduction_percent=summary["packet_latency_reduction_percent"],
                         local_work_share_of_selected_chains=local_shares),
        purpose="Check whether the observed message/CPU critical-chain pattern depends on the original endpoint assignment",
        changed_control=dict(mapping=dict(previous="row_major", next="permuted")),
        mapping_seed=1234, mapping_seed_consumer="Existing rank_mapping default; verified equal to explicit seed=1234",
        network_seed=config["seed"], expected_endpoint_mapping=maps,
        fixed_work=info["work"], full_input_required=True, thermal_feedback=False,
        implementation=dict(binary=str(binary), binary_sha256=digest(binary),
                            source_identity_acceptance_sha256=digest(remote_root / "runs/fastest-consolidation-001/acceptance.json")),
        configuration=str(config_path), configuration_sha256=digest(config_path),
        execution_gate="Require FINAL_ACCEPTED.json for the current 006 report before any new simulation",
        acceptance="Both full arms audited; actual mapping equals registration; original work and per-placement hardware costs unchanged",
        interpretation_limit="One additional paired mapping diagnoses sensitivity; it cannot establish universal placement ranking",
        command=[str(remote_root / ".venv/bin/python"), "-m", "wafer_sim.cli", "--config", str(config_path),
                 "--upstream", str(remote_root / "upstream/nw-design-for-wsi"), "--binary", str(binary),
                 "--output", str(remote_root / "runs/llama16-mapping-permuted-1234-001")])
    write_json(output / "next_experiment.json", registration)
    return dict(status=registration["status"], registered_groups=1, path=str(output / "next_experiment.json"))
