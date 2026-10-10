# R2.1: semantic MessageProgress independent of history lists

Status: registered implementation, not an equivalence receipt.

Only separate per-message semantic progress from FullEvidence. Preserve G1,
G2.1, R1 inputs/results and machine/transition order. Do not introduce sinks,
new recording modes, source range/lazy storage, macro_key, macros or Native/
application executions. The original source deque, packet metadata and full
recording remain. This is not a cost-reduction or R2.2/R3 receipt.

## Semantic and evidence boundary

Each message owns `MessageProgress`: generation clock, injected/received
counts, first/last injection and first/last ejection clocks. Update semantic
state before appending injection/ejection evidence. Drain/completion uses
semantic received counts plus the existing physical-resource conditions.
Remaining work and message summaries use semantic counts/times. Never infer
them from evidence length, iteration or min/max. `generated` is a detached
legacy-compatible view of `generated_at`, not a second mutable state copy.

The full result and R1 default snapshot schema remain unchanged. Snapshot's
`ejected` compatibility field represents the semantic `received` count.
`progress_snapshot()` provides a separate immutable projection of all eight
new semantic fields. Default snapshot diagnostics still inspect full event
counts; snapshots remain optional validation tools, not macro detectors.
No independent counters-only production backend is introduced.

## Gate

On hn072 run the new progress regressions plus existing R1/G1/G2.1 suites.
Test-only write-only evidence containers raise on read/length/iteration, while
ordinary execution must still reach the same semantic completion and drain.
Erasing timestamp histories must leave default semantic snapshots and message
summaries unchanged. These probes demonstrate separation; damaged histories
are not accepted as complete evidence.

Run the seven frozen G1 cases. Persist ordinary full prediction before reference
observation. Compare every R1 default state boundary and all eight progress
fields against independent G1 histories, including initial and drained states.
Preserve same-clock event sequence and its next ID. Stream a separate progress
digest ledger. Require full prediction and old default ledger bytes equal the
accepted R1 campaign; record all archive/source/input/environment/result hashes.

Independent readback restores the saved candidate, authenticates artifacts,
recomputes both ledgers and all progress fields, and checks the summary against
raw evidence. Wrong semantic count/time and missing/duplicate/changed progress
boundary records must fail at the first discrepancy. No Native rerun is needed.

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_causal_progress_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-progress-tests-NEW
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.causal_progress \
  /Projects/haoning/wafer_simulator/runs/causal-progress-NEW \
  --tests /Projects/haoning/wafer_simulator/runs/causal-progress-tests-NEW/TESTS.json \
  --r1-evidence /Projects/haoning/wafer_simulator/runs/causal-transition-002
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.causal_progress \
  /Projects/haoning/wafer_simulator/runs/causal-progress-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-progress-readback-NEW
```

Historical R1 sources/receipts remain pinned at their original Git commit;
do not overwrite or reinterpret them with revised source identity.
