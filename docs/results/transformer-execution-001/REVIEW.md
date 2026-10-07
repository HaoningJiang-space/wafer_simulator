# Backend review and complete Transformer forward execution

> Model correction: these historical results used generic multi-output lowering
> for AllReduce, including a duplicated root result write. The logical block and
> numerical validation remain useful; these absolute times are not the current
> collective model. See the [corrected action execution and WoW study](../collective-execution-001/REVIEW.md).

Checked on **eex005, 2026-10-07**, source `9f3c8e6`. This milestone first reviews
the existing target timing capability, then extends it to a complete, declared
Transformer forward block. Source capture recovery, full Llama execution,
Mstatic and placement sweeps were not prerequisites or new runs.

## Review findings and repairs

The existing execution semantics passed the dependency, shared-service,
capacity and release regressions. The independent checker had concrete coverage
gaps: it could accept an internally consistent alternative route despite the
declared tie-breaking rule, a false resource predecessor on an idle server,
incorrect capacity-wait accounting and inconsistent terminal metadata.

The checker now verifies chronological service submissions, exact FCFS starts
and predecessors, shortest-path tie-breaking, capacity waits and final execution
state. [CHECKER_REVIEW.json](CHECKER_REVIEW.json) records seven altered examples
accepted by the old `6c35f60` checker and rejected by the current checker. These
are checker defects; they do not establish that previous executions were wrong.
The old analytical unit's **entire accepted result record is unchanged**, not
just its 113-cycle application time.

Model limits remain explicit: whole-message store-and-forward networking has
no finite router buffers, credits or adaptive routes; whole-operation storage
reservations and global collective completion are conservative choices. These
remain defined approximations rather than silently claiming BookSim behavior.

## Complete workload and validation

The [block contract](../../TRANSFORMER_EXECUTION.md) defines a bias-free
pre-LayerNorm block, dense unmasked attention, exact GELU, both residuals and
two SUM AllReduces. Batch=1, sequence=16, hidden=64, heads=4, FFN=128, shards=2.
There are **30 operations, 54 data objects and 557,056 MACs**, plus explicitly
counted scalar arithmetic. Parameter storage is 133,120 bytes and the two
retained outputs total 8,192 bytes. No original-machine duration is used.

[93 semantic tests](tests.log) passed at this source revision
([receipt](SEMANTICS.json)). Independent numerical evaluation compares the
partitioned DAG against dense assembled matrices, with multi-batch, single-token
and two/four-shard cases. Operator shapes and individual/total work counts are
checked separately. Tests also cover collective completion, placement-dependent
movement, capacity rejection, persistent parameters and missing target rates.

Each registered execution is independently read back after a JSON round trip:
30 operations, 102 phases and 134 services. All four cases pass. Inputs, rates,
source/interpreter/environment identity and artifact hashes are retained in
[CONFIG.json](CONFIG.json), [STARTED.json](STARTED.json) and
[COMPLETE.json](COMPLETE.json). The [base record](declared.json) includes the
whole DAG, tensor/operator ledger, mapping, hardware, event and storage history.

## Fixed-work resource response

All cases keep logical work, mapping, capacities, routes, link propagation and
the collective policy fixed. The network intervention doubles endpoint and link
byte rates together. These are model-cycle results, not measured hardware time.

| Changed target service | Completion cycles | Reduction from base |
|---|---:|---:|
| Declared rates | 15,862 | — |
| Compute rates doubled | 12,916 | 2,946 |
| Memory-port bandwidth doubled | 12,678 | 3,184 |
| Network bandwidth doubled | 14,326 | 1,536 |

The base block reaches attention partials at cycle 4,625; the first collective
finishes at 7,257. FFN partials finish at 12,782; the second collective finishes
at 15,414; both final residual outputs finish at 15,862. Peak resident/reserved
storage is 87,040 and 82,944 bytes, within the declared 262,144-byte regions.
Only parameters and final outputs remain live at completion.

The [summary](SUMMARY.json) exposes how resource queues change:

- Each base compute server accumulates 704 cycles of queue waiting; each
  memory port accumulates 1,408. Doubling compute rates removes compute queue
  waiting but increases each memory port's accumulated waiting to 1,856.
- Doubling memory rates reduces each memory port's waiting to 576, while each
  compute server's waiting increases to 1,376. Faster input service changes
  when competing compute requests reach the server.
- The two collectives transport 16,384 logical bytes in four messages. This
  case has zero network queue waiting. Doubling network bandwidth removes 384
  serialization cycles from each message, explaining the 1,536-cycle decrease.
  It is not evidence of a congestion reduction.

Wait totals overlap and are not additive contributions to the application's
critical path. The three interventions are separate effects, not a decomposition
of completion time or a universal bottleneck classification.

## Evidence boundary and reproduction

This is a complete analytical **forward block**, not training, a Llama prefix,
the source capture or a Baseline–Rotated comparison. It assumes ideal
operator-level memory traffic and explicit abstract arithmetic rates. Results
validate the target-driven mechanism under that contract; they do not calibrate
actual wafer compute/memory performance or establish topology preference.

Full case records remain in
`/home/wangziheng/wafer_simulator/runs/transformer-execution-001`; tests and the
historical-checker comparison are in `runs/transformer-semantics-002`. Only the
base detailed record and compact evidence are copied into Git. The three other
full records are identified by hashes in `COMPLETE.json`.

Semantic tests use the remote Python recorded in `STARTED.json`, with
`PYTHONPATH=src:tests`, and modules `test_spatial`, `test_collectives`,
`test_collective_values`, `test_timed_execution`, and `test_transformer`.
The remote runner is `scripts/run_timed_example_remote.py OUTPUT TEST_RECEIPT
--workload transformer`; use a fresh absolute output and a passing same-commit
test receipt. Test receipts include source commit, pass flag, absolute log path
and log SHA-256 as shown in `SEMANTICS.json`.
