# System target and future network boundary contract

This is an integration target, not an implemented backend or a new machine
acceptance. Source review is pinned to
[`w2w-memory:7f15bcc6a4142372590a036657c183e12c9fe0ee`](https://github.com/HaoningJiang-space/w2w-memory/tree/7f15bcc6a4142372590a036657c183e12c9fe0ee).
Neither repository is merged or replaced by this document.

## Project roles

Cerebras is the compute-organization reference: distributed PEs, local SRAM,
neighbor mesh communication and arrival-triggered tasks, as described in the
[official SDK overview](https://www.cerebras.ai/blog/supercharge-your-hpc-research-with-the-cerebras-sdk).
Those features motivate the organization; they do not specify a vertically
integrated DRAM product, BookSim service rules or this candidate's numeric budget.

`w2w-memory` supplies the system track. Its
[V3 architecture](https://github.com/HaoningJiang-space/w2w-memory/blob/7f15bcc6a4142372590a036657c183e12c9fe0ee/docs/ARCHITECTURE.md)
separates manufacturing regions, compute clusters, routers, gateways and unique
native DRAM domains. Its
[physical assumptions](https://github.com/HaoningJiang-space/w2w-memory/blob/7f15bcc6a4142372590a036657c183e12c9fe0ee/docs/PHYSICAL_ASSUMPTIONS.md)
declare 65,536 aggregate PEs in 16 clusters, 3 GiB SRAM and 8 GiB native-domain
memory. A macro compute channel represents 64 or 65 fine hops, not a detailed
Cerebras color/multicast/microthread simulation. Memory has no lateral routers.

`wafer_simulator` supplies the causal-service method track: exact local state,
explicit ordinary transitions, evidence separation, guarded compression and
independent verification. The retained v1 system experiments remain valid
within their own contracts; they do not redefine V3. BookSim and Ramulator
remain detailed references for the declared V3 network and memory behavior.

## Boundary review of the pinned system code

The concrete interfaces are in the pinned
[BookSim adapter](https://github.com/HaoningJiang-space/w2w-memory/blob/7f15bcc6a4142372590a036657c183e12c9fe0ee/w2w/backends/booksim/adapter.py),
[boundary client](https://github.com/HaoningJiang-space/w2w-memory/blob/7f15bcc6a4142372590a036657c183e12c9fe0ee/w2w/backends/booksim/runtime/boundary_booksim.py)
and [system kernel](https://github.com/HaoningJiang-space/w2w-memory/blob/7f15bcc6a4142372590a036657c183e12c9fe0ee/w2w/system/kernel.py).
The names below describe semantic operations; they are not a claim that a new
drop-in API has been implemented.

| Boundary | Required meaning from V3 | Gap from accepted G1/R3 |
|---|---|---|
| Submit / `try_send` | Reserve finite source NI and destination packet slots; rejection leaves the request pending. Preserve physical endpoint and packet identity, header/payload packing and legal reachability | Current component demand has no such admission interface or finite system NI descriptor contract |
| Supply / `supply_prefix` | A monotonic eligible payload prefix makes only supplied flits injectable. Descriptor admission alone does not create data. Supply and submit are ordered mutations before the next Native step | Current homogeneous message is fully available at generation; no streaming supply frontier |
| Advance / `arrive` | Advance conservatively to a system boundary; report actual injection and reception progress in stable order | Explicit component core has integer network cycles and one fixed four-router route, without the V3 adaptive mesh |
| Receive | Distinguish flit arrival from SRAM/NI write completion and complete packet delivery; all applicable activation/response writes contend for declared receive resources | `received` in G1 is endpoint ejection, not a timed system receive commit |
| Commit | Return native receive credit only after the corresponding write/commit condition. Inject and commit mutations must retain their relative order | G1 automatically schedules sink credit after ejection; external delayed commit is unsupported |
| Deliver | The system may defer packet acceptance when a controller pool is full. Dependency notification and destination slot release follow successful acceptance | Current component has no controller-consumer acceptance callback |
| Drain | No pending packets, transport/write events, held NI/arbiter resources or outstanding native credits. System makespan and final drain are separate outputs | G1 distinguishes message finish and drain, but only for its own closed component resources |

System time is integer ps. A network boundary is an exact multiple of the
declared NoC period; the adapter advances Native in network cycles and converts
progress clocks back to ps. DRAM and compute periods remain separate. A future
adapter must preserve the kernel's same-boundary order: network arrival/delivery,
native memory progress, local completion/admission, new transfers and supplies,
then subsequent network execution. A frequency conversion must not round an
event early or merge events whose order affects ownership or eligibility.

Frontend routes certify legal reachability; actual Native paths establish
executed routing. A future predictor must generate paths from its own state,
not import a completed S trace. Physical links and service identities must be
shared by C2C and memory traffic even where the system transport uses multiple
stages and finite gateways. Logical storage partitions cannot create interfaces,
DRAM service or buffers without a new declared inventory.

## Next integration gate, after core migration

R2.2 and R3 stabilize the component execution interface; they do not close the
mesh/routing, supply, delayed-commit or ps-clock gaps above. Generalizing those
behaviors requires a new registered contract and its own reference evidence.

The first integration should be a small compute mesh with one HB memory
request/response and an overlapping C2C payload, fixed physical identities and
explicit supply/receive delays. Include staggered supply and blocked receive
contrasts. Compare same-input component events first, then independently
generated closed-loop requests. Require identical legal paths where routing is
fixed, service/credit clocks, receive commits, packet acceptance, application
finish and final drain under the selected BookSim/Ramulator contract.

Do not replace the complete V3 application backend before that gate passes.
Measure the full system afterward using its profiling categories; a 23×
single-flow component ratio is not a system-speedup estimate. Python transaction,
DRAM transport, logging and audit costs can dominate. Any system macro proposal
needs its own safe boundary conditions and validation rather than automatically
extending the network rule to computation or memory.

The method question remains whether less execution work preserves meaningful
memory-placement, gateway and compute-mapping judgments. System validity,
reference equivalence, component compression and total cost are separate claims.
