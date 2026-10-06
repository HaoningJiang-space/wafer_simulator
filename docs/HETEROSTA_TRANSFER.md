# Heterogeneous STA methods: transfer to this simulator

The source assessment below now has a first CPU implementation of flattened
dependency storage and an ordered ready frontier. This is not a GPU backend or
a speedup claim. Existing complete CPU runs keep their original workload and
controls. See [implementation and acceptance](CSR_FRONTIER.md).

## What the sources actually establish

[HeteroSTA, ASPDAC 2026](https://arxiv.org/html/2511.11660v1), Section III,
describes a central flattened CSR netlist database, direct array inputs/outputs
and CPU/GPU interoperability across stages. Its public
[API](https://heterosta.pkueda.org.cn/documentation/api-reference) separates
delay updates from level-wise arrival propagation and accepts GPU result arrays.
The verified distribution consists of a shared library, headers and integration
examples; the [release repository](https://github.com/HeteroSTA/releases) is a
binary release repository. This does not establish availability of its CUDA
kernel source for reuse in BookSim.

The preceding [TCAD 2023 paper](https://guozz.cn/publication/gputimertcad-23/gputimertcad-23.pdf)
gives the more detailed algorithms: frontier-based levelization, task-based
CPU/GPU dependencies, flattened storage and parallelism across timing corners.
Its frontier algorithm decreases successor indegrees atomically and admits a
successor when its last predecessor is processed. It also evaluates when small
updates favor CPU execution.

[IncreGPUSTA, ICCAD 2025](https://guozz.cn/publication/incregpustaiccad-25/incregpustaiccad-25.pdf)
uses base/auxiliary CSR structures and incremental levelization for structural
netlist updates. That is relevant if a simulator changes graph structure across
design iterations. A flit moving or a queue filling does not itself change the
physical network topology; rebuilding CSR every simulation cycle would be a
misapplication of this technique.

## The precise analogy and its limit

For a fixed dependency DAG with fixed operation duration p(v), completion obeys

    F(v) = p(v) + max(release(v), max(F(u) for u in predecessors(v))).

This resembles fixed-arc arrival propagation. It becomes suitable for batched
graph processing when the predecessor relation captures every constraint.

BookSim must additionally determine resource service order and availability.
Two independently ready sends can compete for one output. Returning a credit
can unblock a previously stalled VC. CPU-lane reservation order can change
subsequent injection. These constraints are not present in the original GOAL
dependency graph and cannot be recovered by assigning each message a fixed
latency. Even with fixed network topology, the relevant resource precedence is
resolved during execution.

Once a particular schedule is known, its computation, service and buffer-release
events can be represented by a richer causal event graph. Propagating through
that graph is useful for replay/audit/critical-chain analysis; creating the
correct graph is still part of the simulation problem. Expanding every flit at
every cycle in advance would also undermine the intended reduction in work.

## Transfer choices

| Technique | Candidate application | Additional simulator requirement |
| --- | --- | --- |
| Flattened CSR + array state | Immutable network and workload edges; separate queue, credit, progress and CPU state arrays | Preserve edge/callback order where the reference policy observes it |
| Frontier propagation | Batched dependency completions and ready-event discovery | Ready for dependencies does not mean granted a shared execution or network resource |
| Level-wise parallel execution | Independent routers/ports within an explicitly defined cycle phase | Preserve input, arbitration, update and credit-visibility boundaries |
| Incremental updates | Maintain sets of active routers/VCs; re-evaluate affected resources | Account for future pipeline/credit arrivals and clocks, including currently empty queues |
| Multi-corner parallelism | Batch independent mappings or parameter points | Each scenario has independent state; different topologies and schedules can diverge |
| Shared heterogeneous API | Keep high-volume state on the device between phases | Include transfer, launch, synchronization and event readback in end-to-end timing |

The rows describe proposed transfers, not claims that HeteroSTA already solves
network contention. Similarly, a proposed active-work CPU/GPU selection policy
needs measured crossover costs; switching every cycle can lose the benefit
through state migration.

## What to inspect before implementing a GPU backend

The current placements have 124 and 100 routers, 16 active endpoints and one VC.
eex005 was observed to have two RTX 5090 GPUs with about 32 GiB each. Router
count alone is not a parallelism measurement: the useful dimensions include
active ports/VCs, independent ready operations and independent scenarios.
The 151,889,580 flits in the complete capture measure total work, not concurrent
work available to one kernel.

An appropriate next measurement is the distribution of active work per cycle
phase, plus host/device synchronization frequency under the actual completion
rules. Only then choose a CPU/GPU boundary. Record such instrumentation in its
own candidate build and full-capture run; do not turn a short prefix into a
performance experiment.

Initial implementation boundaries should be:

1. Freeze the CPU reference and complete its all-operation audit.
2. Introduce a common flattened state/transition contract with a CPU backend.
3. Verify unchanged request ordering, arbitration ties, credit visibility,
   flit retirement order, integer cycle timestamps and application events.
4. Implement the corresponding device phases, keeping resource conflicts
   resolved deterministically. A ready frontier is not an unordered GPU queue
   when its processing order changes CPU-lane reservations.
5. Compare the same complete captures and independent cases end to end. Report
   latency for a single simulation separately from throughput across scenarios.

For the current two-placement study, static preprocessing and completed-trace
analysis are easier GPU candidates, but their acceleration need not reduce the
dominant network execution time. Accelerating the network core requires a data
layout and execution redesign, not simply replacing malloc/free with a GPU call.
