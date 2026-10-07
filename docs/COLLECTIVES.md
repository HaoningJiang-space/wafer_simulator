# Collective participants, volume and completion

The collective frontend describes logical participants and tensor roles before
choosing a target algorithm. It exposes target resource demands and completion
conditions without replaying source elapsed time. The
[full-source result](results/collectives-001/REVIEW.md) distinguishes recovered
facts, unresolved source identities and the separately tested target contract.

## Layer boundaries

| Layer | Implementation | Responsibility |
|---|---|---|
| Source decoding | `workloads/chakra_collectives.py` | Tensor argument roles, explicit communicator/sequence, source ports |
| Logical work | `workloads/collectives.py` | Ordered members, slots, reduction and root; volume validation |
| Target binding | `adapters/collectives.py` | Explicit collective algorithm mapped to compute, memory and network demands |
| Execution state | `execution/collectives.py` | Capacity admission, service prerequisites and completion |
| Shared storage | `execution/reservations.py` | Atomic finite-memory reservations shared with ordinary spatial execution |
| Independent readback | `analysis/collective_sources.py` | Raw records, identities and operand-size correspondence |

`scripts/normalize_collectives_remote.py` orchestrates complete 16-rank source
processing on eex005. It reads every original node, inventories every collective
call, and independently rereads the raw input. Its selected record ledger is
an annotation of the full source, not a replacement application DAG.

## Source identity and tensor volume

An instance needs an explicit `(process_group, communication_sequence)` and
ordered global participants. Membership comes from nonempty initialization
metadata or the parameter record's explicit global start, stride and size.
Contradictory declarations, duplicate calls or missing participants fail matching.
Autograd sequence numbers, temporal proximity, rank-local call order and tensor
size ratios cannot substitute for communication identity.

The pinned [c10d operator definitions](../third_party/references/pytorch/torch/csrc/distributed/c10d/Ops.cpp)
show that all-gather and reduce-scatter destinations can be **input argument 0**,
with sources in input argument 1. The returned Work object is not the output
tensor. Slots retain original argument paths and descriptors, shape, dtype,
element count and element bytes. The implemented forms are broadcast, allreduce,
base/coalesced allgather, coalesced reduce-scatter and barrier. Unsupported schemas
remain explicit errors; arbitrary c10d operators are not assumed supported.

For group size `N` and one slot with `I` input elements, logical output elements
are `N*I` for allgather, `I/N` for reduce-scatter, and `I` for allreduce/broadcast.
Ratios constrain a prospective match but do not identify its participants.
Barrier's device-selection tensor is metadata, not application payload.

The [parameter ABI](../third_party/references/pytorch/torch/csrc/distributed/c10d/ParamCommsUtils.hpp)
has forms with and without a leading tensor list. A
[WorkNCCL wait record](../third_party/references/pytorch/torch/csrc/distributed/c10d/ProcessGroupNCCL.cpp)
uses placeholder fields, including a final `1` and negative start/stride; it
must not redeclare a one-rank communicator. Waits attach only through their
explicit matching group and communication sequence. CPU return is retained
separately and never proves output availability.

Chakra's GPU `comm_size` sums input descriptors, which can include both source
and destination buffers. It is retained as source evidence, separately from
logical input bytes and target transferred bytes. Reduction operators require
evidence: compatible attached GPU kernel identity can establish SUM; an opaque
ReduceOp argument alone cannot. A singleton reduction is an identity operation.

All inspected PyTorch files and notices are pinned in this repository. The
[source manifest](../third_party/references/pytorch/SOURCE.json) records their
hashes. This reference revision does not establish the capture's exact build.

## Target resource binding

`bind_collective(..., policy="direct_exchange_rank_order_sum")` requires an
explicit mapping for every participant and the existing target resource graph.
Communicator order remains logical rank order, independent of physical IDs.
The current policy is a declared simple target algorithm, not inferred NCCL
ring/tree behavior:

- Allgather directly distributes each rank's input to every output region.
- Broadcast distributes the logical root's input.
- Allreduce gathers to the first communicator member, performs rank-order SUM,
  and distributes the result.
- Reduce-scatter exchanges destination chunks and reduces at each destination.
- Barrier currently supplies only an all-participant rendezvous condition.

Actions expose memory-read/write byte demands, network transfers with source
and destination memory/endpoints, and `(N-1)*output_elements` scalar additions
per reduced output. Targets must explicitly provide scalar-add service. A
network backend resolves routes and contention on the target graph. Co-located
memory avoids a network transfer; disconnected endpoints reject binding.
This layer does not assign calibrated bandwidth, compute rates or latency.

The current storage policy uses distinct immutable input/output versions and
separate receive staging. Inputs must already be resident and ready. Each
participant atomically reserves output and staging capacity before entry;
failure leaves no partial reservation. The same `ReservationPool` can be passed
from ordinary execution so concurrent operations share one capacity budget.
Input lifetime belongs to the caller, outputs remain allocated, and staging is
conservatively retained until global collective completion. There is no spill
policy. In-place aliasing and capacity deadlock recovery are not implemented.

## Completion is a resource event

Actions become eligible only when their participant-entry and action
dependencies are satisfied. A timing backend must call `complete(action)` after
the **whole service** has finished. Transfer injection does not complete the
transfer, and transfer completion does not complete the destination memory write.
`output_ready(rank, slot)` requires all writes needed by that output.

`wait_satisfied(rank)` requires that rank's output and its participating services
to finish. It does not wait for unrelated ranks' final services. The separate
`all_complete()` predicate covers every participant and action. The regression
suite includes a schedule where one rank can continue while another rank's
final output write is pending. Barrier requires all entries, but needs an
explicit control-message protocol before its latency can be predicted; the
current semantic rendezvous is not evidence for zero-cost barriers.

The binder's analytical tests establish these rules on declared resource
fixtures. The source exporter preserves CPU call IDs, input/output operand
ports, attached GPU IDs and matching wait IDs. Joining these ports to complete
call ownership and concrete tensor allocation/version lifetimes remains required
before full-capture target lowering. Unknown communicator identities, reduction
operators and tensor layouts cannot be filled by this target policy.

No complete native wafer application time is claimed. The next integration is
source-port-to-value binding and recovery of missing collective identities,
followed by a validated timed resource backend, not a new placement sweep.
