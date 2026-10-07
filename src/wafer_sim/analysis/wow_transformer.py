"""Read-only path, queue and operation comparison for the registered WoW pair."""
from pathlib import Path

from wafer_sim.io import read_json, digest


def analyze(directory):
    directory = Path(directory)
    complete = read_json(directory / "COMPLETE.json")
    if (directory / "FAILED.json").exists() or not complete["all_execution_and_reference_checks_passed"]:
        raise ValueError("A complete accepted pair is required")
    for name, expected in complete["artifacts_sha256"].items():
        if digest(directory / name) != expected:
            raise ValueError("Changed run artifact: " + name)
    config = read_json(directory / "CONFIG.json")["experiment"]
    records, arms, paths = [], [], []
    for placement in config["placements"]:
        record = read_json(directory / placement / "execution.json")
        exported = read_json(directory / placement / "network.json")
        result = record["booksim"]
        records.append(result)
        links = {tuple(sorted((link["src"], link["dst"]))): link
                 for link in exported["inputs"]["links"]}
        messages = result["network_messages"]
        active = peak = 0
        for _, change in sorted([(m["ready"], 1) for m in messages] +
                                [(m["finish"], -1) for m in messages]):
            active += change
            peak = max(peak, active)
        for message in messages:
            for flit in message["flits"]:
                route = flit["router_path"]
                propagation = sum(links[tuple(sorted((a, b)))]["latency"]
                                  for a, b in zip(route, route[1:]))
                paths.append(dict(placement=placement, token=message["token"], flit=flit["id"],
                    source=message["source"], destination=message["destination"],
                    routers=route, inter_router_links=len(route)-1,
                    configured_link_cycles=propagation,
                    configured_router_cycles=len(route)*exported["resources"]["router_latency_cycles"],
                    injection_wait=flit["injected"]-flit["generated"],
                    injection_to_ejection=flit["ejected"]-flit["injected"]))
        resources = result["resources"]
        arms.append(dict(placement=placement, application_cycles=result["application_cycles"],
            peak_outstanding_messages=peak,
            first_injection_wait_cycles=sum(m["first_inject"]-m["ready"] for m in messages),
            compute_queue_wait_cycles=sum(r["queue_wait_cycles"] for key, r in resources.items()
                                          if key.startswith("compute-")),
            memory_queue_wait_cycles=sum(r["queue_wait_cycles"] for key, r in resources.items()
                                         if key.startswith("memory-")),
            capacity_wait_cycles=sum(r["capacity_wait_cycles"] for r in result["operations"].values()),
            retained_data=result["storage"]["available_data"],
            critical_chain=read_json(directory / placement / "critical_chain.json")["cycles"]))
    if len(records) != 2 or set(records[0]["operations"]) != set(records[1]["operations"]):
        raise ValueError("Expected the same complete operation set in two placements")
    operations = []
    for operation, first in sorted(records[0]["operations"].items()):
        second = records[1]["operations"][operation]
        operations.append(dict(operation=operation, baseline_ready=first["ready"],
            baseline_finish=first["finish"], rotated_ready=second["ready"],
            rotated_finish=second["finish"], ready_delta=second["ready"]-first["ready"],
            finish_delta=second["finish"]-first["finish"],
            admitted_duration_delta=(second["finish"]-second["admitted"])-
                                    (first["finish"]-first["admitted"])))
    return dict(input_complete_sha256=digest(directory / "COMPLETE.json"),
                run_source_commit=complete["source_commit"], arms=arms,
                operations=operations, paths=paths,
                queue_scope="Summed request waits overlap and are not additive application time",
                path_scope="Actual flit paths and configured costs; no inferred router stall causes")
