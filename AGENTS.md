# Wafer simulator

This directory is an independent project. Local work is source inspection,
editing, and Git. Run new builds, tests, and experiments on
`hn072@143.89.78.72` (hostname `ee4e072`) under
`/Projects/haoning/wafer_simulator`. The user migrated experiments from eex005
because of storage pressure. Use eex005 only for evidence migration and cleanup.

Maintain one project branch, `main`. Commit coherent milestones and push them
to the project's GitHub repository. Deliver all reused Git source as pinned
ordinary files in this repository, with upstream identity and original notices;
external forks and submodules are not the source delivery. Preserve accepted
run evidence and keep large captures, build products and event tables on the
experiment server. Verify migrated bytes before deleting redundant eex005 copies.

Keep responsibilities separate:
- `third_party/`: pinned author implementation, no in-place edits.
- `patches/`: reviewed changes applied to isolated upstream build worktrees.
- `src/wafer_sim/workloads/`: complete workload DAGs and input validation.
- `src/wafer_sim/architecture/`: explicit target resource definitions, without workload or scheduling policy.
- `src/wafer_sim/adapters/`: upstream geometry and BookSim integration.
- `src/wafer_sim/execution/`: resource admission and data lifetime state, separate from timing backends.
- `src/wafer_sim/analysis/`: independent completion audit and paired comparison.
- `src/wafer_sim/experiments/`: experiment orchestration only.
- `configs/`: explicit fixed experiment controls.
- `tests/`: semantic regressions, including upstream failure reproducers.
- `docs/`: provenance, model limits, and compact checked results.

Never label a timed-out or dependency-truncated trace complete. Never silently
remove dependencies or unmatched communication. Keep full source, binary,
input, environment, and result hashes. Do not claim native application timing,
thermal evidence, or equal physical cost from these fixed-clock experiments.
