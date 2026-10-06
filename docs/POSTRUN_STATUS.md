# Placement attribution status

Checked on eex005 at **2026-10-06 12:16 UTC**. This is a dated status receipt,
not a claim that pending simulations have completed.

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
| 006 | No; Rotated audited | Target architecture pair; waiting for Baseline |

At the snapshot, 006 Baseline had processed 137,211,244 of 151,889,580 flits.
This progress is not application completion. No failure or exclusion marker
was present in these five campaigns. The compact machine-readable snapshot is
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
`runs/postrun-unit-006/tests.log`, using analysis commit `f4510ed`.
The subsequent commits correct report wording and campaign identification.
The log SHA-256 is
`ba14c76e69fc0091982b0c4fb0e9f353f20b199337624417b072492a701650c9`.

The complete saved 004 pair passed end-to-end read-only analysis in
`runs/postrun-full-readback-004-001`. It paired all 445,740 messages and recovered
53,813 / 53,715 chain nodes; each chain exactly matched the existing auditor's
completion time and decomposition. The between-chain accounting also closed
exactly. This validates analysis on full-size evidence; it is not the target
006 result or an implementation-equivalence claim. Its `VALIDATION_ONLY.json`
and full artifact hashes remain on the server. Raw inputs/events/CSVs were not
downloaded or added to Git.

## Automatic continuation already running

Postprocessor PID at the snapshot: `2412066` on eex005. It waits for 006's final
`COMPLETE.json`, generates the architecture report, waits for 002's final gate,
then directly compares both full input/event hashes and finalizes only after
equivalence passes. It launches no BookSim process.

- Log: `/home/wangziheng/wafer_simulator/logs/postrun-006-attribution-001.log`
- Output: `/home/wangziheng/wafer_simulator/runs/postrun-006-attribution-001`
- Launch receipt: `runs/postrun-006-attribution-launch.json`
- Snapshot receipt: `runs/postrun-ready-001/status.json`

`ANALYZED.json` means the 006 architecture pair has been analyzed, with reference
equivalence still explicitly pending. `FINAL_ACCEPTED.json` additionally
requires direct full-event equivalence to 002. Neither marker exists at this
snapshot. Review the actual report and its single next-experiment registration
after those gates; do not start another full campaign merely because a config
file has been registered.
