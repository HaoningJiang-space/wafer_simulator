# Target resources now determine execution time

Executed and independently checked on **eex005, 2026-10-07**, at source commit
`42bb6b4`. This is the first complete execution driven by the target compute,
memory-port and directed-network resource calendar. No source-machine `calc`
duration is replayed, and no caller manually supplies phase completion times.

The workload is a fully declared analytical unit:
`A → {B0, B1} → SUM AllReduce → {C0, C1}`. Every tensor is 16 bytes. It includes
six logical operations, thirty phases and forty-two resource services. Both B
tasks fetch A's result across a shared directed link. AllReduce gathers two
inputs, performs four additions and writes both output homes before either C
begins. Its root/participants, work, bytes and global completion policy are
explicit. The [configuration](CONFIG.json) and [complete base event record](declared.json)
are included; this is not a sampled Llama trace or a native wafer benchmark.

## Measured simulator output, checked against hand-derived schedules

All four cases keep logical work, task/data placement, memory capacity, routes
and propagation latency fixed. Each intervention changes one class of service
rates by exactly a factor of two; the network case changes endpoint and link
byte rates together.

| Model parameters | Complete unit, cycles | Change from base, cycles |
|---|---:|---:|
| Declared service rates | 113 | — |
| Compute rates doubled | 99 | −14 |
| Memory-port bandwidth doubled | 97 | −16 |
| Network endpoint/link bandwidth doubled | 93 | −20 |

This demonstrates that each target resource class can change completion time
without changing workload durations: the logical workload contains work
quantities, not durations. These differences are conditional effects of the
declared model. They do not establish a universal network bottleneck, and
cannot be added as independent shares of application time.

The base operation completion times are:

| Operation | Finish cycle |
|---|---:|
| A | 12 |
| B0 / B1 | 52 / 56 |
| AllReduce, both result writes complete | 105 |
| C0 / C1 | 113 / 113 |

At the initial fanout, B0's source read occupies the shared memory port from
12 to 14; B1's read waits and occupies it from 14 to 16. Their first shared link
services occupy 16–20 and 20–24; the second request becomes ready at 18 and
waits two cycles. Link propagation then elapses without retaining serializer
bandwidth. B tasks cannot compute until destination staging writes and local
reads complete. Region peaks are 32, 64 and 32 bytes, below each declared
128-byte capacity; only the two retained final outputs remain live.

## What is now implemented

The backend computes request start, resource release and result completion
times, arbitrates shared resource IDs, advances the event queue, retries
capacity-blocked admissions and invokes the existing lifecycle completion
callbacks. It records ready/admission/finish times, service work, paths,
resource predecessors, queue waits and storage use. A permanently blocked
allocation returns explicit shortages and no application completion time.

The network model is **whole-message store-and-forward**, with deterministic
minimum-hop routing and FCFS directed-link/endpoint serializers. It models
shared bandwidth and propagation; it does not model BookSim flits, credit
backpressure, finite router buffers or adaptive routes. All rates and capacities
here are analytical definitions, not calibrated WoW parameters. The existing
BookSim implementation and accepted M0/M1 results are unchanged.

## Validation and provenance

[80 related semantic regressions](tests.log) passed on eex005
([receipt](SEMANTICS.json)). New cases include hand-calculated compute and
memory service, shared and independent compute resources, two contending
flows, independent link directions, propagation versus serializer occupancy,
rational rates, full producer/consumer completion, capacity release/retry,
permanent shortage, and rejection of damaged timing/attribution records.

`analysis/timing.py` independently checks service rates and latency, per-resource
non-overlap, work and byte conservation, complete phase order, dependency-ready
times, resource-wait predecessors and regional allocation/release accounting.
It also reconstructs resource totals rather than trusting reported summaries.
The runner audits JSON-round-tripped records for every complete case.

[SUMMARY.json](SUMMARY.json) records all four schedules. [COMPLETE.json](COMPLETE.json)
hashes all case records, and [STARTED.json](STARTED.json) records source, input,
interpreter, packages and the passing test receipt. Full case outputs remain in
`/home/wangziheng/wafer_simulator/runs/timed-execution-001`.

No Chakra parser extension, mapping sweep, Mstatic full run, thermal or PDN
experiment was added. The latest priority was to finish this minimal target
timing capability first. Mstatic and a larger explicitly defined Transformer
execution unit remain separate next milestones.
