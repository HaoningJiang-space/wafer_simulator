"""Strict read-only acceptance of an already completed placement campaign."""
from pathlib import Path

from wafer_sim.io import digest, read_json
from wafer_sim.analysis.dependency_profile import validate as validate_profile

ARMS = ("baseline", "ours_rotated")


def accept(campaign):
    campaign = Path(campaign).resolve()
    for name in ("failures.json", "EXCLUDED.json"):
        if (campaign / name).exists():
            raise ValueError(f"Failed/excluded campaign: {campaign / name}")
    complete = read_json(campaign / "COMPLETE.json")
    if complete.get("all_arms_audited") is not True:
        raise ValueError("Both placements must pass the final campaign gate")
    config = read_json(campaign / "config.json")
    provenance = read_json(campaign / "provenance.json")
    registration = read_json(campaign / "registration.json")
    results = read_json(campaign / "results.json")
    rows = {row["placement"]: row for row in results}
    if len(results) != 2 or set(rows) != set(ARMS) or config["placements"] != list(ARMS):
        raise ValueError("Expected exactly the registered Baseline-Rotated pair")
    if len(complete["comparisons"]) != 2 or {row["placement"] for row in complete["comparisons"]} != set(ARMS):
        raise ValueError("Final completion marker has an incomplete pair")
    for row in complete["comparisons"]:
        if row["application_cycles"] != rows[row["placement"]]["application_cycles"]:
            raise ValueError("Final completion marker disagrees with results")
    if (config["truncate_input"] or config["remove_dependencies"] or config["thermal_feedback"] or
            config["network_frequency_hz"] != 1_000_000_000 or config["flit_bytes"] != 2000):
        raise ValueError("This report requires the registered complete fixed-state replay")
    if not registration["all_work_matched"]:
        raise ValueError("Work equality was not registered")
    work = registration["work"]
    if work["input_truncated"] or work["removed_dependencies"]:
        raise ValueError("Truncated/modified work cannot be attributed")
    if not (work["source_sha256"] == config["source_sha256"] == provenance["source_sha256"]):
        raise ValueError("Capture identities differ")
    loaded = {}
    for name in ARMS:
        path = campaign / name
        contract, audit, report, execution, resources, network = (
            read_json(path / file) for file in
            ("contract.json", "audit.json", "trace_report.json", "execution.json", "resources.json", "network.json"))
        if not (audit.get("passed") is True and report.get("complete") is True and
                execution.get("complete") is True and execution["return_code"] == 0 and
                not execution["timed_out"]):
            raise ValueError(f"Unaccepted placement: {name}")
        if not (contract["work"] == audit["work"] == rows[name]["work"] == work):
            raise ValueError(f"Full work mismatch: {name}")
        for field, key in (("instructions_expected", "instructions"), ("instructions_completed", "instructions"),
                           ("messages_completed", "messages"), ("flits_ejected", "flits")):
            if report[field] != work[key]:
                raise ValueError(f"Work conservation failed: {name}/{field}")
        if audit["all_operations_checked"] != work["instructions"]:
            raise ValueError("Independent audit did not check every operation")
        if not (report["application_cycles"] == audit["application_cycles"] == rows[name]["application_cycles"]):
            raise ValueError(f"Completion times disagree: {name}")
        if execution["binary_sha256"] != provenance["binary_sha256"]:
            raise ValueError("Architecture arms use different implementation identities")
        if resources != rows[name]["resources"] or resources != network["resources"]:
            raise ValueError(f"Resource records differ: {name}")
        if rows[name]["network_metrics"] != execution["network_metrics"]:
            raise ValueError(f"Network metrics differ: {name}")
        for field, value in audit.items():
            if field in rows[name] and rows[name][field] != value:
                raise ValueError(f"Saved result differs from independent audit: {name}/{field}")
        if digest(path / "trace_report.json") != rows[name]["report_sha256"]:
            raise ValueError(f"Native report identity changed: {name}")
        if Path(report["events_file"]).resolve() != path / "events.jsonl":
            raise ValueError("Native report refers to a different run's events")
        for file in ("checked_events.npy", "events.jsonl", "trace.json"):
            if not (path / file).is_file():
                raise ValueError(f"Required complete evidence absent: {name}/{file}")
        if config.get("dependency_profile"):
            profile = read_json(path / "dependency_profile_audit.json")
            if (profile.get("passed") is not True or profile["instructions"] != work["instructions"] or
                    profile["edges"] != work["original_dependencies"] + work["arrival_dependencies"]):
                raise ValueError(f"Dependency-profile audit missing/inconsistent: {name}")
            validate_profile(read_json(path / "dependency_profile.json"), work["instructions"],
                             profile["edges"], profile["initial_roots"])
        loaded[name] = dict(path=path, contract=contract, audit=audit, resources=resources,
                            network=network, execution=execution, result=rows[name])
    controls = ("compute_reticles", "network_frequency_hz", "link_bits_per_cycle", "buffer_flits_per_vc",
                "virtual_channels", "router_latency_cycles")
    for key in controls:
        if loaded[ARMS[0]]["resources"][key] != loaded[ARMS[1]]["resources"][key]:
            raise ValueError(f"Fixed hardware control differs: {key}")
    return dict(campaign=campaign, config=config, provenance=provenance, work=work, arms=loaded)
