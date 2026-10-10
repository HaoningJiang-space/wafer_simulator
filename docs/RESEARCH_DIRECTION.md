# Current research: spatial compute–memory–communication model fidelity

The machine is not defined by `spcl/nw-design-for-wsi`. That pinned implementation
provides one Logic-on-Interconnect baseline with its own connectivity assumptions.
Its accepted model-selection results remain valid within their declared scope.

The current candidate is a stitched compute wafer plus an aligned memory wafer,
with explicit SRAM, banks, shared controllers, vertical HB and edge I/O. The
[machine contract](WAFER_MACHINE.md) distinguishes primary-source support for
individual integration mechanisms from the numerical design assumptions and
unqualified combination used in this candidate. No manufactured product claim.

The simulator contract stays:

`logical work + physical machine + mapping/policy -> resource services -> data readiness -> application time`.

Keep the responsibilities separate. Workload definitions contain mathematical
work, immutable objects and dependencies. Architecture definitions contain
geometry and finite resources. Adapters bind the two and specify transaction
paths. Existing execution/storage/calendar and native BookSim are reused.

## First gate: machine integration

Verify local and remote accesses use the defined resources. A remote load needs
a request, bank/controller service and a response over legal physical links.
A store commits before acknowledging completion. Count protocol bytes, data
bytes, bank capacity and controller staging separately. Reject stitching-free
lateral links, illegal HB alignment and resource oversubscription.

The registered complete two-GEMM work exercises all paths with fixed near,
offset and concentrated data placement. This is integration acceptance. A
changed result from changing data placement is not a model-accuracy result.
The reference is an analytical, request-atomic memory contract; row timing,
refresh, streaming RX, internal PE networks and physical closure remain outside
its claims. Numerical rates and capacities are declared assumptions.

## Completed model comparison

The [registered U0/U1/S study](MEMORY_ABSTRACTION_PROTOCOL.md) fixes one machine,
logical work, mapping and execution policy within each of three data layouts.
It is [complete](results/memory-abstraction-001/REVIEW.md): both aggregate
communication models lose the 3,193-cycle near/remote distinction and
underestimate concentrated-storage penalties. They execute faster but fail the
registered application/gap budgets. Controller identities alone are insufficient
for this layout judgment. S remains a conditional mechanism reference.

U0 keeps physical staging guards while pooling DRAM service/capacity. U1 retains
the original banks/controllers and substitutes independent uniform communication.
S–U1 therefore includes path and shared-network effects, not distance alone.
Capacity waiting is reported separately; identical retirement rules can produce
different waits when network and service timing change. No kernel change or new
network feature was needed to obtain this result.

## Completed spatial scaling and decision coverage

The [registered locality–controller balance study](SPATIAL_SCALING_PROTOCOL.md)
is [accepted](results/spatial-scaling-001/REVIEW.md): 4×4, 6×6 and 7×7 arrays,
fixed work and resources per tile, 27 model/layout/size cells, 81 full executions.
Geometry/connectivity legality does not imply manufacturing qualification.
All-operation capacity upper bounds fit and observed capacity waits are zero.

The fixed clustered-near versus remote-balanced pair changes ordering between
4×4 and 6×6 in S. U1 preserves the bank-load penalty but misses the growing
spatial communication time, selecting the wrong member at 6×6/7×7. The local
layout still wins globally. Critical network exposure increases; nominal cut
or HB saturation and a universal bottleneck-migration sequence are not proven.

This closes the larger-coverage question without changing the execution kernel.
S remains practical for these instances (largest execution median 7.51 seconds
on hn072), but it performs and logs far more network events than U0/U1. A future
method question is whether a lower-cost spatial service model recovers these
decisions. The current results do not select a unique omitted mechanism or
prove all detailed BookSim states necessary. No new model is committed by this
milestone; retain the registered controls and the negative saturation result.

## Completed response-service mechanism discrimination

The [registered isolation test](ISOLATED_RESPONSE_PROTOCOL.md) is
[accepted](results/isolated-response-001/REVIEW.md): 20 complete long responses,
10 native replays, unchanged graph/router/link settings. On one 6×6 graph,
0–5 C2C hops keep injection span at 1,987 cycles and middle-half injection rate
at 32 B/cycle. Each hop adds 21 cycles to first receive and completion, without
reducing this isolated sustained rate.

