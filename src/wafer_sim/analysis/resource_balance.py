"""Read-only checks of completion-policy controls and a one-axis resource study."""
from dataclasses import asdict
from statistics import mean

from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.transformer import place_block
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.analysis.collective_contention import summarize
from wafer_sim.execution.plan import ExecutionPolicy
from wafer_sim.io import read_json, digest, object_digest
from wafer_sim.workloads.transformer import build_block


def checked_run(root):
    complete = read_json(root / "COMPLETE.json")
    if (root / "FAILED.json").exists() or not complete["all_execution_and_reference_checks_passed"]:
        raise ValueError("A complete accepted run is required")
    for name, expected in complete["artifacts_sha256"].items():
        if digest(root / name) != expected:
            raise ValueError("Changed evidence: " + str(root / name))
    cases = {}
    for case in read_json(root / "SUMMARY.json")["cases"]:
        directory = root / case["name"]
        config = read_json(directory / "CONFIG.json")
        for arm in case["placements"]:
            path = directory / arm["placement"]
            cases[case["name"], arm["placement"]] = dict(case=case, config=config,
                record=read_json(path / "execution.json"), exported=read_json(path / "network.json"),
                chain=read_json(path / "critical_chain.json"), summary=arm)
    return cases, dict(path=str(root), complete_sha256=digest(root / "COMPLETE.json"),
                       source_commit=complete["source_commit"], hashes_checked=len(complete["artifacts_sha256"]))


def assert_same(a, b, label):
    if a != b:
        raise ValueError("Controlled identity differs: " + label)


def check_current(arm):
    record, config = arm["record"], arm["config"]
    block = build_block(**config["workload"]["block"])
    assert_same(object_digest(asdict(block.workload)), object_digest(record["logical_workload"]), "logical work")
    cm = dict(record["resource_contract"]["compute_memory_parameters"])
    # JSON sorts object keys, whereas target tuples retain the original declared
    # service order. Recover that order from the recorded target, not a new sort.
    units = record["target"]["compute"][0]["work_units"]
    assert_same(set(units), set(cm["compute_rates"]), "compute work units")
    cm["compute_rates"] = {unit: cm["compute_rates"][unit] for unit in units}
    for key in ("compute_rates", "region_capacity_bytes", "memory_bytes_per_cycle"):
        assert_same(cm[key], config["workload"][key], key)
    target, timing, contract = build_wow_target(arm["exported"], cm, config["experiment"]["flit_bytes"])
    placement = place_block(block, record["worker_endpoints"])
    for name, value in (("target", target), ("timing", timing), ("mapping", placement)):
        assert_same(object_digest(asdict(value)), object_digest(record[name]), name)
    assert_same(contract, record["resource_contract"], "resource contract")
    assert_same(record["execution_policy"], config["experiment"]["execution_policy"], "execution policy")
    binding = bind(block.workload, target, placement,
                   execution_policy=ExecutionPolicy(**record["execution_policy"]))
    for backend in ("booksim", "store_and_forward"):
        audit(binding, timing, record[backend])
    chain = critical_chain(binding, record["booksim"])
    assert_same(chain, arm["chain"], "observed critical chain")
    assert_same(record["booksim"]["application_cycles"], arm["summary"]["booksim_cycles"], "summary completion")
    return binding


def observable_equal(a, b):
    """All historic service and native message events, not only makespans."""
    for key in ("logical_workload", "mapping", "worker_endpoints", "target", "timing"):
        assert_same(a[key], b[key], key)
    for backend in ("booksim", "store_and_forward"):
        for key in ("application_cycles", "services", "phases", "resources", "storage"):
            assert_same(a[backend][key], b[backend][key], backend + "/" + key)
        old_ops = {k: {f: v for f, v in row.items() if f != "retired"}
                   for k, row in a[backend]["operations"].items()}
        new_ops = {k: {f: v for f, v in row.items() if f != "retired"}
                   for k, row in b[backend]["operations"].items()}
        assert_same(old_ops, new_ops, backend + "/operations")
    assert_same(a["booksim"]["network_messages"], b["booksim"]["network_messages"], "native messages")


