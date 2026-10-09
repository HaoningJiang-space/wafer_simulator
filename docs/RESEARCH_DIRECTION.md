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

The next method question is whether effective single-flow service plus limited
shared spatial state can preserve the accepted application/layout judgments
at lower cost. A distance-only independent message cost does not explain these
observations. No U2 is implemented or preselected, and the result does not
prove all native router states necessary. Freeze these probes and the 27-cell
results; do not respond by resuming general scaling or hardware-parameter search.

Parameter uncertainty must remain visible. If results depend on an uncalibrated
bank/controller policy, characterize that component rather than declaring the
whole wafer validated. If a simple abstraction is adequate, retain it. A new
machine graph alone does not establish a simulator research contribution.

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