The four matched critical responses become much slower with the original
workload background. Actual critical outputs carry the target plus one peer
at 4×4, and the target plus two peers at 6×6. Their source HB links have no
overlapping peer traffic, yet injection is slowed. This supports downstream
sharing/feedback as the cause class. It does not establish nominal saturation
or uniquely separate allocation, finite buffering, credits and traffic history.

These probes and the original 27-cell results remain frozen. They motivated
testing independently calibrated spatial service before introducing shared
state; no native buffer/credit intervention or hardware-parameter search follows.

## Completed independent spatial service baseline

The [D0 protocol](INDEPENDENT_SPATIAL_SERVICE_PROTOCOL.md) is
[accepted](results/independent-spatial-service-001/REVIEW.md): 1,700 physical
endpoint/payload conditions, 3,460 empty-network captures and 81 complete
U1/D0/S runs. Calibration is generated from machine/input plans without full-S
timings, routes, eligibility clocks or overlaps. D0 retains U1 bank/controller
services and predicts each DRAM message independently from its own ready clock.
All original U1/S execution hashes reproduce; no execution-kernel change.

D0 restores Local's exact 23,903-cycle time at all three sizes and selects
Local alone globally, removing U1's Local/B false tie. Application MAPE falls
from 15.517% to 6.724%. But its primary A−B gaps are +6,338 / +6,212 / +4,290
cycles versus S's +3,549 / −658 / −3,318. It still selects B wrongly at 6×6/7×7
and fails the 100-cycle magnitude budget for every layout pair. Accurate
independent service helps absolute timing and some choices; it is insufficient
for the registered locality-versus-load tradeoff.

The model executes with lower recurring cost and RSS, while calibration took
628 seconds and the exact table is 1.7 MB. That cost is reported separately;
there is no end-to-end one-off speedup claim or unseen-size/path validation.
These results justify studying a lightweight, time-dependent shared-path
service model for the frozen decisions. They do not identify the minimum state,
prove every BookSim detail necessary or establish hardware accuracy or novelty.
No U2 is implemented or preselected. Preserve the frozen controls and gap budget.

Parameter uncertainty must remain visible. If results depend on an uncalibrated
bank/controller policy, characterize that component rather than declaring the
whole wafer validated. If a simple abstraction is adequate, retain it. A new
machine graph alone does not establish a simulator research contribution.

## Public behavior-preserving code organization

The [public API extraction](results/public-periphery-api-001/REVIEW.md) is
complete with f91824d behavior retained. Explicit machine/work/placement/policy
compilation, existing execution, and supplied-plan/event auditing are independent
of private server/repository setup. The [portable suite and usage guide](PUBLIC_PERIPHERY_API.md)
support standalone testing; private receipt workflows retain host/root,
clean-source and same-source checks. The final 254-test formal suite and
141-test minimal-environment suite pass. Eleven pre-refactor event/state cases,
15 registered input identities and three old Native component readbacks match.
There is no new application execution, model/policy change or hardware claim.
Other historical studies retain their pinned entry points and source gates;
this extraction does not reopen their matrices or generalize D1's scope.

## Completed memory-periphery policy sensitivity

The [registered six-cell study](MEMORY_PERIPHERY_PROTOCOL.md) is
[checked](results/memory-periphery-001/REVIEW.md). The original v1 retains one
endpoint per bank. A distinct organization has one interface per controller,
with storage partition/port identity separate from endpoint identity. At the
whole-object policy both organizations give A=30,645 and B=31,303 cycles at 6×6.
Under the same shared-interface organization, a fixed 4 KiB/four-slot pipeline
gives A=25,345 and B=23,561. Thus the preferred member changes from A to B.
The interface contrast and policy contrast are separate; no pipeline arm under
bank-specific endpoints was run, so their interaction is not identified.

All 18 applications reproduce across three fresh processes, nine components
complete and 15 native command streams replay. All 27 saved executions were
reaudited; 562 artifact and 140 source hashes were checked. Bank/channel work,
payload/control bytes, capacities, operand order and retirement remain fixed.
Every observed transaction window is within four fragments. The policy changes
both DRAM and external-controller supply scheduling; C2C stays whole-object.
This shows why zero capacity waiting did not establish policy independence.

