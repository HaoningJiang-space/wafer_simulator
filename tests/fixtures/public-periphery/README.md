# Pre-refactor semantic baseline

Captured on hn072 with clean `f91824d171917e0e58824b97a1d2a2bff2e4cf51`, before
the public API extraction. `EXPECTED.json` contains complete input/result/audit
digests for ten periphery cases and one rank-local collective, plus individual
event/state section digests. The complete pipeline-read input, execution and
audit are included for direct portable readback and full equality checks.

This is the existing pure Python whole-message network backend. These timings
are semantic fixtures, not native S application results or hardware validation.
The cases exercise bank/controller interfaces, whole/pipeline, remainder and
window reuse, reads/writes, concurrent banks, sequential operands, external
memory, consumers and capacity blocking. Event array hashes preserve order;
the checks cover phases, service events, output publication, operations, storage,
resource accounting and peaks, rather than only makespan.

`COMPLETE.json` is the original server completion receipt; some listed files
remain server-only at `runs/public-api-baseline-002` under
`/Projects/haoning/wafer_simulator`. Capture tools live in
`runs/public-api-baseline-tools-002`; their hashes are in EXPECTED. The script
`scripts/capture_public_baseline.py` requires the pinned old checkout, and must
not regenerate expectations from the new implementation to make tests pass.
