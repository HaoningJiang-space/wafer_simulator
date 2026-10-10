# G2 prerequisite: read-only causal-state compressibility audit

Status: [three-case audit complete](results/causal-compressibility-001/REVIEW.md).
Repeated parametric kernels and ordered outputs are observed; batch execution
and any speedup remain unimplemented.

Scope: inspect `single-long`, `merge-0` and `tight-credit` from the accepted G1
registration. No new Native run, application matrix, rate change, backend or
batching implementation. The [fixed controls](../configs/causal_compressibility.json)
pin the existing predictor and G1 registration bytes. Original prediction,
Native events and accepted receipts remain unchanged.

The audit observes one boundary before `future.pop(now)`, before ReadInputs and
source generation. A Python trace hook reads the unmodified function's locals;
it never changes queues, credits, events or the execution clock. Unknown source
identity or missing boundaries fail. Complete resulting predictions must match
the accepted G1 predictions, not only finishes. Instrumented capture/analysis
time is recorded as audit cost and cannot be used as simulator speedup.

## State and normalization

The canonical causal kernel contains all ordered router FIFOs, VC owners,
switch eligibility/deadlines, VC/switch pointers, exact credit balances, source
credits, source issuing identities, ordered pending messages, complete in-flight
data/credit events with same-clock insertion order, completion flags, generation
epochs and live flit metadata. Live metadata retains routes and link-arrival
history as well as injection/arrival ages. Unique forward routes and single-flit
packets are fixed G1 assumptions, not newly approximated rules.

Clock differences are measured from the observed boundary. Expired switch-ready
deadlines and message-ready deadlines become zero: their future meaning is
eligibility now, and their original historical value does not change decisions.
Flit IDs become `(message ID, ordinal - message injected count)`. Message IDs
remain distinct. Generating a message remains an epoch boundary; absolute
generation metadata is preserved.

A source's unissued contiguous, homogeneous single-message suffix is represented
by its first identity **and its explicit remaining count**. Source remaining
work and destination pending ejections are separate finite guard variables.
They are never asserted to be equal when the kernel repeats. The report
distinguishes strict state equality including those counts from a repeated
parametric kernel with an affine progress delta. Thus a decreasing 1,024-flit
suffix is not falsely labelled as the same complete state.

Past diagnostic logs do not decide future service, but their progress counters,
stall counts and queue peaks are retained. Every observed period's ordered
service, input-arrival, credit, allocation, injection and ejection output is
independently normalized and compared; repeating throughput alone is insufficient.

## What the audit can establish

A candidate chain needs at least three consecutive periods with identical
kernel, period length, progress delta and emitted output. Only epochs with all
messages generated and no pending external demand qualify. Idle repeats do not
qualify. Tail bounds preserve at least one unconsumed unit for every advancing
counter; timeout remains another bound. Coverage is a union of intervals, so
overlapping phase-shifted chains do not inflate the result. Report busy service
coverage separately from elapsed-cycle coverage.

This verifies periods **already executed**. It identifies opportunities for a
future bounded batch, not a proof that an unexecuted batch update is correct.
It makes no minimal-state, speedup or full-G2 claim. If observed opportunities
are substantial, the next separately authorized implementation must derive a
batch update and compare its end state, event order, ownership, credits and
all seven G1 outputs. Compact representation/expansion also remains unimplemented.

## Remote execution

Use clean synchronized `main`, fresh directories and the accepted campaign:

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_causal_compressibility_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-compressibility-tests-NEW
PYTHONPATH=src ../.venv/bin/python scripts/audit_causal_compressibility_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-closure-002 \
  /Projects/haoning/wafer_simulator/runs/causal-compressibility-NEW
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.causal_compressibility \
  /Projects/haoning/wafer_simulator/runs/causal-compressibility-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-compressibility-readback-NEW
PYTHONPATH=src ../.venv/bin/python scripts/check_causal_compressibility_negative_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-compressibility-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-compressibility-negative-NEW \
  --readback /Projects/haoning/wafer_simulator/runs/causal-compressibility-readback-NEW
```

Keep normalized state streams on hn072. Publish compact results, source/input/
prediction/state hashes, test receipt and failure notes. No Native internal
event is an input: saved independent G1 predictions are checked only after the
instrumented run. No cycle is skipped during this audit.
The fresh reader authenticates audit sources/artifacts and the old G1 manifest,
checks state boundary inventory, finite-work guards and capacity bounds, then
recomputes every period/output/coverage metric from saved states. Timing fields
are carried as authenticated measurements, not measured again.
After positive readback, saved-data fault injections alter finite-work guards,
boundary inventory and coverage summaries while recomputing every affected
hash. The reader must reject semantic inconsistencies even with valid hashes.
