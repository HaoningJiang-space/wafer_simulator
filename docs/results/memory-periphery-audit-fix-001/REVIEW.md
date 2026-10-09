# Periphery acceptance repairs and frozen-evidence revalidation

Three acceptance/compilation defects are repaired. The stronger reader accepts
all 27 original executions and reproduces the original tables and counts. No
new application simulation, machine parameter, transaction timing rule or D1
change was needed. This does not convert declared policies into hardware truth.

## Repairs and negative regressions

| Defect | Repair | Evidence that exercises the defect |
|---|---|---|
| Executor and audit could both trust an early-output plan | Periphery audit independently requires ordinary outputs at operation retirement, and rejects non-equivalent output phase requirements | Change the plan to publish after a read request, execute it with a real consumer, and reject the resulting early execution; reject publication before final write ack |
| A self-consistent file manifest did not establish SUMMARY/event agreement | Recompute makespan, message/flit counts, byte counts and identities from audited events; cross-check SUMMARY, MEASURED and PROCESS; require every registered row/directory exactly once | Wrong makespan in both summaries with a valid manifest is rejected; wrong counts/costs and duplicate/missing/misidentified rows are rejected |
| Shared NIC configuration was rejected by legacy bank-endpoint port counting | Check inventory/geometry/HB first, then compile declared interfaces and validate actual interfaces plus physical links | Two banks + one shared NIC + HB pass with two ports; v1 and an actual extra NIC fail; more partitions do not create more NICs; HB checks remain enforced |

The periphery publication constraint does not change collective rank-local
semantics. The ordinary execution/storage kernel is unchanged. Incomplete or
capacity-blocked runs are rejected before publication lookup, rather than being
treated as complete. Port deferral is only an inventory pass: the final shared
target still requires router-port validation. v1 retains its old endpoint count.

The complete existing remote regression suite plus 11 added regressions passes:
**239 tests**, including collective regressions, on `ee4e072`. The separate
observational reader's seven regressions are recorded in its own run, not
included in this count.

## Original evidence, read again

Reader and test source: `cdc322e88a77d09559a715e8095cb28320cab7c2`.
Original application source: `1c7a84aff461ef6eb60255686d70d097a9677ef4`.
The new receipt checks 562 raw artifact hashes, 140 original source identities,
all nine components and 18 applications. Changed audit/validation source files
are identified explicitly with archived and current hashes; their old bytes
are verified in Git. All recreated input identities match the saved inputs.
This is bounded source compatibility, not an exemption from frozen-source
checks. The original events, audits, measurements and acceptance records remain.

| Condition | A cycles | B cycles | A−B | Preferred |
|---|---:|---:|---:|---|
| v1 whole | 30,645 | 31,303 | −658 | A |
| Shared controller NIC, whole | 30,645 | 31,303 | −658 | A |
| Shared controller NIC, ideal pipeline | 25,345 | 23,561 | +1,784 | B |

Recomputed application table, effects, component results, transaction timing,
costs and compact SUMMARY are exactly equal to the accepted report. The reader
checks the archived 15-replay receipt; it does not rerun those command streams.
No evidence of an actual wrong original summary or early publication was found.
The negative tests show the old acceptance gaps and the repairs' rejection.

Raw evidence remains at `runs/periphery-applications-001`; new tests at
`runs/periphery-audit-fix-tests-002`; new reader products at
`runs/periphery-revalidation-002`, all under `/Projects/haoning/wafer_simulator`.
[CHECKED.json](CHECKED.json), [SEMANTICS.json](SEMANTICS.json) and
[REPAIR_RECEIPT.json](REPAIR_RECEIPT.json) record provenance and comparisons.
`RUN_COMPLETE.json` is the server reader's byte-exact completion receipt;
its server `REVIEW.md` is published as [READER_REVIEW.md](READER_REVIEW.md).

## Window and interpretation

The unchanged window is now explicitly documented as
[ideal_commit_visibility](../../MEMORY_WINDOW_CONTRACT.md): the policy DAG
holds four logical end-to-end positions **per transaction** and immediately
observes a remote destination commit. There is no notification path or return
latency. This is not a source-owned physical four-slot controller protocol.
No arbitrary fragment ack or timing parameter was added. No target descriptor,
controller-wide outstanding-fragment or RX budget has been supplied; these
hardware constraints remain unmodeled or uncertified.

Whole to pipeline changes service granularity, FCFS interleaving, latency
instances, supply readiness, overlap and ideal feedback together. Sixteen
4 KiB bank services have sixteen trailing 30-cycle latency instances, which
may overlap. Their instance-time sum is not extra makespan. External-controller
traffic also changes policy. The native packet remains one flit: 254 versus
1,445 message submissions both carry 92,525 native flits in each application.

The [existing-trace mechanism analysis](../memory-periphery-attribution-001/INTERPRETATION.md)
reports earlier supply, critical-chain changes and demand envelopes without
assigning independent causal cycle counts. Retain both declared contracts;
do not choose a principal hardware machine from the A/B ranking. D1 remains
registered under v1, with its application matrix deferred.
