# Full-capture run receipt — 2026-10-06

Status: **full run 002 submitted; no application-performance result yet**.

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
limit. Progress fractions are not completed application timing.

Per arm, `stdout.log` records progress, `stderr.log` records errors,
`trace_report.json` declares completion, `events.jsonl` records every operation,
and `audit.json` contains independent readback. The driver writes `COMPLETE.json`,
`results.json`, `summary.csv`, and `comparison.md` only after both full arms
pass. A `failures.json` file means no valid paired result is available.

The native completion/CPU-lane/idle-step regression suite passed all 13 tests
on eex005 (`logs/tests-004.log`). Those checks are software evidence only.
The earlier generated workload campaign was stopped and excluded. See
[the registered input, controls and limits](LLAMA16_PROTOCOL.md).

Inspect progress without launching another experiment:

```bash
ssh wangziheng@eex005 'tail -3 /home/wangziheng/wafer_simulator/runs/llama16-full-002/baseline/stdout.log; tail -3 /home/wangziheng/wafer_simulator/runs/llama16-full-002/ours_rotated/stdout.log; tail -5 /home/wangziheng/wafer_simulator/logs/llama16-full-002.log'
```

Do not restart, truncate, reduce message sizes, or substitute a synthetic case
to obtain a quick number. The configured wall limit is 24 hours per arm.
