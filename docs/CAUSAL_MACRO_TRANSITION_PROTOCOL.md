# R3: migrate the accepted single-flow macro to explicit causal state

Registered implementation, not an accuracy receipt. Retain original G1 and
the accepted AST G2.1 prototype as unchanged independent references. The new
runner is `execution.causal.macro.run`; it imports neither reference, analysis,
AST nor dynamic compilation. There is one ordinary `step_one_cycle()` body.

Only the existing primary four-router/source-0 homogeneous message is allowed.
No merge or tight-credit macro and no full-system backend substitution. Eager
source storage stays the ordinary default. The bounded macro runner alone uses
a homogeneous source range and lazy live metadata; this changes representation,
not message eligibility, injection, ownership, arbitration or credit rules.

The concrete rule has recognition, maximum-safe-repeat and apply operations.
Its key preserves router FIFOs/ownership/deadlines/pointers/credit, source
eligibility, ordered future events and live packet metadata, modulo time/flit
translation. Generation epochs and first-progress times are fixed. Sequence IDs
are normalized relative to next-sequence; every period schedules exactly eleven
events. A jump shifts pending IDs and next-sequence by eleven per repetition,
preserving same-cycle insertion order. Progress/count/stall deltas are explicit.

Guarded homogeneous single-flow rules commute with the clock/label translation
while work remains positive and no external demand changes eligibility. Three
matching periods validate the observed template, not merely throughput. A
recognized authorization is tied to the exact current key, progress, cycle and
template; mutation/staleness cannot authorize a jump. Leave source/receiver tails
and the deadline outside the batch. Closed-loop credits stay inside its frontier.

Default snapshots are expensive validation projections. Recognition uses only
the bounded macro key and an eight-cycle observer, never tracing, JSON or full
snapshots. This short recognition history is algorithm state, independent of
persistent Full/Compact/Counters consumers. Counters produces no persistent event
tables; Compact records repeats without generating skipped dictionaries. Full
validation deliberately expands repeat evidence and makes no compact-cost claim.

Reuse nine frozen G2.1 accuracy inputs, independently expand saved records and
compare every original G1 event and saved G2.1 behavior. At each macro entry/exit,
observe old G1 independently and compare complete default/semantic snapshots,
including insertion IDs and next-sequence. Save macro-off Full, macro-on Full,
Compact and Counters outcomes and their final snapshots. Reject forged templates,
stale ownership/credit/deadline/sequence/work and incomplete drains.

Benchmark 1,024/8,192/32,768 flits, three shuffled repetitions on CPUs 18/19.
Macro off/on use the same explicit core, lazy storage and counters-only output.
Record prediction and full blocking-wait worker wall time, CPU, RSS, real cycle
updates and logical coverage. Measure reconstructable Compact separately; expand
it outside timed prediction and require full equality. No speedup over Native,
application execution or a merged system is inferred.

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_causal_macro_transition_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-macro-transition-tests-NEW
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.causal_macro_transition \
  /Projects/haoning/wafer_simulator/runs/causal-macro-transition-NEW \
  --g2 /Projects/haoning/wafer_simulator/runs/causal-macro-single-003 \
  --tests /Projects/haoning/wafer_simulator/runs/causal-macro-transition-tests-NEW/TESTS.json
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.causal_macro_transition_study \
  /Projects/haoning/wafer_simulator/runs/causal-macro-transition-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-macro-transition-readback-NEW
```
