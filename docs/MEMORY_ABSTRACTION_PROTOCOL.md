# Spatial storage abstraction: registered comparison

Baseline: `592d327`. Freeze the physical machine, 16-worker two-GEMM workload,
three existing layouts, request/response/ack protocol, whole-operation staging,
execution kernel, native binary and seed. No new workload or machine search.

| Model | Storage service and capacity | DRAM communication |
|---|---|---|
| S | Physical bank/controller resources | Existing live BookSim |
| U1 | Identical to S | Independent uniform unloaded one-HB cost |
| U0 | One pooled bank, channel and command resource; summed budgets | Same as U1 |

U0 preserves **each physical controller's staging capacity and reservations**,
including release at operation retirement. This common admission guard avoids
silently giving U0 a different staging policy. U0 is therefore a pooled-DRAM
approximation with a physical staging guard, not an entirely location-blind
memory oracle. Its projected aggregate capacity does not certify per-bank
feasibility. SRAM, host I/O and compute are unchanged. C2C and host traffic use
the original BookSim graph in every model.

Uniform communication duration is fixed before execution:

`ceil(payload / 64) + 2*access(1) + 2*router(4) + HB(1)` cycles.

This is a declared independent unloaded pipelined one-HB estimate, not fitted
to S. It preserves logical payload and padding accounting; it produces no fake
flit trajectories. No DRAM packet competes for native endpoints or links in
U0/U1. Thus U1–S includes distance, sharing, adaptive paths and their timing
interactions; it is not a distance-only intervention.

U0 sums 32 banks' capacities and bandwidths and 16 controllers' channel and
command rates. One shared FCFS resource per category prevents duplicating the
total budget for every requester. The common bank latency is retained. Integer
service rounding remains: pooling command throughput does not permit a request
to finish in less than one cycle. Resource pooling changes an abstraction,
not the underlying declared machine. The interpretation is optimistic access
to all bank/controller throughput, not a physically implemented uniform store.

Every model retains exactly the same task/data identities, computation, logical
transfers, phase dependencies, final-write/ack visibility and staging lifetimes.
Application differences may change realized capacity waits; the admission rule
does not change. Keep capacity waits separate from path and service durations.

## Acceptance and measurements

Run all 9 model/layout cells. Three cold process executions per cell; one further
process per cell reuses the compiled binding for three executions. Every native
network process is fresh, including in binding-reuse mode. This is **not** a
persistent warm BookSim measurement. Rotate model order between repetitions.
All 54 full executions must independently pass service, dependency, logical-byte,
storage and retirement audits. Re-read serialized results; identical results
are required across repetitions. S must exactly reproduce all three accepted
execution hashes. Replay one actual native command log per cell independently.

Measure graph/binding preparation, network config, native initialization,
execution, native close/log serialization, Python result serialization and
independent audit separately. Record Python CPU, exited native CPU, Python
lifetime RSS, live native peak RSS, affinity and host load. Initialization reuse
does not make lifetime RSS an incremental memory measurement. Execution includes
protocol/event recording; approximate models inherently generate fewer detailed
native events, so measured speedup is an end-to-end instrumented implementation
comparison, not proof of a faster algorithm under identical event volume.

Before running: use 100 cycles as the near-equivalence band and absolute gap-error
budget, and 2% as the application-time budget. These are declared study decision
criteria (100 cycles is about 0.4% of the accepted fastest execution), not a
hardware-accuracy confidence interval. Report raw values so other budgets can
be applied. Evaluate all three layout pairs, including ties. For the model's
set of near-optimal layouts, report minimum and maximum reference regret; never
silently select the reference winner from a predicted tie.

Deliver application errors, pairwise design-gap errors, selection disagreements,
regret, observed critical chain C/M/N/capacity decomposition and resource waiting.
Neither summed overlapping queue waits nor chain components are independent
causal effects. S is conditional on uncalibrated service and conservative staging
assumptions. This study cannot establish native hardware accuracy, general
wafer-scale superiority or necessity of detailed modeling in every case.
