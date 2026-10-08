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

## Next coverage question

Freeze these models and register physically legal larger machine/work instances.
Specify how compute, storage, controllers, horizontal cuts and vertical capacity
scale before execution. First test whether the current model-selection result
holds beyond 4×4 tiles and 32 GEMMs. Do not grow work merely to obtain a ranking
reversal, assume compute and all communication budgets scale together, or add
another memory/network mechanism before this coverage question is answered.
No larger configuration has been executed or accepted by the present study.

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
