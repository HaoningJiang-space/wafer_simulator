# Compute + memory wafer: first machine-integration acceptance

Checked on eex005, 2026-10-09. The machine is now defined independently of the
WoW LoI placement generator. Existing execution/storage/timing and native source
remain unchanged from `371aed2`; this milestone adds physical definitions,
transaction binding, independent audits and complete integration work.

This is a **declared candidate system**, not a calibrated DRAM/wafer product.
The [contract](../../WAFER_MACHINE.md) specifies numerical assumptions,
integration limits and whole-object transaction policy. It does not establish
model accuracy relative to a manufactured wafer or a uniform-memory model.

## What now belongs to the machine

The fixed 4x4 compute array has 16 finite SRAM regions, 32 spatial banks, 16
shared bank controllers, 16 HB connections, 24 lateral stitched connections and
one edge I/O link to external storage. There are 33 routers and 49 attached
communication endpoints. Memory-controller buffering is a separately budgeted
capacity pool, not an extra network endpoint or a free interconnect wafer.

Validation rejects lateral reticle links without stitching, nonadjacent stitched
links, illegal HB alignment, insufficient bond/router-port budgets and tiles
outside the wafer. These checks establish consistency of declared resources,
not PPA/yield qualification. Memory controllers occupy the declared memory
periphery; implementing that periphery in a DRAM process remains a design task.

Reads generate requests and return data; writes generate data and post-commit
acknowledgements. Requests, responses, C2C transfers and acknowledgements use
one shared, live native BookSim network. Controller command service, bank
service and shared data-channel service all precede the corresponding response.
Objects become visible only after required writes/acknowledgements.

## Complete same-work acceptance

All three cases finish the same 32 dense float32 GEMMs on 16 logical workers:
`Y_i = (X_i W_i) V_i`, with the second GEMM assigned to the next worker.
Rows=32, hidden=128. The total work is 16,777,216 MACs. One initial input uses
off-wafer storage; other inputs start in SRAM. Weights and final results reside
in banks. Only bank-home placement differs between cases; compute placement,
logical work, rates, capacities, physical graph, policy and seed are fixed.

| Data placement | Application cycles | Critical compute | Critical memory | Critical network | Critical capacity wait | Stitched-link flit traversals |
|---|---:|---:|---:|---:|---:|---:|
| Near consumer | 23,903 | 4,096 | 14,014 | 5,793 | 0 | 7,680 |
| Half-array offset | 27,096 | 4,096 | 12,902 | 10,098 | 0 | 81,504 |
| One controller | 75,032 | 4,096 | 37,478 | 9,411 | 24,047 | 118,416 |

Each case has exactly 33 read requests, 33 data responses, 16 C2C messages,
16 data writes and 16 write acknowledgements: 114 messages, 41,265 native
64-byte flits. Useful data totals 2,637,824 bytes; request/ack bytes total 784.
Padding is additional network service, not logical tensor work. HB traversals
are 36,912 flits and I/O traversals 257 in every case.

The offset case exposes longer horizontal paths while preserving HB/I/O work.
The concentrated case exercises shared banks, controller channel and staging
capacity. Its controller-0 channel has 4,466 aggregate wait cycles; bank-0 has
252,756 aggregate wait cycles. These overlapping per-request waits are **not**
additive application delays. The observed critical chain separately closes to
75,032 cycles. In particular, 24,047 cycles of capacity wait reflect the declared
conservative policy of retaining controller staging until operation retirement;
they are not an inevitable physical DRAM penalty.

This demonstrates the data-path and resource-binding capability. Moving data
changes the actual execution being simulated; it is not an accuracy comparison
between two simulation methods and is not a general placement ranking.

## Acceptance and source identities

* Complete native execution: `0c56c24`, three registered cases, no truncated work.
* 183 related Python/native-interface tests passed before execution. Final
  source organization at `7693eaa` passed all 183 again; see [SEMANTICS.json](SEMANTICS.json)
  and [tests.log](tests.log).
* Three independent full-event audits check service rates/queues, lifetimes,
  capacity, logical byte/work conservation, request/service/response ordering,
  post-write acknowledgements and actual physical packet paths.
* Three native command/reply replays passed: 470, 497 and 553 commands.
* [VERIFIED.json](VERIFIED.json) records a fresh remote readback of all 65 run
  artifact hashes. Current compiled workload, placement, physical target,
  service rates, reservations and every phase match the accepted inputs exactly
  after separating workload roles from placement. Critical-chain and execution
  audits reproduce the saved results. This was readback, not another application run.

[SUMMARY.json](SUMMARY.json) contains times, paths, control/data counts,
per-stage measurement and status. [STARTED.json](STARTED.json) pins complete
machine/workload, source, binary, environment and registration identities.
[COMPLETE.json](COMPLETE.json) contains hashes of the **remote** raw artifacts;
their presence here does not mean those large event files were downloaded.

Execution wall times were about 1.17 / 1.84 / 2.33 seconds in these single
acceptance runs. They do not form a simulator-speedup benchmark. Initialization,
serialization, audit and command replay are separately recorded; Python RSS
is lifetime peak and native CPU is reported after process exit.

Raw results: `/home/wangziheng/wafer_simulator/runs/wafer-machine-001`.
Final test receipt: `runs/wafer-machine-tests-003`.
Fresh independent readback: `runs/wafer-machine-audit-001`.

## Scope and next comparison

Banks use analytical byte service and post-service latency, with no DRAM row,
refresh or command-level timing. SRAM/controller capacities are checked;
streaming RX-slot capacity is explicitly **unmodeled** in this whole-object
contract. Internal PE NoC, hardware calibration and physical cost closure are
not claimed. Collective-to-DRAM transactions are rejected by the new adapter.

The next model study should hold this machine and work fixed and define exactly
what a uniform-memory approximation omits. Compare prediction error and cost
against the spatial transaction reference without simultaneously changing data
placement, controller policy or bandwidth. The accepted LoI results remain
separate; no new FIFO/collective/thermal mechanism is required by this milestone.
