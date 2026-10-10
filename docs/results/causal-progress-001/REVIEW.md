# R2.1 accepted: semantic message progress independent of evidence histories

Validated source: `cd20eace77661716688d245f8fb0263a0a388ba0`.
All new tests and executions ran on hn072 (`ee4e072`). The seven frozen G1
component cases retain byte-identical full predictions and R1 default boundary
ledgers. Independent readback also validates every new semantic progress field.
This closes R2.1 only: no EvidenceSink, new recording mode, source-storage
change, macro migration, Native execution or application matrix was introduced.

## Semantic progress

`MessageProgress` owns seven fields per message: `generated_at`, `injected`,
`received`, `first_inject`, `last_inject`, `first_eject`, `last_eject`.

Source generation sets the semantic generation clock. Each actual injection
and receiver consumption first updates its semantic count and first/last
clocks, then appends evidence. Completion uses received counts together with
the existing FIFO/ownership/pending-event/credit drain conditions. Remaining
work and message summaries read these semantic values rather than history
length, iteration or min/max. `generated` is now a detached compatibility view
of `generated_at`, avoiding a second mutable generation state.

Full output fields and the R1 schema-1 default snapshot remain unchanged.
Snapshot's `ejected` compatibility field represents the semantic `received`
count. The separate immutable `progress_snapshot()` covers all newly explicit
counts and times. Complete R2.1 semantic verification checks both projections;
the default snapshot alone does not expose every new time field. Neither is
used for macro detection. Snapshot diagnostics still inspect full event counts.

Full recording, source deques and eager packet metadata remain. Progress
separation does not provide counters-only execution or remove per-flit memory
and dictionary construction. The result builder still reads full evidence for
full events/flit output, but message time summaries come from semantic state.
No runtime or memory improvement is claimed.

## Equivalence and independent readback

Candidates are persisted before reference observation. Unmodified G1 histories
independently provide count and first/last clock expectations at every cycle.
The verifier checks them against the semantic projection, along with the
existing source/router/event/sequence/default-state checks. The default
boundary ledger is checked against the accepted R1 ledger as it is generated.
Readback restores the saved candidate, recomputes both ledgers, authenticates
source/input/environment/test/archive/result hashes and checks summary rows.

| Case | Flits | Default and progress boundaries | Full prediction / default ledger |
|---|---:|---:|---|
| single-one | 1 | 65 | Byte-identical to R1 |
| single-long | 1,024 | 2,111 | Byte-identical to R1 |
| merge-0 | 3,072 | 6,207 | Byte-identical to R1 |
| merge-509 | 3,072 | 6,207 | Byte-identical to R1 |
| merge-3000 | 3,072 | 8,111 | Byte-identical to R1 |
| queued-source | 162 | 387 | Byte-identical to R1 |
| tight-credit | 384 | 7,516 | Byte-identical to R1 |

Totals are 30,604 state boundaries, 612,220 semantic field comparisons and
10,787 full flit records, retaining
97,083 service records, 43,148 credit returns and every message finish/final
drain. Same-cycle event insertion order and the next global sequence ID are
unchanged. Forty campaign artifacts pass independent readback. Field accounting
uses the independent seven-field inventory over 87,460 message-boundary
instances, rather than an assumed field count.

## Regressions and scope

65 targeted tests pass: nine new R2.1 plus the existing 16 R1, 29 G1 and 11
G2.1 tests. They overlap previous receipts and are not a whole-project test
count. The new probes check:

- Zero generation/injection clocks remain distinct from unstarted `None`.
- Semantic updates occur before timestamp-history append callbacks.
- Test-only evidence containers raise on length/item/iteration reads while
  ordinary execution still reaches the same progress, ownership, credits,
  queues, event sequence and drain.
- Erasing injection/ejection histories leaves every default state boundary and
  final message summary unchanged; wrong history values do not replace semantic
  counts/times. These are separation probes, not production evidence modes or
  acceptance of damaged histories as complete evidence.
- Wrong semantic count/time is rejected at its first changed boundary even
  with intact logs; missing/duplicate/changed progress ledger rows are rejected.
- Generation views and progress snapshots are detached from mutable state.

FullEvidence's private empty timestamp-map buckets are not semantic state;
completion no longer reads those lists or creates buckets merely by testing
their lengths. Compatibility claims here concern serialized full predictions
and R1 default snapshots/ledgers, not incidental private empty-map allocation.

Raw final evidence stays in `/Projects/haoning/wafer_simulator/runs/causal-progress-002`,
tests in `causal-progress-tests-002`, and readback in
`causal-progress-readback-002`. [PUBLISHED_COPIES.json](PUBLISHED_COPIES.json)
pins compact copies. Old G1/R1/G2.1 evidence stays unchanged at its original
source identities; historical source-sensitive readers must use their pinned
Git revision. S/D0/D1, periphery, architecture, existing timed execution,
third-party files and patches are unchanged.

The initial `-001` runs at `b940a45` passed state/event comparisons, but their
summary multiplied field checks by eight although the schema has seven fields.
That overcount (699,680) is not the accepted final count. The revised verifier
checks its explicit field inventory and reports 612,220; tests, all seven
component runs and independent readback were repeated after the correction.
Initial raw evidence is preserved on hn072 and compact identities under
[diagnostic/](diagnostic/README.md). The source correction changed comparison
accounting only, leaving ordinary service and its results unchanged.

R2.2 recording sinks, R3 AST-free macro migration, lightweight macro keys and
G2.2/G2.3 remain separate work. The current ordinary engine continues to record
full evidence using the established physical service rules.
