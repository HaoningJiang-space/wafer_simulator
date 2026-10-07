# Spatial contract v1: logical work, binding and finite storage

This milestone implements the first resource-binding and lifetime contract
from [the research direction](RESEARCH_DIRECTION.md). It does not yet calculate
application time, run a new Llama model, or replace the accepted 006 backend.
The semantic state reports `timing_evaluated=false`, including when all declared
operations have completed their semantic phase callbacks.
The new [timed backend](TIMED_EXECUTION.md) now drives these callbacks from
explicit target compute, memory and network services; its result records
`timing_evaluated=true`. The original state remains usable for semantic checks.

## Implemented layers

| Layer | Responsibility |
| --- | --- |
| [workloads/spatial.py](../src/wafer_sim/workloads/spatial.py) | Immutable whole data objects, producers/consumers, work quantities and control dependencies; reuse the existing DAG validator |
| [architecture/spatial.py](../src/wafer_sim/architecture/spatial.py) | Memory capacities/ports, compute identities and supported work units, endpoint/router connectivity |
| [adapters/spatial.py](../src/wafer_sim/adapters/spatial.py) | Bind independent compute and data placements; generate memory service and target transfers; reuse existing WoW geometry exports |
| [execution/plan.py](../src/wafer_sim/execution/plan.py) | Explicit reservations, resource demands and ordered completion phases |
| [execution/storage.py](../src/wafer_sim/execution/storage.py) | Atomic regional admission, data availability and last-consumer release; no timing or scheduling policy |

Logical operations carry quantities such as a declared number of MACs, with
provenance. A duration is not accepted as a work unit. A data object carries
size, producer, retention policy and provenance. Its ID denotes one immutable,
non-aliasing version, not a raw address or an inferred tensor from message size.
Collectives must already have an explicit supported lowering; no collective
optimizer or source-order deletion is introduced here.

The binding accepts exactly one assignment per operation and per data object.
Moving either compute or a data home regenerates the required transfers while
preserving logical work and dependencies. Network reachability uses the actual
exported router graph, not average hop count. This checks physical connectivity,
not the permitted paths of a particular routing policy or transfer timing.

## Precisely declared v1 storage policy

Each object has one persistent home. Initial objects are available there at
time zero. Initial objects with no consumers and no retention requirement can
be freed immediately. All other initial live bytes must fit each home region;
unused capacity elsewhere cannot compensate for local overflow.

For each operation, admission atomically reserves all of the following:

- Output homes, even when their producer computes elsewhere.
- A private local staging copy for each remote input and remote output.
- Explicit local scratch space.

Resident local input objects are already charged and are not allocated again.
If any region lacks space, no region is partially reserved. The caller may
retry after another operation releases space. A permanently blocked state is
not complete, and the API supplies missing predecessors and shortages. It
does not silently spill, evict, drop dependencies or choose a new schedule.

Admitted operations follow ordered, whole-object phases:

1. Each remote input: source memory read, network transfer, destination staging write.
2. Local reads of the complete inputs, then compute service, then local output writes.
3. Each remote output: local staging read, network transfer, destination home write.

This is a serialized staging policy within an operation. The extra staging
reads/writes are intentional traffic, not a claim that every wafer implements
this data path. The local compute boundary reads each whole input once and
writes each whole output once. Scratch currently charges capacity only; hidden
scratch accesses, repeated kernel reads and cache behavior are not inferred.
These service demands must not be called calibrated kernel memory traffic.
No direct network-to-ALU streaming, overlapping these phases,
cross-operation cache reuse or storage aliasing is implied. The first version
requires one memory region per endpoint; several memory domains behind one
endpoint require a distinct local-DMA model and are rejected.

An output becomes globally available only after the producer's final phase,
including all destination writes. The consumer cannot proceed on first-flit
injection or network arrival alone. Inputs stay live through the completion
of their last consumer; temporary staging/scratch frees at operation completion.
Retained outputs remain charged. Each service phase has a unique ordinal;
unadmitted, duplicate and out-of-order completion calls are rejected.

An operation can be admitted while another is active. Its memory reservation
does not grant its compute unit, memory port or network link. Equal resource
IDs in demands are arbitrated by the separate timed backend; source and
destination memory ports must be included. A caller advancing callbacks without
that service model checks lifecycle semantics only. No bandwidth contention,
runtime or speedup can be claimed from these callbacks themselves.

## Input support and reuse boundary

The current complete ATLAHS grouped capture supplies collective types, sizes,
source workers and buffer addresses. Buffer address reuse is not a supported
substitute for storage versions, aliasing and object lifetime. The source
inspection script reports actual field presence and all four SQLite schemas;
it does not claim that omitted semantic information is unrecoverable from
every possible raw event or additional capture.

Compute work amounts, complete dataflow and local memory calibration remain
missing for a full spatial replay of this capture. The WoW importer supplies
network identity/connectivity from the accepted exports and explicitly does
not infer memory capacity or service rates. No capacity values from the unit
fixtures enter the formal M0/M1 configurations.

The existing GOAL ingestion, source correspondence, author geometry, DAG
validator and BookSim are retained. This is an internal typed interface, not
a newly proposed serialized trace standard. We inspected the
[Chakra schema at 9ff3e3e](https://github.com/mlcommons/chakra/blob/9ff3e3e2f276b4c0554a83f8747bf00b2786fa85/schema/protobuf/et_def.proto):
it provides operation kinds, control/data dependencies, IO descriptions and
tensor/storage identity fields. The subsequent
[Chakra normalization milestone](results/chakra-normalization-001/REVIEW.md)
now reads the complete published rank set through that schema and recovers
shape-derived matrix work. It does not yet supply a complete logical input to
this contract: storage versions/aliasing, remaining operators and execution
scope still need resolution. The published Chakra files are not established
as the same capture as the accepted GOAL input.

## Verification and the next decision

[test_spatial.py](../tests/test_spatial.py) contains analytical semantic
regressions: same logical bytes with different movements; source/read and
destination/write demands; physical disconnection; local overflow despite free
global capacity; atomic blocking/recovery; fanout lifetimes; output availability;
scratch/retention accounting; invalid identities, work and completion ordering.
They are software tests, not smoke experiments or a new workload benchmark.

All **20 tests passed on eex005**, at code commit `06a05ed`. The same code
imported both accepted WoW network graphs (124/232 and 100/226 routers/links)
and inspected all 39,248 grouped source events and all four SQLite schemas.
The [validation receipt](results/spatial-contract-001/VALIDATION.json) includes
code and test-log hashes; [source support](results/spatial-contract-001/SOURCE_SUPPORT.json)
records the actual fields and unresolved inputs. None of these checks invokes
BookSim or provides a new application result.

Build/test execution stays on eex005. Existing complete events and native
binaries are unchanged. The next decision is to provide a complete, supported
logical input and target service parameters before connecting this contract
to a timing backend. The earlier static-versus-shared transfer comparison
remains a separate controlled modeling question, not answered by this milestone.
