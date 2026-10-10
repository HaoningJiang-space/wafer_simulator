# Repeated causal service patterns exist; batching remains unimplemented

The read-only audit found sustained, repeatable causal service structures in
all three selected G1 cases. Complete instrumented predictions match the
accepted independent G1 predictions. The opportunities include VC ownership,
FIFO ordering, live flit metadata, in-flight data, credit feedback and allocator
state; they are not inferred from throughput or an assumed AB alternation.

This supports a bounded service-pattern batching experiment. It does **not**
establish a correct batch-update algorithm, runtime improvement, application
accuracy or general network support. No Native execution or skipped cycle was
introduced. The exact G1 predictor bytes remain pinned and unchanged.

## Checked result

Run on hn072 / `ee4e072`, source
`6a5b8d64a4c4d757f8439ad4e799df21d1a954b8`, following the
[registered protocol](../../CAUSAL_COMPRESSIBILITY_PROTOCOL.md) and
[fixed controls](../../../configs/causal_compressibility.json).

| Case | Total cycle boundaries | Repeated periods | Covered elapsed cycles | Covered service-bearing cycles |
|---|---:|---|---:|---:|
| single-long, capacity 32 | 2,110 | 2 cycles | 1,821 / 2,110 (86.30%) | 1,821 / 2,091 (87.09%) |
| merge-0, capacity 32 | 6,206 | 8, then 4 cycles | 5,056 / 6,206 (81.47%) | 5,056 / 6,187 (81.72%) |
| tight-credit, capacity 2 | 7,515 | 78, then 39 cycles | 6,852 / 7,515 (91.18%) | 2,104 / 2,308 (91.16%) |

Coverage is the union of observed repeated intervals, not a sum of overlapping
phase-shifted chains. A service-bearing cycle contains at least one VC commit,
switch commit or output send anywhere in this four-router component. It is not
the same as every active/blocked allocator cycle or a Native profiling counter.

| Case / phase | Union interval, half-open | Longest same-phase chain | Per-period injections / ejections |
|---|---|---:|---|
| single-long | [166, 1987) | 910 repetitions of 2 | 1 / 1 |
| merge-0, all sources issuing | [482, 3882) | 425 repetitions of 8 | (1, 1, 2) / (1, 1, 2) |
| merge-0, source 2 finished | [4336, 5992) | 414 repetitions of 4 | (1, 1, 0) / (1, 1, 0) |
| tight-credit, all sources issuing | [245, 4843) | 58 repetitions of 78 | (1, 1, 2) / (1, 1, 2) |
| tight-credit, source 2 finished | [5122, 7376) | 57 repetitions of 39 | (1, 1, 0) / (1, 1, 0) |

Half-open union endpoints can differ from a representative same-phase chain by
up to one period because different phases overlap. The shared (1,1,2) progress
comes from the executed state machine. It is neither a fitted flow weight nor
a substitute for eligibility/ownership/credit state.

The 78-cycle primary tight-credit period retains substantial blocking. Its
progress includes source stall deltas (77,77,76), router stall deltas
(74,74,70,0), 36 local service boundaries, 12 arrivals, 16 credit returns,
12 sent credits and 242 allocation records. Credit feedback therefore changes
the pattern length without eliminating repetition in this fixed component.

## What actually repeats

There were **zero strict normalized state repeats** after finite remaining
work was included. A source suffix shrinks and destination pending counts
change. Treating those counts as equal would be an invalid memoization rule.

What repeats is the normalized causal control kernel together with an identical
affine progress delta and ordered emitted boundaries. The kernel preserves all
router queues, owners, eligibility, pointers, credit balances, complete ordered
in-flight events, source state, epochs and live route/time metadata. Pending
homogeneous source suffixes retain their explicit lengths as separate guards.
No unarrived flit is made eligible and no future credit is used early.

Each accepted chain has at least three consecutive observed periods with equal
kernel, period, progress and output. The output comparison includes service,
arrivals, credits, allocation snapshots, source injection and destination
ejection, with only time translation and within-message ID translation.
Different message identities remain distinct.

Tail and timeout bounds are explicit. The representative chains end near a
tail, so their reported *additional periods at that final boundary* are zero;
that does not erase the hundreds of already verified interior repetitions.
The warm-up, changes in source population, tails and final credit drain are
outside steady interiors and must resume normal execution in a future method.

## Acceptance and cost

- Six audit regressions pass. They check observational equivalence, necessary
  state distinctions, remaining-work semantics, overlap accounting, idle
  exclusion and a changed credit output despite repeating state.
- Saved-state readback passes all three cases, authenticating eight audit
  artifacts, exact source identities and the original G1 manifest. It
  recomputes periods, progress, outputs and coverage from saved states.
- Three saved-data negative probes are rejected even after recomputing all
  affected hashes: wrong remaining-work guard, duplicate cycle boundary and
  incorrect coverage summary. These are separate from the six regressions and
  the prior G1 audit's 19 faults.
- Native executions: zero. Skipped cycles: zero. Compression implementation:
  absent. No application execution or expanded message benchmark occurred.

| Case | Instrumented state capture | Pattern analysis |
|---|---:|---:|
| single-long | 1.096 s | 0.606 s |
| merge-0 | 8.854 s | 4.051 s |
| tight-credit | 1.750 s | 3.422 s |

These times describe audit overhead only. They exclude state-file writing and
whole-process overhead, and cannot be interpreted as simulation acceleration.
The test receipt records Python 3.13.16 and the same executable SHA-256 as G1.
The original G1 environment, demand, contract and complete prediction hashes
remain pinned. All three observed predictions match their saved full results.

Normalized state streams (about 0.32 / 7.42 / 0.85 MB compressed) remain on the
server in `runs/causal-compressibility-002`. The source's earlier diagnostic
capture `runs/causal-compressibility-001` and its test receipt are preserved;
the final receipt adds independent readback and saved-data negative checks.
Final tests/readback/negative directories have the corresponding `-002`
suffix. Compact copies and byte identities are in
[PUBLISHED_COPIES.json](PUBLISHED_COPIES.json).

## Next bounded question

The hypothesis is worth pursuing in the registered component: sustained busy
service and blocked feedback both have substantial observed repetitive
interiors. A future implementation must derive guarded batch updates for
queues, owners, pointers, credits, in-flight events and counters, then compare
each batch end state and expanded boundary sequence with ordinary G1 execution.
It must stop before external generation, source/destination tails or timeout.

Start with the verified 2-cycle single-flow pattern; only then test the
8/4-cycle merge and 78/39-cycle credit-limited patterns. Retain all seven G1
cases for accuracy, and separately measure longer-message execution and compact
representation cost. These are next-step requirements, not results of this
audit, and no new implementation is included here.
