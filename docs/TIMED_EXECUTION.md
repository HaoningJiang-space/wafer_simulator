# Target-resource timed execution

The current main task is an executable compute–memory–network model. Source
recovery remains frozen at its accepted result; missing Chakra communication
identities do not gate this backend. Mstatic remains a separate next model
comparison and is not required to validate the backend's service semantics.

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

Network transfers use injection, directed link and ejection byte servers on
the target's actual router graph. Routing selects a minimum-hop path with
lowest router ID on ties. The initial backend uses whole-message
store-and-forward: each hop receives the complete message before the next hop
is requested. Propagation latency does not occupy the link serializer. Shared
directed links serialize traffic; reverse directions are separate unless their
service IDs explicitly coincide. Memory reads/writes stay separate from network
service. Internal router queues are abstract queues; there is no flit, VC,
credit/backpressure or router-buffer-capacity model here.

This is a declared coarse network backend, not an emulation of the existing
BookSim backend, adaptive WoW routing, or a calibrated wafer. BookSim remains
the accepted full-capture network reference. A later integration can supply
finer transfer completion without changing the work/placement/lifetime contract.

Admission still atomically reserves output, staging and scratch storage across
regions. An admission blocked by capacity retries after a service completion;
it never busy-waits through idle cycles. If no event can release the blockage,
the result is incomplete with explicit shortages and no application time.
Data becomes available only after every producer phase, including destination
writes. Last-consumer release and retained outputs use the existing state.

## Responsibilities and evidence

| Layer | File | Responsibility |
|---|---|---|
| Hardware timing | `architecture/timing.py` | Rational rates, latency, directed links and endpoints |
| Binding | `adapters/timing.py` | Validate physical coverage, routes and phase demand services |
| Execution | `execution/timing.py` | Resource calendar, event completion, admission and lifecycle callbacks |
| Independent readback | `analysis/timing.py` | Rates, non-overlap, work/byte conservation, dependencies and capacity |
| Logical example | `workloads/timed_example.py` | Complete declared A/fanout-B/AllReduce/C work |
| Orchestration | `experiments/timed_example.py` and remote runner | Fixed input and separate rate interventions |

The runner reports operation ready/admission/finish times; every phase and
resource request; exact paths and bytes; resource queue waits; capacity waits;
and regional peak occupancy. Busy time and wait totals overlap across resources
and are not an additive application-time decomposition or a unique causal
bottleneck attribution. Controlled single-rate changes test their effect.

## First complete execution unit

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
