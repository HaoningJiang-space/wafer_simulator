# Placement attribution status

**Final update, 2026-10-07:** the independent 002–006 full-event equivalence
check has passed for both placements. Mapping remains deferred with zero new
mapping groups; see [final receipts](results/model-boundary-001/REVIEW.md).
The 2026-10-06 account below is preserved as historical context.

Checked on eex005 at **2026-10-06 13:02 UTC**. This is a dated status receipt,
not a claim that pending simulations have completed.

**006 has passed both full-placement audits and read-only attribution.**
The [reviewed result](results/llama16-006/REVIEW.md) and
[generated attribution report](results/llama16-006/attribution.md) are available.
Rotated reduces mean packet latency by 14.7490%, while full conditional replay
time falls by 0.13603%. Direct full-event equivalence to 002 is still pending.

The research goal is frozen in [POSTRUN_PROTOCOL.md](POSTRUN_PROTOCOL.md).
The native implementation is unchanged. No additional simulator, reduced-work
experiment, thermal model or GPU implementation was launched in this stage.

## Existing full runs

| Run | Both full arms audited | Current use |
| --- | --- | --- |
| 002 | No | Required direct implementation-equivalence reference |
| 003 | Yes | Preserved intermediate evidence |
| 004 | Yes | Existing full events used to validate read-only attribution |
| 005 | Yes | Preserved intermediate evidence |
| 006 | Yes | Target pair and complete read-only attribution accepted |

Both 006 arms retained 5,324,230 operations, 9,002,700 dependency/arrival edges
and 151,889,580 flits and passed the separate dependency-profile audit.
No failure or exclusion marker was present. The earlier 12:16 snapshot is
[postrun-ready-20261006.json](results/postrun-ready-20261006.json).

## Delivered analysis and checks

- Strict paired acceptance from existing native, all-operation and dependency
  profile audits; fixed-work, implementation and resource identities checked.
- Separate reconstruction of each selected critical chain, every message pair,
  unchanged local stages, observed CPU blocking relations and endpoint mapping.
- Exact accounting of application-time differences across different chains;
  report includes critical-message phase changes without inferring port causes.
- One conditional next-mapping registration through the existing mapping
  consumer. Registration never starts a simulation.

Ten analytical semantic tests passed on eex005 in
`runs/postrun-unit-008/tests.log`, using analysis commit `fd8767b`.
This includes rejecting premature experiment registration and checking analysis
and finalization environment identities.

The 006 analysis ran from the same `fd8767b` commit. All ten saved artifact
hashes were checked. A separate CSV delivery check read all 445,740 message
rows and checked their work totals and three-phase timing identities, both
critical-chain service sums, 99,428 paired local rows and 32 endpoint records.
See [the delivery check](results/llama16-006/delivery_check.json).

The complete saved 004 pair passed end-to-end read-only analysis in
`runs/postrun-full-readback-004-001`. It paired all 445,740 messages and recovered
53,813 / 53,715 chain nodes; each chain exactly matched the existing auditor's
completion time and decomposition. The between-chain accounting also closed
exactly. This validates analysis on full-size evidence; it is not the target
006 result or an implementation-equivalence claim. Its `VALIDATION_ONLY.json`
and full artifact hashes remain on the server. Raw inputs/events/CSVs were not
downloaded or added to Git.

## Automatic continuation already running

Postprocessor PID confirmed live at the snapshot: `2412066` on eex005.
It has generated the 006 architecture report and is now waiting for 002's final
gate. It will compare both full input/event hashes and finalize only after
equivalence passes. Next-study registration is also deferred until that gate.
It launches no BookSim process.

- Log: `/home/wangziheng/wafer_simulator/logs/postrun-006-attribution-001.log`
- Output: `/home/wangziheng/wafer_simulator/runs/postrun-006-attribution-001`
- Launch receipt: `runs/postrun-006-attribution-launch.json`
- Snapshot receipt: `runs/postrun-ready-001/status.json`

`ANALYZED.json` means the 006 architecture pair has been analyzed, with reference
equivalence still explicitly pending. `FINAL_ACCEPTED.json` additionally
requires direct full-event equivalence to 002. `ANALYZED.json` exists;
`FINAL_ACCEPTED.json` does not at this
snapshot. Review the actual report and its single next-experiment registration
after those gates; do not start another full campaign merely because a config
file has been registered.
