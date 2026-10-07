# Target resources for the fixed-state WoW comparison

This describes the model already used by M0 and M1. It separates identities
recovered from the capture from target-resource assumptions. It does not
calibrate GPU computation to a wafer. Checked against the accepted artifacts
on eex005 on 2026-10-07; no new simulation was launched.

## From source identity to target location

The historical ATLAHS generator's GPU iteration order, with `unique_nic=True`
and source-host order `[2, 0, 3, 1]`, establishes the source GPU to `(host,NIC)`
association. Complete correspondence to the published GOAL provides its
evidence; NIC identity is not inferred from a CPU-lane number.

The target association is a declared experiment choice: sort the 20 compute
endpoints by `(layer,y,x)` and assign the 16 sorted `(host,NIC)` identities to
the first 16. One source GPU communication identity occupies one target compute
reticle. The same rule is used in both placements; physical endpoint IDs need
not be equal. M0 and M1 have exactly the same association within each placement.

| Source parser GPU | GOAL host | NIC | Baseline endpoint | Rotated endpoint |
| ---: | ---: | ---: | ---: | ---: |
| 8 | 0 | 0 | 0 | 0 |
| 9 | 0 | 1 | 1 | 3 |
| 10 | 0 | 2 | 2 | 1 |
| 11 | 0 | 3 | 3 | 4 |
| 0 | 1 | 0 | 4 | 2 |
| 1 | 1 | 1 | 5 | 5 |
| 2 | 1 | 2 | 6 | 8 |
| 3 | 1 | 3 | 7 | 6 |
| 12 | 2 | 0 | 8 | 9 |
| 13 | 2 | 1 | 9 | 7 |
| 14 | 2 | 2 | 10 | 10 |
| 15 | 2 | 3 | 11 | 13 |
| 4 | 3 | 0 | 12 | 11 |
| 5 | 3 | 1 | 13 | 14 |
| 6 | 3 | 2 | 14 | 12 |
| 7 | 3 | 3 | 15 | 15 |

These GPU numbers are parser identities, not CUDA device ordinals. The
[32-row resource table](results/model-boundary-001/target_resource_mapping.csv)
also gives router, layer, physical coordinates and endpoint-to-router latency.
It joins the accepted `TRANSFORMATION.json`, `contract.json` and `network.json`;
their hashes and the M0/M1 equality checks are in
[DELIVERY.json](results/model-boundary-001/DELIVERY.json).

All 1,337,280 recovered pairs connect distinct source GPUs. The injective target
mapping therefore makes each a cross-reticle transfer, even though both ends
were on the same original host. There is no remaining target-local transfer
class in this particular recovered set. A future many-to-one mapping would
require a separate local-transfer rule; the current lowerer rejects same-endpoint
messages instead of silently assigning them zero cost.

## What executes each kind of work

| Work | M0 resource and completion | M1 resource and completion | Evidence or remaining assumption |
| --- | --- | --- | --- |
| Measured event-group interval | Original `(host,CPU)` lane for unchanged duration | Same | Source boundaries known; internal timing is composite and not target-calibrated |
| Reduction, copy, combined reduction/copy | Same lane, original published model duration | Same | Author model-call category identified; GPU-derived cost not recalibrated |
| Source-supported intra-host transfer | Separate original send/receive `calc` costs on their lanes | One explicit network message and a zero-duration receive join | Peer, size and original requires relation recovered; target cost is a modeling intervention |
| Original inter-host transfer | Explicit network message | Same network mechanism, now competes with recovered traffic | Original identity, size and dependencies preserved |
| Zero-duration synchronization | Complete after prerequisites and lane availability | Same | No invented compute or communication service |
| Unexplained contents of a measured interval | Retained within original duration | Same | Neither omitted nor reclassified as pure computation or waiting |

