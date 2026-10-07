# Target-resource timed execution

The executable compute–memory–network model is established. The current
research compares simulation abstractions, prediction error and measured cost.
Source recovery remains frozen at its accepted result; missing Chakra
communication identities do not gate this backend.

## Execution contract

`execute(binding, timing)` derives every phase completion from requested work
and explicit target service rates. It drives the existing `StorageState` phase
callbacks itself. A request of amount `W` at rate `p/q` units per cycle occupies
its resource for `ceil(W*q/p)` cycles. Its result is available after the optional
additional latency. Units, rates and latency are supplied, never inferred from
source durations. Missing services or inconsistent physical resources fail
before execution begins.

Compute and memory requests with the same resource ID share a nonpreemptive
FCFS server, even across work units or memory regions. Independent IDs may
overlap. Demands within one phase run in their declared sequence. Resources
are requested when the previous service completes, not reserved across a
whole future path. Completion ties use event submission order, and operation
admission uses stable topological order. These are explicit scheduling choices.

`execute(..., memory_quantum_bytes=Q)` optionally divides every memory request,
including ordinary operation accesses and DMA packet reads/writes, into bursts
of at most Q valid bytes. Each subsequent burst rejoins FCFS at the prior burst's
completion; it does not reserve future service. Per-burst rate rounding and
configured latency apply, and the original callback fires only after all bursts.
Compute and network service are unchanged. Q is independent of native flit size;
packet injection and credit release still require complete payload read/write.
The default `None` preserves request-atomic execution and accepted event records.
This is an explicit target-service policy, not a hardware-calibrated bus width.
See the [registered policy-isolation study](MEMORY_SERVICE_ISOLATION.md).

Explicit collective operations use the existing [collective action DAG](COLLECTIVE_TIMING.md).
All ready actions are submitted to this same calendar/network interface; phases
are not serialized solely because they belong to one collective. Ordinary
operations retain sequential phases. Global collective admission and final
output visibility remain governed by the shared storage state.

By default, network transfers use injection, directed link and ejection byte servers on
the target's actual router graph. Routing selects a minimum-hop path with
lowest router ID on ties. The initial backend uses whole-message
store-and-forward: each hop receives the complete message before the next hop
is requested. Propagation latency does not occupy the link serializer. Shared
directed links serialize traffic; reverse directions are separate unless their
service IDs explicitly coincide. Memory reads/writes stay separate from network
service. Internal router queues are abstract queues; there is no flit, VC,
credit/backpressure or router-buffer-capacity model here.

This default is a declared coarse network backend. The optional
`execute(binding, timing, network=client)` interface now uses a persistent
BookSim process for native flit, VC, credit and adaptive-routing behavior.
Compute/memory scheduling and storage semantics stay in the same executor;
message completion resumes destination memory writes. Neither backend
calibrates compute/SRAM parameters. See the [online contract and checked
placement experiment](TRANSFORMER_WOW_PROTOCOL.md), including the explicit
native-cycle to external-boundary conversion and equal-boundary event order.

The same interface accepts the optional `PacketPipeline` candidate. It reuses
the resource calendar for cross-hop packet pipelining under the pinned trace
configuration, with source-derived initiation periods and fixed coarse routes.
It retains FCFS output service but omits input arbitration, finite buffers,
credits and adaptive routing. Unsupported configurations are rejected by the
adapter. This is not the default backend. See its
[contract](PACKET_PIPELINE_PROTOCOL.md) and
[same-work accuracy/cost comparison](results/packet-pipeline-001/REVIEW.md).

The optional `MemoryBoundary` interface instead retains native BookSim and fuses
only exclusive source-read / transfer / destination-write chains. Chunk memory
requests share the original resource calendar. A TX slot is reserved before
read, native injection requires completed read service, and a bounded RX slot
is held until destination write completes. Only full-object commit completes
the original movement. Fixed TX/RX capacity is carved out of the original SRAM
for every comparison arm. Immediate-credit `pipeline` is a diagnostic model:
its measured RX overflow is an abstraction failure, not feasible extra storage.
See the [declared target](MEMORY_NETWORK_BOUNDARY_PROTOCOL.md) and
[checked results](results/memory-boundary-001/REVIEW.md). This changes endpoint
service, not internal router arbitration, and is not the default backend.

