# Wafer simulator

This directory is an independent project. Local work is source inspection,
editing, and Git. Run builds, tests, and experiments on `wangziheng@eex005`
under `/home/wangziheng/wafer_simulator`.

Keep responsibilities separate:
- `third_party/`: pinned author implementation, no in-place edits.
- `patches/`: reviewed changes applied to isolated upstream build worktrees.
- `src/wafer_sim/workloads/`: complete workload DAGs and input validation.
- `src/wafer_sim/adapters/`: upstream geometry and BookSim integration.
- `src/wafer_sim/analysis/`: independent completion audit and paired comparison.
- `src/wafer_sim/experiments/`: experiment orchestration only.
- `configs/`: explicit fixed experiment controls.
- `tests/`: semantic regressions, including upstream failure reproducers.
- `docs/`: provenance, model limits, and compact checked results.

Never label a timed-out or dependency-truncated trace complete. Never silently
remove dependencies or unmatched communication. Keep full source, binary,
input, environment, and result hashes. Do not claim native application timing,
thermal evidence, or equal physical cost from these fixed-clock experiments.
