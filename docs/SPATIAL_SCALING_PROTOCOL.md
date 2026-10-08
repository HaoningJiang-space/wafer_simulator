# Geometry-constrained scaling: locality versus controller load

Freeze physical/transaction/execution and U0/U1/S model semantics at `c8cb1a5`.
Runtime relocation is outside the simulated contract. All runs use hn072, never
eex005. Do not compare host speed to previous-server wall times.

Question: under fixed work and resources per compute tile, does increasing the
spatial extent change the locality-versus-controller-balance decision, and can
the aggregate representations predict its size and ordering? Bottleneck migration
is a hypothesis, not an acceptance condition.

## Fixed construction, before simulation

Use square sides 4, 6, 7 with the accepted 26×33 mm tile and a 300 mm circular
wafer. The existing legality validator must pass corners, HB alignment, ports,
stitch signals and link capacities. No edge exclusion, routing closure, timing
closure, power, yield or qualified manufacturing claim is added. 7×7 is only
an ideal-boundary geometric candidate.

Each compute tile retains its SRAM, compute rates, two banks, controller,
staging capacity, one HB link and neighboring C2C links. Aggregate compute,
bank and HB budgets therefore grow with tile count; central horizontal cuts
grow with array side. The physical I/O attachment remains the same edge port.
Register these totals explicitly; do not claim all resources scale equally.

Use the existing complete two-GEMM work: rows32, hidden128, one worker per tile,
1,048,576 MACs per worker, second GEMM on the next logical worker. No tensor
size/compute-rate scaling, truncation, extra artificial messages or new scheduler.
As in the accepted work, exactly one initial X is host resident, all other X
objects start in SRAM. This fixed one-object I/O exception is recorded at every
size; weak scaling is per-worker mathematical work/data size, not replicated
external-I/O demand. No result is interpreted as Llama training.

Three data layouts, computed only from logical row/column:

- `local`: each bank object is at its consumer's tile.
- `clustered_local` (A): consumer `(r,c)` uses controller
  `(2*floor(r/2), 2*floor(c/2))`. Every 2×2 group shares one nearby controller;
  odd edges form smaller groups. Maximum distance two mesh links.
- `remote_balanced` (B): consumer `(r,c)` uses controller
  `((r+floor(side/2)) mod side,c)`. This is a bijection, balances controller work,
  and deliberately moves it farther away. There is no performance-driven search.

Keep first/second weights in banks0/1 and outputs in bank0, as before. SRAM,
compute assignment, logical dependencies, host placement and resources are
identical across layouts. A and B trade distance for controller load with the
same installed budget. Local is a reference case, not a fourth optimized design.

Each worker accounts for 147,456 controller payload bytes. A's largest 2×2 group
therefore requests at most 589,824 bytes across whole-operation reservations,
less than the unchanged 1 MiB controller staging capacity. Before any run,
sum **all** initial objects and **all** operation reservations simultaneously
per memory region and require this upper bound to fit every capacity. This
prevents the prior conservative staging bottleneck from dominating the tradeoff.
Verify zero capacity waits after execution; a failure blocks interpretation.

## Matrix, references and acceptance

3 sizes × 3 layouts × 3 models = 27 cells; 3 independent fresh processes per
cell = 81 full executions. Freeze every input and preflight identity before
running. Rotate model order over repetitions. Same native binary as the
accepted study, same seed and logging policy. Reuse the existing full service,
dependency, byte/path, storage, retirement and projected-resource audits.
Replay one actual native command stream per cell; repeated execution hashes
must agree. For 4×4 local/remote S, require the accepted 23,903/27,096 cycles and
exact complete-event hashes. No new network or endpoint model.

Decision criteria remain explicit: 100-cycle near-equivalence/gap budget and
2% absolute-time budget; report raw signed errors too. Evaluate every layout
pair, with A–B the primary tradeoff. Include false ties and candidate-set regret;
do not force a winner or require a ranking reversal.

## Bottleneck and cost evidence

Report makespan, normalized weak-scaling time and MACs/cycle (aggregate and per
worker), observed critical-chain compute/memory/network/capacity intervals,
controller/bank/SRAM service utilization and queued requests. For S report
actual HB/C2C link traversals, most-loaded directed links and finite-window
activity, endpoint injection waits and critical message routes. Network-chain
durations spanning HB and C2C cannot be uniquely divided into component delay.
Busy ratios and chain shares expose pressure; without a resource intervention,
do not promote them to proof that increasing one capacity improves makespan.
If no migration is supported, report that negative result.

Measure graph/binding build, native initialization, execution, serialization,
audit and replay separately. Record CPU, process RSS and logical/native event
counts. Every process is fresh. Execution cost includes native IPC and logging;
coarse models emit fewer detailed events. Evaluate whether S remains practical
on the three tested scales, without claiming asymptotic performance from them.

Close with the tradeoff decision, abstraction error and cost envelope. A larger
configuration count alone is not a simulator-method contribution. Do not add
DRAM microarchitecture, FIFO, NoC, collective algorithms, thermal, yield or
runtime optimizations to this milestone.
