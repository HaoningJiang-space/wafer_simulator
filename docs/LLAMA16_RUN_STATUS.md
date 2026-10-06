# Full-capture run receipt — 2026-10-06

Status: **full runs 002, 003 and 004 executing; no application-performance result yet**.

- Host: `wangziheng@eex005`.
- Run: `/home/wangziheng/wafer_simulator/runs/llama16-full-002`.
- Driver log: `/home/wangziheng/wafer_simulator/logs/llama16-full-002.log`.
- Core implementation commit: `b6371ab`; the per-run `provenance.json` records
  the exact source commit including the wall-budget amendment.
- Native binary SHA-256:
  `a44b9af3c35f8f0924d2c4a8047bb2b472919b3822ca275f2dbebc9a2cb6fdac`.
- Patch SHA-256:
  `05f9ff13ef43cbb1433a07a004f96ca369922da188465c40c409c348b12de371`.

The first complete-input launch passed the identity gate and entered native
execution. Its baseline progress indicated a risk of exceeding the original
12-hour limit, so it was stopped and excluded before any performance result.
Run 002 uses the identical full workload and native binary with a 24-hour
limit. Both arms passed full-input equality and entered native execution.
Driver PID at launch: 2099908; native PIDs observed: 2101576 and 2101577.
Progress fractions are not completed application timing.

Per arm, `stdout.log` records progress, `stderr.log` records errors,
`trace_report.json` declares completion, `events.jsonl` records every operation,
and `audit.json` contains independent readback. The driver writes `COMPLETE.json`,
`results.json`, `summary.csv`, and `comparison.md` only after both full arms
pass. A `failures.json` file means no valid paired result is available.

The native completion/CPU-lane/idle-step regression suite passed all 13 tests
on eex005 (`logs/tests-004.log`). Those checks are software evidence only.
The independent readback also passed three tests against saved native events
(`logs/readback-regressions-001.log`), including critical-chain closure and
rejection of changed duration and unexplained CPU wait. No simulation was
launched for those readback tests.
The earlier generated workload campaign was stopped and excluded. See
[the registered input, controls and limits](LLAMA16_PROTOCOL.md).

Inspect progress without launching another experiment:

```bash
ssh wangziheng@eex005 'tail -3 /home/wangziheng/wafer_simulator/runs/llama16-full-002/baseline/stdout.log; tail -3 /home/wangziheng/wafer_simulator/runs/llama16-full-002/ours_rotated/stdout.log; tail -5 /home/wangziheng/wafer_simulator/logs/llama16-full-002.log'
```

Do not restart, truncate, reduce message sizes, or substitute a synthetic case
to obtain a quick number. The configured wall limit is 24 hours per arm.

## Implementation comparisons

These runs retain the same complete input, both placements and fixed physical
controls. They compare simulator implementations, not new architecture settings.

| Run | Implementation | Exact full-replay reference |
| --- | --- | --- |
| `llama16-full-002` | Completion-corrected author implementation | Control |
| `llama16-full-003-topology-ref` | Immutable routing topology passed by reference | 002 |
| `llama16-full-004-runtime-opt` | Dense instruction state and empty channel evaluation removed | 003 |

Run 004 passed the full-input equality gate and launched both native processes
(observed PIDs 2149199 and 2149200). Its recorded source commit is `79784d5` with
a clean checkout. Its driver log is `logs/llama16-full-004-runtime-opt.log`.
The binary hash, 15 passing semantic regressions and 12 exact regression-report
matches are recorded in [the runtime optimization note](RUNTIME_OPTIMIZATION.md).
The wrappers automatically compare complete event hashes after both candidate
and reference finish their independent audits. Until those acceptance files
exist, neither full-capture equivalence nor an end-to-end speedup is established.