The [acceptance repairs](results/memory-periphery-audit-fix-001/REVIEW.md) reject
early-publication plans independently of execution, derive summaries from
audited events and validate router ports after declaring actual NICs. All 27
old executions reproduce the accepted tables and counts under these checks;
239 remote regressions pass. Original artifacts and execution/storage semantics
remain unchanged, with no new application runs.

The [existing-trace analysis](results/memory-periphery-attribution-001/INTERPRETATION.md)
records earlier supply, bank/channel/network overlap and changed critical-chain
exposure. B has no observed packet-order or route changes; its critical W read
payload envelope stays 6,177 cycles and V's increases from 6,171 to 6,674.
Earlier transaction completion therefore does not imply faster network service.
These observations constrain explanations without uniquely assigning causal
cycle counts to overlap, service interleaving or feedback.

The [window contract](MEMORY_WINDOW_CONTRACT.md) explicitly retains
ideal_commit_visibility: four end-to-end positions per transaction, remote
commit visible globally without notification propagation. No target controller
descriptor, total-fragment or RX budget is available. A can demand 16
controller-associated positions despite the per-transaction bound of four;
this is a demand envelope, not certified resident storage. Retain both declared
contracts without choosing a principal machine from their rankings. Defining a
physical controller requires ownership/lifetime, aggregate issue limits,
receive storage and a completion notification protocol.

The old shared-network findings and D0 errors remain valid under v1. They do not
establish layout-choice robustness across storage/DMA policies. The reticle-region
compute rate, bank serializer and controller channel still have declared rather
than product-derived values. This comparison clarifies their service roles; it
does not qualify a physical memory-periphery implementation or equal cost.

The [D1 max-min comparison](results/shared-spatial-service-001/REVIEW.md) is now
complete under v1: 81 applications and 18 replays, all frozen D0/S event hashes
equal. D1 restores all nine pair directions and reduces MAPE to 1.201%, with
8/9 application-budget passes. None of the nine signed gap errors passes the
100-cycle budget. Local remains the unique global choice for D0, D1 and S.
Fresh-worker recurring cost is 8.03–13.81× lower than S, with existing calibration
reported separately. This is a partial result; close this candidate without
adjusting effective rates, fairness or mappings. Flow fairness and instant
whole-path occupancy remain hypotheses, not inferred native policies.
Do not interpret these v1 numbers as predictions for the new pipeline.
No new holdout workload, parameter sweep, hardware calibration or more detailed
credit model is part of this completed study.

## Necessary information and behavior-preserving computation

The [evidence table](NECESSARY_INFORMATION.md) relates independent duration,
source ordering, immediate end-to-end sharing, flow fairness, supply granularity
and ideal feedback to observed or constructed distinguishing cases. S is the detailed reference
within an explicit machine contract; agreement with S is separate from hardware
representativeness. Treat D0 and D1 as retained comparisons, not an obligation
to build D2/D3.

The [saved-data source-order test](results/source-order-001/REVIEW.md) confirms
that native selection is nonpreemptive until the current source injection queue
drains. A source-only probe recovers common-source final times without fitting
rates, but still releases the second head 60 cycles after native selection.
The three-distinct-source component remains inaccurate. Its output arrivals
count 501/501/1,002 flits from two input branches in a common window; this is
evidence to test input identity and local arrival, not a complete arbitration law.

All 69 saved S critical network messages have zero generation wait. Neither
6×6 nor 7×7 B has a D1 same-source overlap touching the S critical chain, while
both have actual two-plus-one input merging on critical responses. Do not
promote the common-source repair into a primary explanation of application gap
errors. Local competition remains relevant; the completed bounded test below
identifies its actual service stage. The source-only candidate does not pass the
component gate for a new application backend; zero new native or application executions were needed.

