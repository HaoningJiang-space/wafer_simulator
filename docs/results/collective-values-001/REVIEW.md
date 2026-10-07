# Collective identity, tensor versions and target lifetime

Matched collective calls now bind to explicit byte-region value versions, and
those versions identify target allocations and transfers. Runtime availability
is separate from source version construction. The target state publishes an
output after its required writes and retains each version through the completion
of all declared consumers. A second collective can consume the first one's
resident output without allocating another input copy.

The [119 semantic tests](tests.log) passed on eex005 at `1d1bbc5`
([receipt](SEMANTICS.json)). Coverage includes an in-place source input/output,
partial earlier writes with multiple producers, stale allocation generations,
rejection before mutation, a broadcast with uninitialized non-root destinations,
capacity failure without partial acquisition, fanout, retained results, local
completion before global completion, and a chain of two collectives sharing
one storage pool. Transfers carry version identities, including explicit
reduce-scatter chunk positions. These are software semantics, not timing results.

Code responsibilities remain separate: `workloads/collective_values.py` binds
source accesses and immutable producers; `adapters/collectives.py` generates
target demands; `execution/values.py` tracks residency/consumers;
`execution/reservations.py` owns capacity and active pins; `execution/collectives.py`
publishes and consumes versions at service boundaries. Source correspondence
stays in `analysis/collective_ports.py`, with remote orchestration in `scripts/`.
The existing ByteVersions, target adapter and storage pool are reused. Frozen
native BookSim and third-party implementations are unchanged.

## Complete source correspondence

The complete evidence join used commit `6dbe21b`. The later adapter change adds
version IDs to transfers and the chained-lifetime regression; it does not change
this join. [VALIDATED.json](VALIDATED.json) hashes all outputs. It pairs the
accepted complete effect and owner ledgers by rank, original node and byte offset,
checks each collective's tensor roles and dependencies, and preserves original
CPU/GPU/wait ports. The [summary](SUMMARY.json) gives:

| Quantity | Count |
|---|---:|
| Original source records checked | 4,530,939 |
| CPU collective calls joined | 33,632 |
| Tensor input/output operand pairs | 33,312 |
| Calls with at least one source/destination pair sharing storage identity | 33,312 |
| Calls with explicit communicator/sequence identity | 3,840 |
| Attached GPU ports | 6,496 |
| Attached wait ports | 3,840 |

Shared source storage is evidence that input/output identities must be treated
carefully; it does not establish simultaneous byte overlap, allocation lifetime
or a target in-place implementation. No source record was dropped to construct
this table. The join writes only collective annotations and leaves the complete
accepted ledgers unchanged.

Full joined artifacts stay at
`/home/wangziheng/wafer_simulator/runs/collective-ports-001` (about 2.4 MiB).
Per-rank receipts record hashes of all consumed ledgers; original complete
input identities remain linked through the accepted collective, effects and
ownership receipts. [STARTED.json](STARTED.json) records the interpreter and
packages. Only compact reports and receipts are committed here. No raw captures
were copied locally and no new full simulation or smoke experiment ran.

## What remains source-dependent

The full capture still has 29,792 coalesced calls without a source-backed
communicator/communication-sequence pair. Inspected call and attached GPU
attributes contain source profiling/stream fields; opaque ProcessGroup/Work
arguments do not provide the missing object identity. The join preserves these
calls and records the missing identity instead of matching by order.

Every joined call also retains explicit requirements for allocation generation,
exact byte footprint and access order. Consequently **the full-capture value
binding count is still zero**: the new version/lifetime interface is verified
with explicit analytical bindings, while these missing facts are not fabricated
for the capture. The earlier 24 instances with unresolved reduction operators
remain unresolved as well. Source-owned call scopes are not automatically target
completion events.

The next source step is to supply these explicit layout/allocation/order and
communication identities, or define a separate supported logical workload with
them declared. The current capture is retained as a complete, unresolved source
description. Calibration and a complete timed execution backend remain separate
from this milestone. See the [updated contract](../../COLLECTIVES.md).
