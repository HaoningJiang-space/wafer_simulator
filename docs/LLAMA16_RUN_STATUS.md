# Full-capture run receipt — 2026-10-06

Status checked **2026-10-06 13:02 UTC**: runs 003 through 006 have passed
their paired full-completion audits. The 006 attribution report and all message
pairs are now available and checked. Run 002 is still executing both arms;
direct 002-vs-006 equivalence and final next-study registration remain pending.
See [the postrun receipt and validation](POSTRUN_STATUS.md).

The working tree now maintains only the selected run 006 implementation through
the [unified build/test/run entry points](IMPLEMENTATION.md). The historical
run labels below identify preserved processes and evidence, not selectable
implementation variants in the current code.

The launch details below are historical receipts. Completed intermediate
implementations do not replace the requested 006 acceptance gate, and matching
completion times alone do not establish full-event implementation equivalence.

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
| `llama16-full-005-node-reuse` | Ordered-container nodes retained across arbitration/credit reuse | 004 |
| `llama16-full-006-csr-frontier` | Flat dependency CSR, stable ready frontier, aggregate readiness profile | 005 |

Run 004 passed the full-input equality gate and launched both native processes
(observed PIDs 2149199 and 2149200). Its recorded source commit is `79784d5` with
a clean checkout. Its driver log is `logs/llama16-full-004-runtime-opt.log`.
The binary hash, 15 passing semantic regressions and 12 exact regression-report
matches are recorded in [the runtime optimization note](RUNTIME_OPTIMIZATION.md).
The wrappers automatically compare complete event hashes after both candidate
and reference finish their independent audits. Until those acceptance files
exist, neither full-capture equivalence nor an end-to-end speedup is established.

Run 005 also passed the full-input equality gate and launched native processes
2186310 and 2186311 from clean source commit `e3899f8`. Its driver log is
`logs/llama16-full-005-node-reuse.log`. The additional 1,500-round arbitration
comparison and checked-container ownership tests are documented in
[NODE_REUSE.md](NODE_REUSE.md). Full-capture acceptance is pending.

Run 006 passed the full-input equality gate and launched native processes
2209666 and 2209667 from clean source commit `10a6f35`; wrapper PID 2208034.
Its driver log is `logs/llama16-full-006-csr-frontier.log`. It retains all
5,324,230 operations, 9,002,700 dependency/arrival edges and 151,889,580 flits
per placement. The candidate enables dependency profiling; its separate
accounting audit must pass before campaign completion. The wrapper then checks
exact input/event hashes against run 005. The 18-test reference/candidate
semantic acceptance, binary identity and complete-graph structure inspection
are documented in [CSR_FRONTIER.md](CSR_FRONTIER.md). No GPU kernel or full-run
speedup has been established.
