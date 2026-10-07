# WoW application simulation: accuracy and cost of network abstractions

Registered before new runs. The research variable is the **simulation method**.
Direct-root/tree are frozen validation inputs; no new algorithms, mapping search,
thermal, PDN, capture recovery or runtime optimization are part of this milestone.

## Existing evidence, no new simulation

Reconstruct/audit the 12 accepted direct/tree × Baseline/Rotated × 32/256/1024
cells. Report application signed/absolute errors and MAPE against live BookSim,
six placement ordering decisions, and absolute/relative gap errors. A near-zero
reference gap makes its relative error ill-conditioned; also report cycles and
error divided by reference Baseline time. Ties are distinct from ordering.

Both backends share workload, binding, local resources, scheduling and lifetime.
Coarse is FCFS whole-message store-and-forward with deterministic minimum-hop
lexicographic routing, **not** an independent-delay or no-contention model.
Native uses the pinned author's adaptive selection/cycle-breaking routing and
per-flit router, VC/credit model. Coarse serializes payload bytes rounded to
integer service cycles; native rounds to 2000-byte flits. At the current
2000 B/cycle channels these give equal isolated serialization cycle counts,
but native records padded wire work. No retrospective cause is called
"contention" without evidence separating route and granularity.

Match transfers by logical phase, report readiness, completion, service error,
coarse queue/serialization/propagation terms and actual native versus coarse
paths. Rebuild critical chains for both. This is observed attribution, not an
intervention that holds network-ready times fixed.

## Bounded extension and measurement

`configs/model_fidelity.json` preregisters exactly six complete block conditions:
TP2/TP8 × sequence 16/32/64, eight heads, batch 1, hidden 64, FFN 128.
Keep direct-root, Baseline, row-major, seed 1, 1 GHz, original network and
compute rates, 256 KiB per region, and **32 B/cycle memory** fixed. These are
declared analytical local resources, not measured GPU-like WoW reticles.
Geometry/link parameters come from the pinned author export. Sequence controls
tensor bytes via operator shapes; TP2 supplies low-overlap communication and
TP8 permits multiple ready gathers under the existing dependencies. No forced
simultaneous injections, arbitrary flit multiplier or infinite supply rate.
Capacity infeasibility is a result; do not expand memory or reduce work to hide it.

First measure the unchanged models, then decide whether a minimal correction
is justified. Do not promise a ranking reversal or a saturated cut. This study
does not vary topology, so new cases measure model error, not design rankings.

Measure sequentially on eex005 with a common two-CPU affinity and record load
and CPU identity. Use three repetitions; alternate backend order. Cold trials
start a fresh Python worker and rebuild input/graph/binding. Reuse trials retain
those immutable objects for three executions in one worker. Each native execution
still creates a new BookSim process; this is **graph reuse**, not native network
reset/reuse. Report common geometry export separately and do not hide it in one
backend. Cold launch wall time includes interpreter/import cost; phase timings do
not. Three samples support observed ranges/medians, not statistical significance.

Separate graph build, network config/startup, timed execution, native close and
its JSON serialization, execution-result serialization, independent audit, and
standalone timestamp replay. Normal native protocol flushes and full flit logs
remain enabled, while coarse retains its full service log. Report actual artifact
bytes. The execution-cost ratio includes their different observability/IPC costs;
it is not a claim of a new or pure simulation-algorithm speedup.

Record Python CPU using `getrusage`, live native CPU from `/proc/PID/stat` (with
clock-tick resolution), and exact exited-child CPU via `RUSAGE_CHILDREN` after
close. Native per-phase CPU is quantized; use total child CPU for robust totals.
Peak RSS is a process lifetime high-water mark, not a phase delta. Record Python
and native separately before audit/replay. Sum of their maxima is a conservative
upper bound, not a measured simultaneous peak. Reuse-worker RSS is cumulative
across executions; cold process observations provide independent per-trial peaks.
Do not attribute audit/replay memory to the backend execution peak.

Accept only complete output and independent timing/lifetime audit, native flit
conservation, standalone interface agreement, stable repeated simulated events,
and identical workload/target/policy across the two backends. Publish hashes of
source, binaries, environment, inputs and results. Any failed/excluded condition
is recorded explicitly, and does not count as a completed accuracy/cost sample.

## Decision

Report what simple models already preserve, where service/gap errors occur, and
what measured cost is saved. A route difference is not a pipeline error. A model
change is justified only after a particular omitted behavior is isolated. If
the bounded cases do not isolate one, retain the existing models and state that
no new approximation has been validated. Reference accuracy is relative to
BookSim under this shared execution contract, never real-wafer validation.
