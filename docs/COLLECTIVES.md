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
| Tensor values | `workloads/collective_values.py` | Exact source access bindings, input snapshots and output producer versions |
| Target binding | `adapters/collectives.py` | Explicit collective algorithm mapped to compute, memory and network demands |
| Execution state | `execution/collectives.py` | Capacity admission, service prerequisites and completion |
| Shared storage | `execution/reservations.py` | Atomic finite-memory reservations shared with ordinary spatial execution |
| Value lifetime | `execution/values.py` | Resident version readiness, declared consumers and last-consumer release |
| Independent readback | `analysis/collective_sources.py` | Raw records, identities and operand-size correspondence |
| Source port join | `analysis/collective_ports.py` | Join all calls, GPU and wait ports to checked ownership/effect ledgers |

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

The current target storage policy uses distinct immutable input/output versions and
separate receive staging. Inputs must already be resident and ready. Each
participant atomically reserves output and staging capacity before entry;
failure leaves no partial reservation. The same `ReservationPool` can be passed
from ordinary execution so concurrent operations share one capacity budget.
With version binding, `ValueLifetime` controls input/output residency using the
complete declared consumer set. Staging is conservatively retained until global
collective completion. The older unversioned analytical interface leaves input
and output lifetime to its caller. There is no spill policy or capacity deadlock
recovery. Source in-place writes can become distinct immutable target versions;
target in-place buffer reuse is not implemented.

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
ports, attached GPU IDs and matching wait IDs. These ports are now joined to
complete call ownership; concrete allocation/version bindings remain required
for the capture. Unknown communicator identities, reduction operators and tensor
layouts cannot be filled by the target policy.

## Source ports to resident versions

`bind_values` accepts a checked collective match, original call records and
`AccessBinding` entries keyed by `(rank, call_node, argument_path)`. Every access
needs an explicit live `StorageKey` generation and exact byte spans. It checks
rank/device/storage identity and footprint volume. Missing or stale generations,
missing bindings and overlapping destinations reject the whole operation before
any write. Repeated/broadcast elements needing packing have no implicit rule.

All required inputs are read before **any** output version is created. An
in-place source collective consequently retains its old immutable input even
after the source storage receives a new producer version. Partial prior writes
retain all contributing producers. A broadcast's non-root destination is an
overwrite, not a read of potentially uninitialized contents. Source storage
sharing alone never merges versions or makes them ready.

`TensorValue.key` incorporates rank, device, storage generation, exact slices and
immutable producers. `bind_collective(..., values=...)` uses these identities for
target allocations and transfers; reduce-scatter chunk labels retain communicator
position. Values passed between collectives use the same allocation key, so an
already resident input is not allocated again. Whole value materialization and
placement are explicit; partial views do not automatically become free target
aliases or packing operations.

For execution, first declare each allocation, producer prerequisites, complete
consumer set and retention policy in `ValueLifetime`, sharing a `ReservationPool`.
Then use `CollectiveState(binding, lifetime=...)`. Creating a logical producer
version does not publish it. Target readiness requires the resident allocation
and service completion. Input acquisition pins storage; `release` rejects active
pins. Capacity failure leaves inputs unacquired and output reservations unchanged.

Output writes publish that rank's version for downstream consumers. Each input
consumer finishes only after that rank's collective completion condition. A
separate internal output consumer keeps results resident while the collective
may still read them, and releases at global completion. External consumers can
begin once their data and control prerequisites are satisfied. The last completed
consumer frees an unretained value; retained results remain charged. Consumer
sets must be complete before execution, rather than appended after a release.

The [connected value/lifetime result](results/collective-values-001/REVIEW.md)
includes a two-collective chain, partial producer history, source in-place
updates, failed admission, fanout and local versus global completion. The
catalogue exposes an ordinary producer/consumer interface and shares the existing
finite storage pool; automatic lowering of all ordinary source operators and
their control dependencies is still frontend work.

No complete native wafer application time is claimed. The next integration is
recovery of source allocation/layout/order evidence and missing collective
identities, followed by a validated timed resource backend, not a new placement
sweep. The full source join records unresolved requirements per call.
