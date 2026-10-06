"""Independent input/completion/dependency accounting and delay decomposition."""
from collections import defaultdict
import statistics

from wafer_sim.workloads.dag import validate, summary, compute_only_bound


def audit(workload, report, flit_bytes=2000):
    order, _ = validate(workload)
    expected = summary(workload, flit_bytes)
    if not report.get("complete"):
        raise ValueError("Incomplete execution cannot be compared")
    events = {e["id"]: e for e in report["events"]}
    if len(events) != len(report["events"]) or set(events) != set(order):
        raise ValueError("Missing, duplicate, or extra completed instructions")
    for field, key in (("instructions_completed", "instructions"),
                       ("instructions_expected", "instructions"),
                       ("messages_completed", "messages"), ("flits_ejected", "flits")):
        if report[field] != expected[key]:
            raise ValueError(f"Work conservation failed: {field}")
    by_id = {n["id"]: n for n in workload["nodes"]}
    message_times, injection_wait, transfer_times = [], [], []
    paths = {}
    finishes = {}
    compute_by_rank = defaultdict(list)
    for i in order:
        n, event = by_id[i], events[i]
        ready = max([n["release_cycle"]] + [events[d]["finish_cycle"] for d in n["deps"]])
        finish = event["finish_cycle"]
        start = event.get("start_cycle", ready)
        if not event["completed"] or event["flits_remaining"] != 0:
            raise ValueError("Incomplete node or outstanding payload")
        if event["ready_cycle"] != ready or finish < ready:
            raise ValueError("Dependency/release timing violation")
        if n["kind"] != "message":
            if finish != start + n["duration_cycles"]:
                raise ValueError("Compute duration was lost or changed")
            if n["kind"] == "compute":
                compute_by_rank[n["rank"]].append((start, finish))
        else:
            generated, injected = event["generated_cycle"], event["first_inject_cycle"]
            last_injected, first_received = event["last_inject_cycle"], event["first_eject_cycle"]
            if not ready <= generated <= injected <= last_injected <= finish:
                raise ValueError("Message injection timestamps are inconsistent")
            if not injected <= first_received <= finish:
                raise ValueError("Message receive timestamps are inconsistent")
            flits = (n["bytes"] + flit_bytes - 1) // flit_bytes
            if last_injected - injected < flits - 1:
                raise ValueError("One-flit-per-cycle injection capacity violated")
            message_times.append(finish-ready)
            injection_wait.append(injected-ready)
            transfer_times.append(finish-injected)
        # Follow the latest-finished prerequisite. Sum mutually exclusive
        # durations on this observed chain, never sum all rank waiting times.
        parent = max(n["deps"], key=lambda d: (events[d]["finish_cycle"], d), default=None)
        parts = paths[parent].copy() if parent is not None and events[parent]["finish_cycle"] >= n["release_cycle"] else dict(compute=0, message=0, release=n["release_cycle"], dispatch=0)
        parts["dispatch"] += start-ready
        parts["message" if n["kind"] == "message" else "compute"] += finish-start
        paths[i] = parts
        finishes[i] = finish
    if workload.get("provenance", {}).get("compute_model") == "one explicitly ordered lane per rank":
        for spans in compute_by_rank.values():
            spans.sort()
            if any(a[1] > b[0] for a, b in zip(spans, spans[1:])):
                raise ValueError("Overlapping work on a single compute lane")
    terminal = max(order, key=lambda i: (finishes[i], i))
    makespan = finishes[terminal]
    if makespan != report["application_cycles"]:
        raise ValueError("Application end does not include all terminal operations")
    critical = paths[terminal]
    if sum(critical.values()) != makespan:
        raise ValueError("Critical-chain accounting does not close")
    mean = lambda xs: statistics.mean(xs) if xs else 0.0
    return dict(passed=True, **expected, application_cycles=makespan,
                compute_only_bound_cycles=compute_only_bound(workload),
                exposed_network_cycles=makespan-compute_only_bound(workload),
                mean_message_ready_to_complete=mean(message_times),
                mean_message_injection_wait=mean(injection_wait),
                mean_message_first_inject_to_complete=mean(transfer_times),
                critical_chain=critical,
                iteration_completion_cycles=[max(finishes[i] for i in sinks)
                                             for sinks in workload.get("iteration_sinks", [])])
