# Accepted placement attribution

The current goal is application attribution, with the single maintained native
implementation frozen. No 007/008 optimization variant, new simulator model,
GPU backend, thermal feedback or additional workload execution belongs to this
stage. All analysis and tests run on eex005.

## Acceptance and order

1. Wait for both arms of `llama16-full-006-csr-frontier` to pass their existing
   final `COMPLETE.json` gate. Reject failed/excluded runs. Confirm native
   reports, independent all-operation audits, dependency-profile audits, work
   counts, fixed controls and common binary provenance.
2. Read the existing original graph, `checked_events.npy`, mappings and saved
   summaries. Generate the architecture comparison and critical-message report.
   Do not rerun `goal_completion.audit`, overwrite its artifacts, or call the
   legacy generated-DAG `analysis/comparison.py`.
3. Separately wait for 002, then run the retained `verify_full_replay.py`
   directly on 002 versus 006. Pending reference equivalence does not prevent
   attribution of the accepted 006 pair, but remains explicitly pending in its
   report. Finalize the report only when both placements' complete input/event
   hashes and results match.
4. Interpret the data and register exactly one subsequent controlled experiment
   in `next_experiment.json`. Registration is not authorization to infer missing
   simulator knobs or execute a new campaign during this stage.

The checkout is `/home/wangziheng/wafer_simulator/source`; its parent holds the
venv, original graphs and runs. Thus commands should use the checkout for code
and the parent for data:

```bash
cd /home/wangziheng/wafer_simulator/source
bash scripts/postrun_attribution_remote.sh \
  /home/wangziheng/wafer_simulator/runs/postrun-006-attribution-001
```

This wrapper waits and performs read-only analysis of existing runs. It never
invokes BookSim. Individual analysis is available through
`scripts/analyze_placement_remote.py CAMPAIGN NEW_OUTPUT`.

## Outputs

- `application_comparison.csv`: same-implementation Baseline–Rotated application
  cycles/seconds, message phases, packet latency/hops and resource counts.
- `baseline/critical_chain.csv` and `ours_rotated/critical_chain.csv`: each arm's
  independently reconstructed chain, operation identities, controlling
  predecessor/relation, CPU lane, timestamps, and known endpoint positions.
- `message_pairs.csv`: every send matched by the original operation ID/receive
  pair, per-arm endpoints, timestamps, three-phase decomposition and membership
  in each selected chain.
- `endpoint_mapping.csv`: complete active endpoint mappings and physical positions.
- `summary.json` and `attribution.md`: compact attribution and exact between-chain
  accounting, including messages on one or both selected chains.
- `acceptance.json` and `ANALYZED.json`: source/binary/input/artifact identities
  and explicit implementation-equivalence status.
- `implementation_equivalence.json` and `FINAL_ACCEPTED.json`: direct complete
  002-vs-006 acceptance after the reference finishes. `FINAL_ACCEPTED` covers
  the attribution/equivalence gate; the overall research goal also requires the
  reviewed interpretation and a single next-experiment registration.

## Interpretation rules

The three message intervals are CPU wait, pre-first-flit injection wait, and
first-injection-to-completion. The final interval includes later injection,
transport and competition; it is not pure link latency. CPU wait is accounted
through predecessor services in the critical chain and must not be added twice.

The chain uses the existing audit's deterministic tie policy. Membership means
membership in this selected chain, not a proof that an absent operation has
positive slack on every possible critical path. The two arms can select
different chains. Their completion difference is checked as common-node service
differences plus Baseline-only services minus Rotated-only services. This is an
accounting identity, not a per-message counterfactual intervention.

The original model has logical host/CPU lanes but does not assign every `calc`
to a physical compute reticle. Such CSV rows have no fabricated physical
coordinates. The capture's fixed local work includes opaque intra-host activity;
results remain conditional replay times, not calibrated native wafer training.

Internal router/port/VC contention is not reconstructed from message timestamps.
Use the observed message/phase attribution first, then decide whether one
specific missing observation is needed. Raw event/CSV artifacts stay on eex005;
only compact checked summaries and reports should enter GitHub.
