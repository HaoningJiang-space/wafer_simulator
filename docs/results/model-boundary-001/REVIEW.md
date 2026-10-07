# M0/M1: accepted conditional placement comparison

Retrieved and checked on eex005 on **2026-10-07**. The previously launched
M1 retry completed both full placements and automatic attribution. No new
simulation was launched for this delivery.

| Model | Baseline, s | Rotated, s | Baseline minus Rotated, ms | Completion-time reduction |
| --- | ---: | ---: | ---: | ---: |
| M0: source-local fixed transfer costs | 1.738783916 | 1.736418652 | 2.365264 | 0.136030% |
| M1: source-supported transfers on target resources | 2.040325219 | 2.027207062 | 13.118157 | 0.642944% |

Expanding the identified transfer class changes the predicted placement gap
by **10.752893 ms**. Both modeled completion times increase, and Rotated remains
faster; there is no ranking reversal. This establishes sensitivity to the
model boundary, not calibrated native wafer timing or a need for dynamic
shared-resource simulation rather than static target costs.

The same 006 binary, per-placement network and endpoint mapping were used.
Every non-transfer operation and original dependency was preserved. Transfer
endpoint calc costs were replaced, not added to new network cost. Their old
lane occupancy also becomes asynchronous network service, as declared in the
[resource mapping](../../TARGET_RESOURCE_MAPPING.md). M0/M1 alone does not
isolate this occupancy change, target cost and contention.

The same **445,740 original inter-host messages** have mean readiness-to-completion
times of 13,865.265 / 13,753.736 cycles in M0 and 28,836.887 / 28,089.760 cycles
in M1 (Baseline / Rotated). This common population avoids mixing in the added
messages. It demonstrates changed timing of pre-existing work; it does not
identify a particular congested router or port.

In M1, the selected chains differ by 12,371,603 cycles of local service and
746,554 cycles of message service, totaling the 13,118,157-cycle application
gap. Local durations themselves did not change between placements: the chains
include different operations. This accounting is not an independent causal
contribution of computation versus communication. Both dominant composite
intervals remain on both chains, unmodified.

The separate **002–006 complete-event equivalence check passed for both
placements**, including exact trace and event hashes. Host-runtime ratios
remain observational because runs overlapped and the reference was debugger-sampled.

## Artifact scope

- [DELIVERY.json](DELIVERY.json) records retrieved-file hashes, input identities
  and the 32-row GPU/host/NIC/reticle join.
- [COMPLETE.json](COMPLETE.json), [MODEL_COMPARISON.json](MODEL_COMPARISON.json)
  and [M1 acceptance](M1/acceptance.json) cover the M0/M1 result.
- [FINAL_ACCEPTED.json](FINAL_ACCEPTED.json) and
  [implementation_equivalence.json](implementation_equivalence.json) come from
  the separate 006 postrun directory and cover M0 implementation equivalence.
- The preserved generic [M1 attribution](M1/attribution.md) says reference
  equivalence `pending`: it did not ingest the separate final M0 check. This
  does not mean M1 is incomplete or M0/M1 events should be identical.
- Large events, message pairs and full critical-chain/source tables remain in
  `/home/wangziheng/wafer_simulator/runs/model-boundary-analysis-001` on eex005.
  `COMPLETE.json` lists their hashes; this directory is a compact publication
  subset, not a full copy of that server tree.

The current delivery closes the source table, target-resource specification
and [comparison protocol](../../MODEL_BOUNDARY_PROTOCOL.md). No new mapping,
static-model, thermal or acceleration experiment is launched. The next question
is whether independent target transfer costs with the same issue/completion
semantics already explain the observed change. Remaining source intervals and
reduction/copy costs are uncalibrated; this pair cannot establish pure-compute
dominance or equal-cost topology superiority.
