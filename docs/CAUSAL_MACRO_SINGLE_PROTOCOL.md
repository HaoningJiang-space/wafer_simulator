# G2.1: guarded two-cycle transition on the existing G1 state machine

Status: registered implementation/validation work, not an accuracy or speedup
receipt. This gate covers one source-0 message to endpoint 3 under the exact
primary G1 contract. Multi-source traffic, two-flit buffers, other routes and
G2.2/G2.3 are excluded. Accepted G1 source and evidence stay byte-pinned.

The implementation reuses the pinned G1 transition body. A checked mechanical
derivation exposes its cycle boundary, substitutes equivalent lazy homogeneous
source-label storage and compressed evidence containers, and replaces final
materialization. It does not change arrival handling, source admission,
VC/switch decisions, output scheduling, reverse credits or retirement order.
The derived ordinary Python source and its hash are saved for review. An
unmodified G1 run is the independent reference; a macro-disabled run of the
same derived core isolates the effect of skipping service computation.

## Translation and guard

The kernel includes ordered live FIFO labels/metadata, ownership, exact pending
switch deadlines, pointers, credit balances, source eligibility and every
ordered in-flight event. It uses integer tuples, not Python tracing or JSON.
Clock and live flit labels may translate; generation epochs do not. Remaining
source and receiver work and diagnostic counters remain explicit.

The guarded region has a single generated homogeneous message, no pending
external demand, the fixed source/route/contract, and positive finite remaining
work. No other input/output can request service. Under these conditions the
pinned transitions are equivariant under simultaneous clock and flit-label
translation: comparisons use deadlines/eligibility and resource state, while
labels identify interchangeable single-flit packets. Source-empty, receiver
completion and deadline exits must remain outside the batch. This structural
argument, not three observations alone, licenses repetition.

Require three observed two-cycle transitions with the same complete kernel,
progress and emitted template. Per period the fixed signature consumes one
source flit and one pending ejection; source stalls increase by one, router
stalls stay unchanged, and peaks are unchanged. All credits and in-flight
events are internal to the recurring kernel. The macro count is bounded by
`min(source_remaining-1, receiver_remaining-1, (cycle_limit-now-1)//2)`.
The final source/receiver unit and deadline boundary are never skipped.

One macro translates the bounded live frontier and in-flight events, moves the
source suffix cursor, updates counts/stalls, and appends a repeat descriptor.
It never constructs one dictionary per skipped flit/event. Normal execution
resumes for the tail and final credit drain. A periodic output count alone,
an absent credit, changed owner or unmatched event cannot authorize a batch.

## Verification and cost

On hn072, compare unmodified G1, macro-disabled derivation and macro-enabled
derivation for the frozen sizes and delayed release. Expand compact evidence
outside timed execution and require complete prediction equality, including
all allocations, flits, services, credits, peaks, stalls, finish and drain.
At each macro entry/exit independently capture the original G1 boundary and
compare logical kernel, finite counters, deadlines and next events. Inject
wrong ownership/credit/event/counter states and ensure rejection. Timeout is
incomplete even when a macro was taken.

Benchmark 1,024/8,192/32,768 flits, three shuffled repetitions, fixed CPU
affinity and identical counters-only output for macro off/on. Record physical
cycle updates, skipped logical cycles, macro count, prediction wall time,
complete worker wall time, CPU and peak RSS. Report source/recording benefits
separately from macro off/on acceleration. Compact evidence and full expansion
have separate costs; counters-only execution is not a full flit audit.
Worker wall time uses blocking waitpid with a separate 180-second process-group
watchdog, avoiding timeout-polling latency. Persist start/end monotonic counters,
exit status, command/input/worker identities and parsed GNU time CPU/RSS/elapsed
fields. Readback cross-checks these raw receipts before computing medians.
A separately labelled `macro_compact` worker saves reconstructable prefix,
repeat and tail evidence. Its complete-worker cost includes that serialization;
its saved evidence is fully expanded and compared with fresh G1 on readback.
The primary macro-off/on ratio continues to use identical counters-only output.

Use fresh directories, clean main, same-source tests, source/interpreter/input/
environment/result hashes. Preserve all failed attempts and large evidence on
hn072. Do not retune the contract, use Native internal events, or claim a general
network backend, application-gap result or hardware calibration.

## Remote entry points

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_causal_macro_single_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-macro-single-tests-NEW
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.causal_macro_single \
  /Projects/haoning/wafer_simulator/runs/causal-macro-single-NEW \
  --tests /Projects/haoning/wafer_simulator/runs/causal-macro-single-tests-NEW/TESTS.json
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.causal_macro_single \
  /Projects/haoning/wafer_simulator/runs/causal-macro-single-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-macro-single-readback-NEW
PYTHONPATH=src ../.venv/bin/python scripts/check_causal_macro_single_negative_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-macro-single-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-macro-single-negative-NEW \
  --readback /Projects/haoning/wafer_simulator/runs/causal-macro-single-readback-NEW
```

Candidate compact evidence is persisted before original G1 observation. The
reader restores that evidence rather than rerunning a correct candidate over
it, regenerates only the independent reference, checks all macro boundaries,
and recomputes cost tables from worker/process receipts. Expanded data use the
G1 event-projection schema, including its compatibility scope string; the outer
record explicitly identifies the actual G2.1 producer and compression metrics.
The projection is not labelled as a new Native or uncompressed G1 execution.
