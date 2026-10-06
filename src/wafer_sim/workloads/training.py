"""Explicit, synthetic synchronous data-parallel training schedule.

Each iteration has a local forward/backward phase, a dependency-complete ring
reduce-scatter/all-gather, and a local optimizer phase. Compute durations are
controlled inputs, NOT measurements or a Llama performance model.
"""
from wafer_sim.workloads.dag import validate


def make_training(ranks=20, iterations=3, compute_cycles=2000,
                  chunk_bytes=64000, optimizer_cycles=100):
    for value in (ranks, iterations, chunk_bytes):
        if type(value) is not int or value <= 0:
            raise ValueError("Positive integral workload dimensions required")
    if ranks < 2:
        raise ValueError("Ring training requires at least two ranks")
    nodes = []

    def add(kind, rank, deps, label, duration=0, size=0, dst=-1):
        i = len(nodes)
        nodes.append(dict(id=i, kind=kind, rank=rank, dst=dst,
                          deps=sorted(set(deps)), label=label,
                          duration_cycles=duration, bytes=size, release_cycle=0))
        return i

    previous = [[] for _ in range(ranks)]
    iteration_sinks = []
    for iteration in range(iterations):
        ready = [add("compute", r, previous[r], f"iter{iteration}/forward_backward/r{r}",
                     duration=compute_cycles) for r in range(ranks)]
        for phase in ("reduce_scatter", "all_gather"):
            for step in range(ranks - 1):
                sends = [add("message", r, [ready[r]],
                             f"iter{iteration}/{phase}/step{step}/r{r}",
                             size=chunk_bytes, dst=(r + 1) % ranks)
                         for r in range(ranks)]
                # Require both outgoing completion and incoming availability:
                # a conservative one-chunk workspace, identically in all arms.
                ready = [add("join", r, [sends[r], sends[(r - 1) % ranks]],
                             f"iter{iteration}/{phase}/step{step}/done/r{r}")
                         for r in range(ranks)]
        sinks = [add("compute", r, [ready[r]], f"iter{iteration}/optimizer/r{r}",
                     duration=optimizer_cycles) for r in range(ranks)]
        iteration_sinks.append(sinks)
        previous = [[i] for i in sinks]
    workload = dict(schema_version=1, name="synthetic_ring_dp_training", ranks=ranks,
                    nodes=nodes, iteration_sinks=iteration_sinks,
                    provenance=dict(kind="generated_application_schedule",
                                    calibrated_compute=False, original_llama_trace=False,
                                    compute_model="one explicitly ordered lane per rank",
                                    reduction_arithmetic="included in fixed phase budget; not separately timed"),
                    parameters=dict(iterations=iterations, compute_cycles=compute_cycles,
                                    chunk_bytes=chunk_bytes, optimizer_cycles=optimizer_cycles))
    validate(workload)
    return workload
