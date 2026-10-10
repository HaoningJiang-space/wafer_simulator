# G2.1: exact guarded single-flow batch transition

Accepted execution source: `17abfedae89f935e9ae929803d121848507992c5`.
All new tests and executions ran on hn072 (`ee4e072`). This closes G2.1 only:
one source-0 message to endpoint 3, the unchanged primary four-router contract,
single-flit packets and 32-flit buffers. No Native or application execution was
started. Original G1 source and accepted evidence are unchanged.

## Accuracy and state

The final receipt records 11 regressions, nine accuracy cases and 36 controlled
cost workers. Independent readback checked 274 artifacts. Eight real-evidence
fault injections were rejected. Earlier test receipts overlap with the final
suite and must not be added to it.

| Flits / ready | Logical cycles | Actual cycle updates | Skipped cycles |
|---|---:|---:|---:|
| 1 / 0 | 64 | 64 | 0 |
| 64 / 0 | 190 | 190 | 0 |
| 127 / 0 | 316 | 296 | 20 |
| 128 / 0 | 318 | 296 | 22 |
| 1,024 / 0 | 2,110 | 296 | 1,814 |
| 1,025 / 0 | 2,112 | 296 | 1,816 |
| 2,049 / 0 | 4,160 | 296 | 3,864 |
| 8,192 / 0 | 16,446 | 296 | 16,150 |
| 1,025 / 37 | 2,149 | 333 | 1,816 |

Complete expanded predictions equal unmodified G1, including 13,635 flit
records, 122,715 local service boundaries, 81,810 allocation records, arrivals,
credit returns/sends, stalls, peaks, message finishes and final drain. Macro
disabled predictions also match. Fourteen macro entry/exit checkpoints match
independently captured original G1 states. Saved compact records are restored
without rerunning the candidate; all nine compact cost records, including
32,768 flits, also expand exactly to fresh original G1 predictions.

For 1,024 flits the detected macro starts at boundary 172, repeats 907 periods,
and exits at 1,986 with one source flit and 55 receiver flits remaining. Neither
the tail nor the credit drain is skipped. Message finish is 2,096, final drain
2,110; the one-flit case retains finish 50 and drain 64.

## Why the jump is guarded

The complete state does not repeat. A causal kernel recurs while finite work
and cumulative progress change. The kernel retains ordered FIFOs, ownership,
exact deadlines, pointers, credits, source eligibility and ordered in-flight
events plus live packet metadata. A two-cycle period advances one injection
and one ejection, with a fixed service/credit template.

Within the supported homogeneous, single-message region, the original service
rules commute with translation of clocks and live flit labels: decisions use
resource state and relative deadlines, and packet roles remain identical.
Generation epochs remain fixed. Three matching observed periods check the
implementation/template, but are not the sole justification for future jumps.
The structural guard excludes other requests, depleted work and changed credit
eligibility. The repeat bound is
`min(source_remaining-1, receiver_remaining-1, (cycle_limit-now-1)//2)`.
Induction over that guarded region licenses the affine translation; source
empty, receiver completion and deadline exits remain outside it.

The macro translates the bounded live frontier and adds repeat descriptors;
it does not construct one dictionary per skipped service event. Ordinary
execution handles the tail. This prototype mechanically derives its core from
SHA-pinned G1; the derived ordinary source is archived. It is not yet the
explicit-state transition API proposed for R1. The expanded G1-compatible
projection preserves its legacy scope string for exact comparison; the outer
compact record explicitly identifies the G2.1 producer.

## Measured costs

Unprofiled workers used CPUs 18/19, shuffled order and three repetitions per
size/mode. Parent wall time uses blocking waitpid with a separate watchdog;
GNU time CPU/RSS and raw start/end/exit/input identities are checked. The
primary algorithm comparison uses the same derived core and identical
counters-only outputs, with macro disabled/enabled.

| Flits | Off prediction s | On prediction s | Off worker s | On worker s | Worker speedup | Reconstructable compact worker s |
|---|---:|---:|---:|---:|---:|---:|
| 1,024 | 0.072124 | 0.037860 | 0.120289 | 0.085897 | 1.40× | 0.093105 |
| 8,192 | 0.490489 | 0.037992 | 0.538858 | 0.085689 | 6.29× | 0.093414 |
| 32,768 | 1.923619 | 0.037803 | 1.972071 | 0.085657 | 23.02× | 0.093378 |

At 32,768 flits, 65,598 logical updates become 296 actual updates. Same-core
prediction speedup is 50.89×. Worker ranges are 1.970521–1.999991 s off and
0.085507–0.085700 s on. Median RSS is 21,396/21,720 KiB respectively; process
CPU is 1.96/0.08 s. The compact-evidence worker uses 23,808 KiB and writes
731,805 bytes, with serialization included in its worker cost. Compact output
sizes at 1,024/8,192 flits are 729,214/730,995 bytes.

Original G1's 32,768-flit worker is 2.084656 s and 319,008 KiB, but it internally
materializes full evidence. That comparison combines recording/storage and
macro benefits; it is not the primary isolated algorithm ratio. Full expansion
and independent audit remain proportional to event count and are outside the
timed prediction/worker measurements. No speedup over BookSim S, full validation
workflow, application execution or general network is claimed.

## Provenance and preserved attempts

Final raw evidence: `/Projects/haoning/wafer_simulator/runs/causal-macro-single-003`;
independent readback: `causal-macro-single-readback-003`; tests:
`causal-macro-single-tests-004`; negative checks: `causal-macro-single-negative-002`.
[PUBLISHED_COPIES.json](PUBLISHED_COPIES.json) records byte lengths, hashes and
server paths of the published receipts. [RESULTS.json](RESULTS.json) contains
medians/ranges; [VERIFIED.json](VERIFIED.json) links the campaign manifest.

Earlier campaigns and receipts remain on hn072. Campaign 001 passed accuracy
but used timeout-polling process waits; its quantized worker timings are
excluded from the final cost table. Campaign 002 corrected the wait and used
the three counters modes. Campaign 003 adds the separately measured,
reconstructable compact mode. No older accepted evidence was overwritten.

G2.1 now demonstrates actual exact computation skipping in this bounded
single-flow contract. Multi-source merge, credit-limited macros, generalization
and algorithm novelty remain separate questions. R1 will preserve this
prototype and G1 as references while exposing state and one-cycle rules.
