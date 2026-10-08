# Wafer-Scale Simulator

**Research question:** which execution details are needed to predict data
availability, resource feasibility and the performance difference between two
WoW designs—and which details can be omitted?

The completed milestone freezes the execution kernel and compares **serial,
pipeline and bounded memory–network boundaries** on Baseline and Rotated.
Use the same two complete analytical Transformer blocks, two declared memory
policies and native BookSim. This is a study of simulation abstractions;
placements and collectives are fixed validation cases, not optimization targets.
[Registered controls and acceptance](docs/BOUNDARY_DESIGN_PROTOCOL.md)

## Latest result and stop decision

The [paired design-gain report](docs/results/boundary-design-001/model_selection.md)
now covers 24 configurations and 72 complete executions. serial has substantial
absolute-time bias but only +8/+44/+20/-12 cycles of design-gap error; all four
pass the registered 100-cycle gap budget. Two threshold classifications still
disagree: a small error does not certify the winner of a close comparison.
Reference gaps of 74/82 cycles put the designs within the declared indifference
band. pipeline reproduces all reference makespans but violates RX capacity.

**Decision:** retain serial for this scoped gap estimate, bounded for declared
message/capacity predictions, and close endpoint enhancement/runtime optimization.
Compute/SRAM/DMA remain design assumptions, not calibrated native wafer inputs.
The next research question is independent workload/shared-resource coverage;
it requires its own registration and has not been launched. Existing evidence:
[decision table](docs/results/boundary-design-001/analysis/model_decision_table.csv),
[costs](docs/results/boundary-design-001/analysis/cost.csv),
[earlier reduction reconvergence](docs/results/boundary-model-selection-001/REVIEW.md).

## Current entry point (eex005 only)

Local work is source inspection, editing and Git. Build, test and execution run
on `wangziheng@eex005`, under `/home/wangziheng/wafer_simulator`; source is in `source/`.
Existing accepted native binaries are reused. All output directories must be new.

```bash
cd /home/wangziheng/wafer_simulator/source
export PYTHONPATH=src
/home/wangziheng/wafer_simulator/.venv/bin/python scripts/test_wow_target_remote.py \
  /home/wangziheng/wafer_simulator/runs/boundary-design-tests-NEW
/home/wangziheng/wafer_simulator/.venv/bin/python -m wafer_sim.cli boundary-design \
  --tests /home/wangziheng/wafer_simulator/runs/boundary-design-tests-NEW/SEMANTICS.json \
  --output /home/wangziheng/wafer_simulator/runs/boundary-design-NEW
/home/wangziheng/wafer_simulator/.venv/bin/python -m wafer_sim.cli analyze-boundary-design \
  --run /home/wangziheng/wafer_simulator/runs/boundary-design-NEW \
  --output /home/wangziheng/wafer_simulator/runs/boundary-design-analysis-NEW
```

`wafer-sim` exposes the same commands when the package entry point is installed.
`goal-replay` explicitly selects the historical full-capture campaign; it is not
the current default example. Timeout or truncated work never counts as complete.

## Interpretation and evidence

Results distinguish execution completion, semantic audit, capacity status
(`feasible`, `violated`, `unmodeled`), reference agreement and hardware calibration.
A diagnostic pipeline with RX overflow is not a feasible design even if its
predicted time is correct. bounded is a reference for the declared mechanisms,
not measured hardware truth. Network resources differ between the two designs;
these are not equal-area or equal-bandwidth comparisons. No thermal claims.

Every accepted run retains source/input/binary/environment hashes, events,
independent byte/lifetime/timing audits and explicit completion status. Raw traces,
builds and full event tables stay on eex005; compact checked results are in Git.

## Source organization and completed work

`workloads/` defines logical work; `architecture/` target resources; `adapters/`
binds targets and integrates pinned geometry/BookSim; `execution/` manages
admission, lifetimes and timing; `analysis/` audits and compares; `experiments/`
only orchestrates. These live under `src/wafer_sim/`. Fixed controls are in
`configs/`, semantic regressions in `tests/`, native changes in `patches/`.
`third_party/` contains [pinned ordinary author source](docs/EXTERNAL_SOURCES.md),
with notices preserved and no in-place edits or submodule dependency.

Maintain one branch, `main`, in this repository. See the
[current research contract](docs/RESEARCH_DIRECTION.md),
[milestone index](docs/MILESTONES.md), [source audit](docs/UPSTREAM_AUDIT.md),
[storage/provenance cleanup](docs/results/remote-cleanup-001/REVIEW.md), and
[historical GOAL protocol](docs/LLAMA16_PROTOCOL.md).
