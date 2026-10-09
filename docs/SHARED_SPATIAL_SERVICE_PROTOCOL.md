# D1: one time-aware fluid sharing hypothesis

Register against `dc18ed1`. Run tests, components and complete work on hn072.
Freeze machine/work/placement/resources, storage/admission/execution, native
binary, U0/U1/D0/S and accepted evidence. New analysis dispatch may recognize
D1; old model events must reproduce. No parameter/mapping search or native
router, buffer, VC or credit intervention is part of this study.

Question: can shared spatial demand, compressed to active flows and capacities,
restore the registered A/B judgment without native flit execution?

## One fixed candidate

D1 routes from machine topology using deterministic minimum-hop lexicographic
paths. It uses no S application routing or traffic records. Messages enter
online at their own DAG readiness and every DRAM, C2C and I/O message uses the
**same state and resource namespace**. D1 never launches a native process.

Round bytes to `ceil(bytes/64)` packet-equivalents. Reuse the D0 component law:
two cycles per packet plus fixed access/router/physical-link latency. Validate
the rule against all 1,700 accepted D0 component conditions, then independently
check C2C and I/O singleton messages. Unsupported machine-service assumptions
must fail these checks; full application results cannot calibrate the rule.

Resources are physical directed links and injection/ejection endpoints at
unchanged nominal machine capacity, plus each router's directed output at
the independently observed 1/2 packet-equivalent/cycle service. The latter is
a modeled effective packet service, not a change to installed link bandwidth.
End-to-end rate is the equal-weight max-min fair allocation under all resources
on each active route. Progressive filling uses exact rational arithmetic.

All path resources are occupied concurrently from message readiness until
fluid serialization completes. Release occurs at the first integer boundary
that covers remaining packet work; fixed physical propagation then precedes
message delivery. Fractions unused in the last cycle are discarded. Rates
change when flows join or release, and the DAG observes only full-message
delivery. Router-output identity allows distinct outputs and reverse directed
links to operate independently. No per-flit events, finite queues/buffers,
VCs, credits, per-router pipeline or adaptive routing state is retained.

This is an explicit idealization of immediate path feedback. It does not
model the time a first flit needs to reach each sharing point, transient
wavefronts or finite buffer/credit feedback. Test this candidate once; do not
respond to a failed layout budget by tuning its rate or silently adding state.

## Component checks before applications

On the unchanged 6×6 physical graph, register 38 input conditions:

- 20 singletons: HB-local DRAM, three-hop DRAM, three-hop C2C, I/O ingress
  and I/O egress, each at 16, 65, 16,384 and 65,536 bytes.
- 18 mixed/shared controls: two and three DRAM flows; disjoint columns;
  reverse directions; DRAM/C2C and DRAM/I/O sharing; all-three-class sharing;
  common source endpoint. Ready offsets 0, 509 and 3,000 include simultaneous,
  partial-overlap and fully separated cases where applicable.

Each condition runs D1/S twice in fresh network state, rotating order: 152
component executions. Require repeated message hashes, complete all-message
reception and exact single-flow duration agreement. Check no-sharing controls
and staggered progress, while reporting all concurrent-service errors. Concurrent
components are validation of the fixed sharing hypothesis, not fitting data.
If singleton agreement fails, no application completion receipt is allowed
for this candidate until that independent-service issue is resolved explicitly.

Independent fluid audit reconstructs paths/resources from machine input,
checks byte rounding and packet work, verifies every capacity and a saturated
max-min bottleneck certificate for every flow, and requires the first valid
integer serialization boundary plus the declared propagation. It does not call
the prediction allocator. Tampered rates, paths, missing progress, incomplete
work, mixed traffic and deadline boundaries have semantic regressions.

## Frozen complete work, ranking and cost

The old scaling study has nine machine/work/layout inputs and 27 U0/U1/S
model cells. Preserve it. This new comparison uses those identical nine inputs
with **D0/D1/S**, also 27 cells and three rotated fresh-process repetitions:
81 complete executions. Retain U1's accepted results for interpretation. Require
exact accepted D0/S execution hashes and equal physical input identities.
All DAG/dependency, work/bytes, capacity, publication and retirement audits must
pass; capacity waits remain zero. Replay native streams for 18 D0/S cells.
D1 is independently audited from fluid epochs; it has no native stream.

Keep 100-cycle indifference and gap-error budgets, and the 2% application-time
budget. Report signed errors, all layout pairs, primary A−B ranking, false ties,
candidate-set regret and same-message service errors on S's critical messages.
Correct direction with excessive gap error is a partial result. After prediction
is complete, compare D1 paths to S's recorded paths for diagnosis only.

Measure graph/binding, network construction/initialization, execution, logging,
serialization, audit, CPU and RSS. Also time each **whole fresh worker** including
imports and all these phases. Record full output size, fluid epochs, zero native
process/flit counts, host load and affinity. Reference replay and component
validation costs are separate. D1 reuses D0's 628-second calibration; report
incremental component cost and do not claim free calibration or whole-campaign
speedup from execution-only ratios. Large captures/epoch tables stay on hn072.

Close this one hypothesis with accuracy and cost, whether it passes or fails.
If it succeeds, a new untouched workload is a subsequent study. If it fails,
distinguish path mismatch, sharing-service approximation and missing transient
feedback as possible explanations without declaring credit uniquely necessary.
No expansion of the machine, thermal/hardware validation, equal physical cost
or simulator-method novelty is established by this limited experiment.