def summarize_arm(arm):
    record, summary = arm["record"], arm["summary"]
    result = record["booksim"]
    traffic = summarize(arm["exported"], result["network_messages"])
    details = {}
    operations = {o["id"]: o for o in record["logical_workload"]["operations"]}
    for collective in record["collectives"]:
        op = collective["operation"]
        retired = result["operations"][op]["retired"]
        ranks = []
        for rank, data in zip(collective["participants"], collective["output_objects"]):
            consumers = {}
            for name, operation in operations.items():
                if data not in operation["inputs"]:
                    continue
                starts = [s["start"] for s in result["services"] if s["token"].startswith(name + "/phase/")]
                consumers[name] = dict(result["operations"][name], first_service_start=min(starts))
            ranks.append(dict(rank=rank, data=data, output_ready=result["output_ready"][data],
                              retired=retired, consumers=consumers))
        maximum = max(r["output_ready"] for r in ranks)
        details[op] = dict(ranks=ranks, tail_ranks=[r["rank"] for r in ranks if r["output_ready"] == maximum],
            output_ready_span=maximum-min(r["output_ready"] for r in ranks),
            consumers_admitted_before_retirement=sum(c["admitted"] < retired for r in ranks for c in r["consumers"].values()),
            consumers_started_before_retirement=sum(c["first_service_start"] < retired for r in ranks for c in r["consumers"].values()),
            consumers_retired_before_retirement=sum(c["retired"] < retired for r in ranks for c in r["consumers"].values()))
    chain = arm["chain"]
    row = dict(case=arm["case"]["name"], placement=record["placement"],
        memory_bytes_per_cycle=arm["config"]["workload"]["memory_bytes_per_cycle"],
        application_cycles=result["application_cycles"], coarse_cycles=summary["coarse_cycles"],
        critical_compute=chain["cycles"].get("compute", 0), critical_memory=chain["cycles"].get("memory", 0),
        critical_network=chain["cycles"].get("network", 0),
        mean_message_cycles=mean(m["finish"]-m["ready"] for m in result["network_messages"]),
        first_injection_wait=sum(m["first_inject"]-m["ready"] for m in result["network_messages"]),
        first_flit_router_excess=traffic["first_flit_router_excess_cycles"],
        peak_messages=summary["peak_outstanding_messages"],
        attention_output_span=details["attention_sum"]["output_ready_span"],
        attention_consumers_started_early=details["attention_sum"]["consumers_started_before_retirement"],
        attention_tail_ranks=details["attention_sum"]["tail_ranks"],
        ffn_tail_ranks=details["ffn_sum"]["tail_ranks"])
    return row, dict(collectives=details, critical_chain=chain, traffic=traffic)


def analyze(historical, global_run, local_run, balance_run):
    loaded = [checked_run(path) for path in (historical, global_run, local_run, balance_run)]
    old, global_cases, local_cases, balance_cases = [x[0] for x in loaded]
    assert_same(set(old), set(global_cases), "historical/global cases")
    assert_same(set(global_cases), set(local_cases), "global/local cases")
    rows, details, comparisons = [], {}, []
    for group, cases in (("global", global_cases), ("local", local_cases), ("balance", balance_cases)):
        for key, arm in cases.items():
            check_current(arm)
            row, detail = summarize_arm(arm)
            rows.append(dict(group=group, **row))
            details[group + "/" + "/".join(key)] = detail
    for key, control in global_cases.items():
        observable_equal(old[key]["record"], control["record"])
        local = local_cases[key]
        for field in ("logical_workload", "mapping", "worker_endpoints", "target", "timing"):
            assert_same(control["record"][field], local["record"][field], "completion policy control/" + field)
        comparisons.append(dict(case=key[0], placement=key[1],
            global_cycles=control["summary"]["booksim_cycles"], local_cycles=local["summary"]["booksim_cycles"],
            native_message_schedule_unchanged=control["record"]["booksim"]["network_messages"] ==
                                             local["record"]["booksim"]["network_messages"],
            historical_full_events_match=True))
    # A single parameter changes across bandwidth: compare complete input
    # configurations and local/network resources with that field removed.
    for key, arm in balance_cases.items():
        anchor = local_cases["tp8-row_major", key[1]]
        for field in ("logical_workload", "mapping", "worker_endpoints", "target", "execution_policy"):
            assert_same(anchor["record"][field], arm["record"][field], "balance/" + field)
        assert_same(anchor["exported"], arm["exported"], "balance/network geometry and parameters")
        for section in ("workload", "experiment"):
            a, b = dict(anchor["config"][section]), dict(arm["config"][section])
            if section == "workload":
                a.pop("memory_bytes_per_cycle"); b.pop("memory_bytes_per_cycle")
            assert_same(a, b, "balance/config/" + section)
        a, b = anchor["record"]["timing"], arm["record"]["timing"]
        ports = {m[p] for m in arm["record"]["target"]["memory"] for p in ("read_port", "write_port")}
        for field in ("links", "endpoints", "provenance"):
            assert_same(a[field], b[field], "balance/timing/" + field)
        assert_same(len(a["services"]), len(b["services"]), "balance/services")
        for x, y in zip(a["services"], b["services"]):
            x, y = dict(x), dict(y)
            if x["resource"] in ports:
                assert_same(y.pop("rate_numerator"), arm["config"]["workload"]["memory_bytes_per_cycle"], "port rate")
                x.pop("rate_numerator")
            assert_same(x, y, "balance/service parameters")
        if arm["config"]["workload"]["memory_bytes_per_cycle"] == 32:
            observable_equal(anchor["record"], arm["record"])
    return dict(rows=rows, completion_comparison=comparisons, runs=[x[1] for x in loaded],
                audited_arms=len(global_cases)+len(local_cases)+len(balance_cases),
                historical_controls_match=True, balance_single_axis_verified=True), details
