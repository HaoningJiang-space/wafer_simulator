"""Independent all-operation readback of the real GOAL execution."""
import json
from pathlib import Path

from wafer_sim.io import read_json, write_json


def audit(graph_directory, run_directory):
    import numpy as np
    from scipy.sparse import coo_matrix
    graph_directory, run_directory = Path(graph_directory), Path(run_directory)
    report = read_json(run_directory / "trace_report.json")
    contract = read_json(run_directory / "contract.json")
    expected = contract["work"]
    if not report["complete"]:
        raise ValueError("An incomplete capture cannot enter a placement comparison")
    for name, key in [("instructions_expected", "instructions"), ("instructions_completed", "instructions"),
                      ("messages_completed", "messages"), ("flits_ejected", "flits")]:
        if report[name] != expected[key]:
            raise ValueError(f"Work conservation failed: {name}")
    ops = np.load(graph_directory / "operations.npy", mmap_mode="r")
    deps = np.load(graph_directory / "dependencies.npy", mmap_mode="r")
    pairs = np.load(graph_directory / "message_pairs.npy", mmap_mode="r")
    n = len(ops)
    fields = ("ready_cycle", "start_cycle", "finish_cycle", "cpu_predecessor",
              "generated_cycle", "first_inject_cycle", "last_inject_cycle", "first_eject_cycle")
    events = np.lib.format.open_memmap(run_directory / "checked_events.npy", mode="w+",
                                       dtype=[(f, "i8") for f in fields], shape=(n,))
    count = 0
    with Path(report["events_file"]).open() as stream:
        for i, line in enumerate(stream):
            event = json.loads(line)
            if i >= n or event["id"] != i or not event["completed"] or event["flits_remaining"]:
                raise ValueError("Missing, duplicate, reordered or incomplete event")
            events[i] = tuple(event.get(f, -1) for f in fields)
            count += 1
    if count != n:
        raise ValueError("Missing completion events")
    ready, start, finish = (events[f] for f in fields[:3])
    required = np.zeros(n, dtype="i8")
    np.maximum.at(required, deps[:, 1], finish[deps[:, 0]])
    np.maximum.at(required, pairs[:, 1], finish[pairs[:, 0]])
    if np.any(required != ready) or np.any(start < ready) or np.any(finish < start):
        raise ValueError("Dependency/release timing violation")
    message = ops["kind"] == 1
    calc = ops["kind"] == 0
    duration = np.where(calc, ops["amount"], 0)
    if np.any((finish-start)[~message] != duration[~message]):
        raise ValueError("Published local work duration was changed")
    cpu = ops["rank"].astype("i8")*expected["cpu_stride"]+ops["cpu"]
    predecessors = events["cpu_predecessor"]
    waiting = start > ready
    if np.any(predecessors[waiting] < 0) or np.any(predecessors[waiting] >= n):
        raise ValueError("Unexplained CPU wait")
    prev = predecessors[waiting]
    if (np.any(cpu[prev] != cpu[waiting]) or np.any(~calc[prev]) or
            np.any(finish[prev] != start[waiting])):
        raise ValueError("CPU blocking predecessor does not explain start time")
    active = np.flatnonzero(calc & (duration > 0))
    order = active[np.lexsort((start[active], cpu[active]))]
    same_lane = cpu[order[1:]] == cpu[order[:-1]]
    if np.any(same_lane & (start[order[1:]] < finish[order[:-1]])):
        raise ValueError("Overlapping local work on a serialized lane")
    generated, first, last, received = (events[f][message] for f in fields[4:])
    if (np.any(generated < start[message]) or np.any(first < generated) or np.any(last < first) or
            np.any(last > finish[message]) or np.any(received < first) or np.any(received > finish[message])):
        raise ValueError("Inconsistent message timestamps")
    flits = (ops["amount"][message]+expected["flit_bytes"]-1)//expected["flit_bytes"]
    if np.any(last-first < flits-1):
        raise ValueError("Injection exceeded one flit per cycle")
    makespan = int(finish.max())
    if makespan != report["application_cycles"]:
        raise ValueError("Application completion excludes a terminal operation")
    # Recover an actual critical chain, including observed CPU contention edges.
    edges = np.concatenate((deps, pairs))
    parents = coo_matrix((np.ones(len(edges), dtype="i1"), (edges[:, 1], edges[:, 0])), shape=(n, n)).tocsr()
    current = int(finish.argmax())
    compute = network = chain_nodes = 0
    while True:
        chain_nodes += 1
        if chain_nodes > n:
            raise ValueError("Cycle in observed critical chain")
        service = int(finish[current]-start[current])
        if message[current]:
            network += service
        else:
            compute += service
        candidates = parents.indices[parents.indptr[current]:parents.indptr[current+1]].tolist()
        if predecessors[current] >= 0:
            candidates.append(int(predecessors[current]))
        if not candidates:
            if start[current] != 0:
                raise ValueError("Unexplained nonzero root start")
            break
        parent = max(candidates, key=lambda i: (int(finish[i]), i))
        if finish[parent] != start[current]:
            raise ValueError("Critical-chain timing does not close")
        current = parent
    if compute+network != makespan:
        raise ValueError("Critical-chain decomposition does not equal full completion")
    result = dict(passed=True, work=expected, application_cycles=makespan,
                  application_seconds_at_1GHz=makespan/1e9,
                  critical_local_work_cycles=compute, critical_message_cycles=network,
                  critical_chain_nodes=chain_nodes,
                  mean_message_ready_to_complete=float((finish[message]-ready[message]).mean()),
                  mean_cpu_wait_before_send=float((start[message]-ready[message]).mean()),
                  mean_message_injection_wait=float((first-start[message]).mean()),
                  mean_first_inject_to_complete=float((finish[message]-first).mean()),
                  total_local_work_cycles=int(duration.sum()), all_operations_checked=count,
                  tagged_last_flit_arrived_early=report["tagged_last_flit_arrived_early"])
    events.flush()
    write_json(run_directory / "audit.json", result)
    return result
