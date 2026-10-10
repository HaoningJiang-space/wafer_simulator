# R3: single-flow macro on the explicit causal core

Accepted execution source: `be45fff9f41e688761a7bc2aea3900f7eb995315`.
All new tests and predictions ran on hn072. There were no new Native or
application runs. Original G1, AST G2.1 and their accepted evidence are unchanged.

The [84-test receipt](TESTS.json) includes overlapping core, progress, evidence,
legacy macro and new explicit-rule regressions; counts are not additive.
[Independent readback](VERIFIED.json) checks nine frozen accuracy cases, 14 full
macro entry/exit states, 27 raw cost workers and 266 artifacts. All flit, service,
allocation, credit, message and drain events match original G1 and accepted G2.1.
Macro-off Full and macro-on Full/Compact/Counters final semantic states match.
Compact expands through the independent evidence reader. Event insertion IDs
and next-sequence match at every compared macro boundary.

The runner calls the ordinary explicit `step_one_cycle()` body. Its source
range/lazy live metadata preserve eligibility and order. The guarded period-2
transition has no AST rewriting, dynamic compilation or analysis dependency.
Full validation expands repeated evidence during execution; timed Counters and
Compact modes do not. The rule leaves tails, external demand and deadlines out
of its jump. It does not support merge, tight-credit or a general mesh.

| Flits | Logical cycles | Actual updates | Off worker median | On Counters median | Speedup |
|---:|---:|---:|---:|---:|---:|
| 1,024 | 2,110 | 296 | 0.142 s | 0.135 s | 1.05× |
| 8,192 | 16,446 | 296 | 0.622 s | 0.134 s | 4.66× |
| 32,768 | 65,598 | 296 | 2.289 s | 0.129 s | 17.77× |

These are three shuffled repetitions per size/mode, same explicit core and
Counters output, with the blocking worker wall time measured end to end.
32,768-flit Compact worker median is 0.159 s; independent expansion is outside
timed prediction. Small cases show that fixed recognition/startup cost matters.
The old prototype's 23.02× is retained as its separate result, not reused here.
Neither ratio is a speedup over BookSim or a complete wafer application.

Two preliminary readbacks failed on validation representation/identity checks:
JSON integer-map keys versus in-memory keys, then a virtual-environment launcher
versus its resolved interpreter. Both were corrected, fresh campaigns retained,
and the final raw records passed independent readback. Profiling also identified
deep-copy normalization in the bounded key; the replacement keeps an explicit
complete metadata inventory and rejects unknown fields. No physical service
rule or fitted rate changed.

Raw accepted campaign: `/Projects/haoning/wafer_simulator/runs/causal-macro-transition-003`;
tests: `causal-macro-transition-tests-003`; readback:
`causal-macro-transition-readback-003`. Failed campaigns `-001`/`-002` and their
diagnostics are preserved, excluded from accepted costs. The [published copies](PUBLISHED_COPIES.json)
were byte-verified against server originals. The accepted manifest is
`bb1fb863a3020fbcb8db2eb970ed413ac64b4171077016c24016188bd50fe20b`.

The final ordinary core also passed the seven-component, three-evidence-mode
[supplementary readback](../causal-evidence-001/final-core/VERIFIED.json): 30,604
boundaries and 10,787 flits, identical to the original R2.2 result. G2.2/G2.3 are
not started. Further work targets system execution in `w2w-memory` under a
separate compute/DRAM/network contract.