`cycle_limit` is a positive integral **inclusive** completion boundary for all
backends. Events exactly at the limit are drained; an execution requiring a
later boundary returns incomplete rather than exceeding the limit silently.

Admission still atomically reserves output, staging and scratch storage across
regions. An admission blocked by capacity retries after a service completion;
it never busy-waits through idle cycles. If no event can release the blockage,
the result is incomplete with explicit shortages and no application time.
Ordinary-operation data becomes available after all producer phases, including
destination writes. Explicit collectives publish each rank's final output
after its materialization completes; operation retirement still waits for all
actions. Last-consumer release and retained outputs use the existing state.

## Responsibilities and evidence

| Layer | File | Responsibility |
|---|---|---|
| Hardware timing | `architecture/timing.py` | Rational rates, latency, directed links and endpoints |
| Binding | `adapters/timing.py` | Validate physical coverage, routes and phase demand services |
| Execution | `execution/timing.py` | Resource calendar, event completion, admission and lifecycle callbacks |
| Independent readback | `analysis/timing.py` | Rates, non-overlap, work/byte conservation, dependencies and capacity |
| Live network bridge | `adapters/online_booksim.py`, `adapters/native/online_booksim.cpp` | Persistent accepted native kernel; dynamic request and receive completion |
| Native readback | `analysis/online_network.py` | Actual paths, all-flit conservation and completion boundaries |
| Logical example | `workloads/timed_example.py` | Complete declared A/fanout-B/AllReduce/C work |
| Transformer block | `workloads/transformer.py` | Complete shape-defined tensor-parallel forward work |
| Orchestration | `experiments/timed_example.py` and remote runner | Fixed input and separate rate interventions |

The runner reports operation ready/admission/finish times; every phase and
resource request; exact paths and bytes; resource queue waits; capacity waits;
and regional peak occupancy. Busy time and wait totals overlap across resources
and are not an additive application-time decomposition or a unique causal
bottleneck attribution. Controlled single-rate changes test their effect.

The review preceding the Transformer extension tightened the independent audit
to check FCFS service order, chronological request submission, minimum-hop
lexicographic route selection, capacity-wait accounting and terminal-state
consistency. The previously accepted 113-cycle unit's full event record remains
identical. See the [review and extension evidence](results/transformer-execution-001/REVIEW.md).

## First complete execution unit

This original generic multi-output unit is retained as an exact event-regression
fixture. The newer explicit collective-action tests validate actual gather/SUM/
broadcast materialization and concurrency; they supersede interpreting the
generic multi-output service sequence as that collective algorithm.

`configs/timed_execution_example.json` defines three compute/memory regions,
four routers and shared directed links. Every tensor has four float32 elements.
A reads its seed and performs 64 MACs. Two B tasks consume A's tensor remotely
and each perform 128 MACs. Two-rank SUM AllReduce gathers their results at the
declared root, performs four adds and writes a 16-byte result at each rank.
Both destination writes finish before the two C tasks begin their 32 MACs each.
This conservative global completion policy is explicit. The AllReduce is lowered
to ordinary data dependencies and resource phases; it does not require any old
source communicator, allocator or tensor descriptor.

This is a complete analytical execution unit, independently specified rather
than sampled or truncated from Llama. Its rates and capacities are test-model
definitions, not calibrated WoW reticle properties. The expected base schedule
is independently hand-derived: A finishes at 12 cycles; B0/B1 at 52/56;
AllReduce at 105; C0/C1 at 113. Separate factor-of-two rate changes keep the
entire logical work, placement, link latencies and other rates unchanged.

Run builds and tests only on eex005. After semantic tests at the committed
revision, `scripts/run_timed_example_remote.py OUTPUT TEST_RECEIPT` emits the
complete execution and independent audit for all registered cases. Full Llama,
mapping sweeps, thermal, PDN and new capture recovery are outside this delivery.

The subsequent [Transformer extension](TRANSFORMER_EXECUTION.md) reuses the same
calendar, storage model and audit, selected by `--workload transformer` in this
runner. Its separate configuration includes all arithmetic service rates and
explicit worker/data placement.