The 164 lanes are **virtual replay serialization resources**, indexed as
`host * 41 + cpu`. A positive-duration calc reserves its lane from scheduled
start to finish, with FCFS in deterministic dependency-ready callback order.
The execution model does not bind these lanes to calibrated reticle ALUs,
copy engines or SRAM ports. GPU identity provides location provenance; it does
not supply such hardware capacity or service-rate calibration. Independent
lanes do not acquire a shared reticle compute or memory resource.

For a send, all prerequisites and lane availability must be satisfied before
it is offered to the endpoint. CPU issue overhead is zero, and transmission
does **not** hold the CPU lane. Completion occurs only after **all** message
flits arrive, not at generation, first injection or arrival of a tagged last
flit. The matched receive completes only after that send, its other local
prerequisites and its own lane availability. Neither operation reserves a
finite application output or receive buffer: data residency, buffer lifetime
and receiver-consumption backpressure are outside this model.

Replacing a transfer calc therefore changes its resource occupancy as well as
its time: an old CPU-lane reservation becomes asynchronous network service.
This is part of the declared M0/M1 boundary, not an additional simulator
optimization. An eventual static target-cost comparator must preserve M1's
issue and completion semantics; putting a static delay back into an ordinary
CPU-holding calc would confound resource ownership with network competition.

## Which network resources a message uses

The pinned author exporter provides one injection endpoint and a central router
per compute reticle in trace mode. For these placements the endpoint channel
latency is 6 cycles, based on average distance to the reticle center. The LoI
interconnect layer is represented by the author's exported router/link graph.
Inter-reticle links combine in-plane distances and a one-cycle hybrid-bonding
term; bonding is not an independently scheduled controller or separate budget.

A transfer uses its source endpoint, permitted router/link path, destination
router and destination endpoint. The author's cycle-breaking routing and
adaptive selection choose paths during execution. The endpoint table specifies
locations, not a measured per-message router path. Current completion logs
cannot identify the particular port/VC responsible for a message's delay.

The native configuration uses 1 GHz, 2000-byte flits, single-flit packets,
1 VC with 32-flit router buffers, four-cycle router pipelines and one flit per
cycle at a unit-speed link (2 TB/s). Flit count is `ceil(bytes/2000)`; padding
consumes transmission capacity. Credit and switch/VC arbitration constrain
network injection and forwarding. Messages at one source share its injection
stream; a new message is generated when the previous message's staging queue
has emptied. The ready-message and generated-flit staging queues are software
queues, not capacity-calibrated SRAM. Network credit does not model application
storage availability at the receiver.

| Physical/model quantity | Baseline | Rotated |
| --- | ---: | ---: |
| Compute endpoints / active endpoints | 20 / 16 | 20 / 16 |
| Exported routers | 124 | 100 |
| Undirected links | 232 | 226 |
| Aggregate directed link capacity, bits/cycle | 7,424,000 | 7,232,000 |

These are the original two configurations, not equal-cost designs. Geometry
and link parameters are reused from the pinned author implementation; this
does not establish detailed routing feasibility, SRAM capacity feasibility or
native training throughput.

## Implementation and evidence locations

- Source association and transfer substitution:
  [local_transfers.py](../src/wafer_sim/workloads/local_transfers.py),
  [source report](LOCAL_STAGE_PROVENANCE.md).
- Geometry and endpoint ordering: [wow.py](../src/wafer_sim/adapters/wow.py),
  author [exporter at the pinned revision](https://github.com/spcl/nw-design-for-wsi/blob/9470042fb2d8b5368556e46cc75ac818dbf31522/export_to_rapidchiplet.py).
- Lane IDs, dependency predicates and messages:
  [goal_booksim.py](../src/wafer_sim/adapters/goal_booksim.py).
- Issue, completion, credit and event semantics: frozen
  [native patch](../patches/booksim-wafer.patch) and pinned author BookSim.
- Controlled comparison and its claim boundary:
  [M0/M1 protocol](MODEL_BOUNDARY_PROTOCOL.md).
