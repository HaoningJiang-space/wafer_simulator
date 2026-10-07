# Spatial Workload Execution for Wafer-Scale Systems

Research question: **how should execution of the same AI work change with the
target wafer's topology, placement and resource structure, and how does that
change application completion time?**

The initial target is WoW Logic-on-Interconnect, comparing Baseline and Rotated.
The method should explain when network improvements reach the application,
which work or resources prevent that, and when a simpler model already gives
the same design decision. A ranking reversal is not required.

## Derive the model from spatial resources

Omelet is a reference for organizing evidence: modeling gap, targeted model,
then consequences for architectural decisions. It does not determine what
wafer execution must model. That follows from the target's distributed compute,
memory and finite communication resources.

For an `n x n` array with constant compute per tile, fixed-pitch local mesh
links, fixed link capacity and a fixed number of network layers, total compute
scales as `n^2` while a straight bisection has capacity proportional to `n`.
This is a conditional cut argument, not a universal law for every 3D wafer or
a proof that any workload is bandwidth-bound. The useful constraint is the
residual traffic that actually crosses each target resource cut after mapping
and reuse. Derive that cut's capacity from the actual resource graph.

Geometry determines feasible connectivity and link timing in the reused WoW
model. Locality then depends on both producer/consumer placement and data
residency. Moving a fixed-size tensor farther away does **not** by itself change
its logical bytes: distinguish logical payload, per-link bytes, byte-hops and
bytes crossing a selected cut. Residency, replication, reuse or collective
lowering can change which physical transfers are required.

Memory is a spatial resource from the start, not a later physical add-on.
Capacity is checked per region and time, and read/write service competes for
local ports. Application progress follows data availability, task dependencies
and shared-resource service, with overlap; compute and network totals cannot
generally be added to obtain makespan. These phenomena also occur beyond wafers;
the research must demonstrate why the selected wafer structures expose an
important modeling gap rather than claim exclusivity.

## Logical work, execution policy and target resources

The intended interface is
`Execute(logical_work, mapping, execution_policy, target_resources, initial_state)`.

Write logical work as `W = (V_compute, V_data, E_semantic)` and the target as
`H = (C, M, N, G)`: compute, memory, network and geometry. Mapping has separate
task and data placements, `phi_compute` and `phi_data`. Execution is
`E = Execute(W, H, phi, pi, S0)`. Policy `pi` and initial state `S0` remain
explicit; geometry alone cannot determine scheduling, allocation or routing.

| Input | Contains | Must not silently inherit |
| --- | --- | --- |
| Logical work | Operation identity/work amount; data objects, sizes and production/consumption dependencies; collective semantics | Source host-local/remote classifications, waiting or transport times |
| Mapping and execution policy | Worker/data placement, collective algorithm and lowering, scheduling/routing policy | Source stream serialization presented as necessary semantic dependence |
| Target resources | Compute/copy/memory service, modeled storage capacity, endpoints/network, resource ownership and release | Source machine timing presented as a target hardware parameter |
| Initial state | Required data residency and resource state | Unspecified warm/cold start or missing inputs |

Target binding determines locality, visited resources and contention.
Execution generates message readiness and completion from task progress and
resource service. A changed architecture need not change the tensor program
or logical byte requirements; it can change paths, contention and the realized
critical chain. Collective lowering and scheduling remain explicit policies
so a topology comparison does not silently become an algorithm comparison.

This is a research contract, not a claim that the current code implements all
these inputs. Source-supported transfer bytes alone do not reconstruct tensor
identity, liveness or mathematical semantics.

## Minimum spatial execution contract to specify next

| Object | Required information | Event or constraint |
| --- | --- | --- |
| Compute operation | Operation/work description, inputs, outputs, scratch demand, target service model | Inputs available, output/scratch storage reserved, required service resources available |
| Data object | Stable identity/version, size, producer, consumers, resident copies, release rule | Capacity charged at each live copy; availability only after its production or arrival |
| Memory region | Capacity, read/write service rates, port sharing, initial contents | Live allocations plus reservations never exceed that region's capacity |
| Transfer | Required object or supported slice, source copy, target location, bytes, dependency | Reads, transport and destination writes use defined resources; availability after defined completion |
| Network resource | Feasible links, bandwidth/latency, routing policy, buffers/credits | Shared service and backpressure follow the chosen network abstraction |

