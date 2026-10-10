# R1 accepted: explicit state and exact one-cycle execution

Validated implementation: `b0e924846586878a3d1bbee2d85092d7bdfe982c`.
All new tests and executions ran on hn072 (`ee4e072`). Seven frozen G1 cases
match the unchanged legacy reference at every cycle boundary and in their
complete saved predictions. No macro, Native build/run or application matrix
was introduced. This closes R1, not R2 evidence separation or R3 macro migration.

## Explicit ordinary core

`execution/causal/state.py` exposes `CausalState`, `SourceState`, `RouterState`,
an insertion-ordered `EventQueue` and detached immutable `CausalSnapshot`.
`transition.py` exposes `step_one_cycle()`, `run()` and complete-result
projection. Neither module imports analysis/experiments or uses AST rewriting,
dynamic compilation, Python tracing, reference traces or filesystem state.

```python
from wafer_sim.execution.causal import initialize, step_one_cycle, result

state = initialize(contract, messages, cycle_limit=200000)
step_one_cycle(state)
boundary = state.snapshot()  # Detached; does not influence execution.
while not state.complete:
    step_one_cycle(state)
prediction = result(state)
```

Ordinary service preserves G1's order: consume prior channel events; generate
and inject source work; evaluate allocations using pre-update ownership;
commit VC/switch service and schedule channel/credit events; check drain.
Source queues remain non-preemptive message queues. A switch release does not
retroactively enable a VC request in the same cycle. Same-clock events retain
global insertion sequence, rather than sorting by kind or flit identity.
Message completion remains distinct from final credit/resource drain.

Snapshots include full issuing IDs, pending message heap order, ownership,
exact switch deadlines, pointers, credit balances, ordered in-flight events and
sequence IDs, live packet metadata, generations, finite remaining work and
progress/stalls/peaks. Every uninjected packet's metadata is represented by
lossless contiguous identity segments, including exceptions to homogeneous
roles. Incorrect message/source/epoch/ID is visible before injection. This
coalesces snapshot copies only; it does not skip service or replace the source
deque. `snapshot(include_history=True)` additionally includes all generated
packet metadata and complete evidence history. Default snapshots omit retired
history; complete results independently check it.

Full event recording remains the sole ordinary-core mode. `FullEvidence` groups
owned records, but the transition still constructs full records; no EvidenceSink
redesign is claimed. Global legacy flit IDs remain unchanged. The returned
projection deliberately retains G1-compatible scope/fields for exact equality;
the campaign provenance identifies the new explicit-core producer.

## Equivalence gate

The candidate is run without observation and persisted first. A separate
verifier then observes the unchanged G1 and compares an independently advanced
shadow engine at every pre-cycle boundary plus the final drained boundary.
Reference locals are projected independently, without using the producer's
snapshot encoder. Reference schedule calls establish expected event sequence
IDs only; no observed event is submitted to the shadow engine. Tracing exists
only in this offline verifier. Stored boundary ledgers are authenticated and
recomputed on independent readback; saved predictions are checked, not replaced.

| Frozen case | Flits | State boundaries checked | Message finishes | Final drain |
|---|---:|---:|---|---:|
| single-one | 1 | 65 | 50 | 64 |
| single-long | 1,024 | 2,111 | 2,096 | 2,110 |
| merge-0 | 3,072 | 6,207 | 6,190 / 6,192 / 4,144 | 6,206 |
| merge-509 | 3,072 | 6,207 | 5,682 / 6,192 / 5,160 | 6,206 |
| merge-3000 | 3,072 | 8,111 | 2,096 / 5,096 / 8,096 | 8,110 |
| queued-source | 162 | 387 | 302 / 370 / 372 | 386 |
| tight-credit | 384 | 7,516 | 7,499 / 7,501 / 5,005 | 7,515 |

All 30,604 state boundaries, 10,787 full flit records, 97,083 service records,
43,148 credit returns, sent credits, arrivals, stalls, peaks and finish/drain
fields match. The seven complete prediction files have the same SHA-256 bytes
as their accepted G1 counterparts. There are 88,910 G1 combined router-cycle
allocation records; this differs from the original Native observation's
112,695 separate VC/switch allocation calls. The record inventory has not been
reduced: the complete G1 predictions are identical. No Native comparison was
rerun or relabelled as a new Native execution.

Independent readback authenticated 31 campaign artifacts and reproduced all
seven boundary ledgers and result rows. It checks input identities, archived
prediction/manifest hashes, source/environment hashes and summary consistency.
[VERIFIED.json](VERIFIED.json) records the final campaign/result identities.

## Regression and failure evidence

56 targeted regressions pass: 16 R1, 29 existing G1 and 11 existing G2.1 tests.
These counts overlap prior receipts; they are not a new whole-project test
count. Negative cases change credit, owner, deadline, future event order and
queued packet roles, and require the first changed boundary/field to be
reported. Wrong saved output, duplicate/missing/changed boundary ledger,
incomplete drain and invalid boundary inputs are rejected. Snapshot and result
copies do not alias mutable state.

The first test attempt at `985374f` failed in the new verifier/fixture: tracing
revisited the channel loop line within a cycle and advanced the shadow again;
an invalid fault fixture also referenced an unknown packet. The verifier now
observes each clock once, and the fault fixture reverses actual same-clock
events. That failed receipt/log is preserved. The initial seven-case acceptance
at `642da3f` also remains. A subsequent snapshot-strengthening change added all
queued packet roles and was followed by the final 56-test/seven-case acceptance;
neither earlier receipt is substituted for the final one.

## Provenance and limits

Final tests: `/Projects/haoning/wafer_simulator/runs/causal-transition-tests-003`.
Final campaign/readback: `causal-transition-002` /
`causal-transition-readback-002`. Earlier tests/campaign/readback remain under
their original suffixes. Full predictions, state ledgers and logs stay on
hn072; [PUBLISHED_COPIES.json](PUBLISHED_COPIES.json) pins the compact copies.

Legacy G1 SHA-256 remains
`24831579b2d0c49d11ab1003daef490754dba5d92e80b68c30da0fdbd1e9cf41`.
The [accepted G2.1 prototype](../causal-macro-single-001/REVIEW.md) remains
unchanged, including its AST derivation. S/D0/D1, periphery, architecture,
existing timed execution, third-party sources and patches are unchanged.

The new ordinary core is a stable state/transition entry for future research
within this bounded four-router contract. It is not a general NoC engine,
hardware calibration, macro migration or an acceleration result. R2 sinks and
R3 macro rules require their own behavior and cost gates; G2.2/G2.3 have not
started in this refactor.