The [local-service reconstruction](results/local-service-001/REVIEW.md) observes
24→36 at offsets 0/509/3,000 without changing reference events. With one output
VC, contention enters VC allocation and ownership filters switch eligibility;
all observed switch calls have at most one requesting input. The 32/32 branch
counts in complete overlapping windows are therefore not proof of simultaneous
input-fair switch allocation. Given actual arrivals and processed credit returns,
a small FIFO/VC/pipeline state machine computes eligibility and reproduces all
four local service clocks. Requests/grants are comparison targets, not inputs to
that second replay. This closes conditional reconstruction only: source release,
upstream arrivals, downstream feedback and complete messages are not independently
predicted. Busy-case advancement skips only 18 cycles; no speedup is claimed.
No new application backend or matrix is started. A next method experiment should
retain these established causal boundaries while separately testing independent
boundary generation or compression, without fitting flow weights or bandwidth.

The [G1 experiment](results/causal-closure-001/REVIEW.md) now closes those
external boundaries on an explicit four-router merge tree. Given only the
external ready/source/destination/flit counts and declared service contract,
local states generate upstream arrivals and all downstream credit returns.
Seven cases match source generation/injection, flit arrivals, VC/switch/send
clocks, allocator/FIFO/ownership state, credit sequences, message finishes and
final drainage. The tight-credit diagnostic exercises actual blocking at all
three upstream routers. The observer preserves full S events/protocols.
This is independent component prediction, beyond conditional reconstruction;
it remains limited to unique routes, single VC/packets and one used output per
router. No closed application, general backend or minimum-state proof follows.
The original implementation advances cycles/flits and remains an unchanged reference.

The [compressibility audit](results/causal-compressibility-001/REVIEW.md) now
tests the repeated-state hypothesis without changing that predictor. Single
flow, simultaneous merge and tight-credit cases show recurring 2, 8/4 and
78/39-cycle causal kernels plus ordered service/credit outputs. Their finite
remaining counts are unequal and stay explicit guards. This supports testing
a bounded batch update; that audit alone is not an acceleration receipt.
The saved states and opportunity summaries have independent readback and
hash-consistent negative checks. No Native or application matrix was rerun.

The [G2.1 acceptance](results/causal-macro-single-001/REVIEW.md) now establishes
exact guarded two-cycle batching in the primary single-source contract. Full
events and macro boundary states match original G1. Same-core off/on execution
with identical counters outputs demonstrates computation skipping and measured
worker acceleration; reconstructable evidence and full audit costs are separate.
G1 and the AST-derived G2.1 prototype remain fixed references. The subsequent
[R1 explicit state/transition gate](results/causal-transition-001/REVIEW.md) now
passes seven cases, every cycle/final boundary and complete saved predictions.
New ordinary execution has no AST, tracing or analysis dependency. Full evidence
remains; sinks, macro migration and multi-source/credit-limited compression are
separate future gates. Do not treat this equivalence result as a new speedup.

Changes to recording must preserve message completion and closed execution.
If repeated router work is the relevant cost, investigate batching between
causally necessary boundaries with event equivalence; do not assume an unchanged
active-flow count licenses a jump. No event-compressed network or new physical
feedback protocol is implemented by these milestones.

The [two-input S cost diagnosis](results/native-service-profile-001/REVIEW.md)
now preserves full events and protocols in four controlled profiles. Remaining
BookSim Step work and adapter flit/path recording are both material; Python JSON
and audit traversals add cost. Evidence optimization is an independent engineering
track, not a prerequisite for testing source order and local merging. The local
recording-mode draft is paused outside main, without validation or performance
claims. S stays the detailed decision reference, D0/D1 the comparisons. Profiling
waits are not pure IPC cost, and instrumented sections are not speedup measurements.

## Frozen evidence

The old [boundary model choice](results/boundary-design-001/model_selection.md)
and [group-sharing coverage](results/group-sharing-001/REVIEW.md) are complete.
The latter reports actual shared paths but no final group slowdown; it is not a
pending experiment. Do not restart packet/FIFO enhancement, algorithm or mapping
search, Chakra recovery, thermal/PDN or runtime optimization as a prerequisite.
The superseded benchmark-envelope draft had no executed or accepted results.
All accepted artifacts remain indexed in [MILESTONES.md](MILESTONES.md).
The active experiment server is now hn072; historical eex005 evidence is kept
in a verified cold archive, with [recovery and cleanup records](results/server-migration-001/REVIEW.md).