The first contract must decide when destination space is reserved, whether
operations stream or require complete inputs, when consumers release each
copy, and whether memory/network stages pipeline or serialize. Define these
before implementing them. If full-input availability and full-output reservation
are chosen initially, label that policy and keep it identical across arms.
Do not charge the same transfer in a fixed interval and again through memory
or the network. An infeasible allocation must block or be reported infeasible;
it cannot silently use free spill memory or an invented eviction policy.

These fields cannot be recovered from a duration alone. `calc = 556 ms` does
not identify FLOPs, tensor sizes or memory traffic. Missing semantic identity
and capacity/service parameters are explicit input gaps. Retain opaque stages
as conditional baselines until supported replacements exist; do not claim
data-placement feasibility or source independence for that baseline.

The first locality question is whether, at fixed logical work and stated
policies, separate compute and data placement changes physical movement and
application progress enough to affect the design judgment. Report per-region
capacity/port usage, logical and physical movement separately, critical tasks
and completion time. This is stronger than rerouting the same fixed messages.

## Present evidence and its limits

The [source analysis](LOCAL_STAGE_PROVENANCE.md) recovers 1,337,280 transfer pairs
frozen as source-local calc costs. The [target binding](TARGET_RESOURCE_MAPPING.md)
assigns their endpoints to distinct compute reticles. The accepted
[M0/M1 pair](results/model-boundary-001/REVIEW.md) changes the predicted
Baseline–Rotated gap from 2.365264 ms to 13.118157 ms. This demonstrates a source
boundary sensitivity under fixed remaining local costs, with identical native
implementation and retained complete logical work.

M1 is **partial communication retargeting**, not a source-machine-independent
workload model. Measured intervals, reduction/copy costs, CPU-lane serialization
and source collective organization remain. The largest intervals have source
provenance but lack target compute calibration. Data objects and application
storage lifetimes are not explicit.

Source analysis prepares the choice of abstraction; it is not the research
objective. Recovering an author's existing grouping/transfer functionality
is baseline construction, not by itself a new simulator contribution.

## Next research steps, in dependency order

1. **Define and source the minimum spatial contract above.** Distinguish work,
   data objects and semantic dependencies from source scheduling and intervals.
   Preserve unresolved stages explicitly. Do not remove an edge merely because
   it appears to encode scheduling; a complete independence claim needs evidence
   for those replacements.
2. **Use the existing transfer case to test abstraction sufficiency.** Compare static target costs
   with dynamic service using the same work, issue, completion and lane-occupancy
   semantics. Separate stale cost parameters from interactions static costs
   cannot capture. The [protocol](MODEL_BOUNDARY_PROTOCOL.md) lists open choices;
   no such new experiment is registered.
3. **Study compute/data locality, then topology–workload interaction.** Use common messages, readiness,
   resource waits and actual chains. Examine controlled local-cost or mapping
   sensitivity after the mechanism is identified. If static service suffices
   for the intended decision, retain it.
4. **Establish reuse and validity.** Extend one axis at a time to a second complete
   workload with different compute/communication structure, then placement and
   resource budgets. Validate component service and execution semantics against
   independent evidence at the fidelity claimed. Model disagreement alone is
   not an accuracy reference.

The eventual paper must connect a demonstrated modeling gap, a target-resource
method and an architecture conclusion with validity limits. Logical/physical
separation is the framing, not an automatic novelty claim. Compare existing
workload reorganization and execution-model capabilities before claiming a new
method.

Basic finite capacity and bandwidth constraints belong in the spatial model.
Detailed physical feasibility is a later question: whether ports, links, bonding,
wiring, power and cooling can deliver those assumed resources. Thermal, PDN,
new schedulers and new simulator acceleration are outside the current work.
Original-design and equal-budget comparisons remain distinct.

The current delivery closes the source table, target-resource description and
M0/M1 protocol. It records the previously authorized completed run and launches
no new placement scan or model implementation.
