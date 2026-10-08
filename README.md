# Wafer-Scale Simulator

**Current objective:** determine which spatial compute–memory–communication
abstractions support application timing, capacity and layout decisions.

The [candidate machine](docs/WAFER_MACHINE.md) is a stitched compute wafer plus
an aligned memory wafer. It explicitly defines SRAM, banks, shared controllers,
vertical HB and edge I/O. Logical work and data placement compile to request,
response, compute and memory services on the existing timed executor and live
BookSim. `spcl/nw-design-for-wsi` remains a pinned LoI network baseline; it does
not prescribe the simulator's entire machine organization.

All candidate resource numbers are **declared design assumptions**, not measured
DRAM timing or a qualified TSMC/Cerebras system. Whole-object controller staging
and an analytical bank service are explicit policies. See the
[current research scope](docs/RESEARCH_DIRECTION.md) and
[registered machine validation](configs/wafer_machine_validation.json).

The [U0/U1/S comparison](docs/results/memory-abstraction-001/REVIEW.md) is complete:
9 cells, 54 full executions, 192 related tests and 840 rechecked artifact hashes.
S exactly reproduces the [accepted machine](docs/results/wafer-machine-001/REVIEW.md)
times of 23,903 / 27,096 / 75,032 cycles. Uniform communication in both U0 and U1
loses the 3,193-cycle near-versus-remote distinction; preserving controllers
recovers much of the concentrated-storage penalty but not its full magnitude.
The cheaper projections fail this study's timing and gap-error budgets.
See the [model choice](docs/results/memory-abstraction-001/model_selection.md):
these are reference-relative findings under declared policies, not hardware
accuracy or a claim that every fine network detail is necessary.

## Current entry point (eex005 only)

Local work is source inspection, editing and Git. Builds, tests and execution
run on `wangziheng@eex005`, under `/home/wangziheng/wafer_simulator`.
Use fresh output directories and existing pinned native binaries.

```bash
cd /home/wangziheng/wafer_simulator/source
export PYTHONPATH=src
/home/wangziheng/wafer_simulator/.venv/bin/python scripts/test_wow_target_remote.py \
  /home/wangziheng/wafer_simulator/runs/memory-abstraction-tests-NEW
/home/wangziheng/wafer_simulator/.venv/bin/python -m wafer_sim.experiments.memory_abstraction \
  --tests /home/wangziheng/wafer_simulator/runs/memory-abstraction-tests-NEW/SEMANTICS.json \
  --output /home/wangziheng/wafer_simulator/runs/memory-abstraction-NEW
/home/wangziheng/wafer_simulator/.venv/bin/python -m wafer_sim.analysis.memory_abstraction_study \
  /home/wangziheng/wafer_simulator/runs/memory-abstraction-NEW \
  /home/wangziheng/wafer_simulator/runs/memory-abstraction-analysis-NEW
```

This reproduces the [registered same-machine abstraction study](docs/MEMORY_ABSTRACTION_PROTOCOL.md).
U0 pools DRAM service/capacity while retaining physical staging guards; U1
retains controllers/banks but simplifies communication; S uses the physical
paths. No timeout or truncated work can produce a completion receipt.
The next coverage task is larger physically legal machine/work configurations
with preregistered scaling rules. Other model features remain frozen.

## Retained model-selection evidence

The [two-group study](docs/results/group-sharing-001/REVIEW.md) completed 12
configurations and 36 executions in one shared native network. Actual paths and
message times changed, but neither group's final completion slowed down.
Joint bounded times were 55,743/55,629 cycles; serial gave 54,306/54,144, with
a +48-cycle design-gap error. This is limited-coverage evidence, not saturation.

The [paired boundary study](docs/results/boundary-design-001/model_selection.md)
completed 24 configurations and 72 runs. Serial gap errors were
+8/+44/+20/-12 cycles despite larger absolute-time errors. It did not reliably
classify near-equal designs. Pipeline matched time but violated RX capacity.
These completed studies retain their original contracts; new machine results
must not be spliced into their tables as if only one abstraction had changed.

Execution completion, semantic audit, storage/FIFO feasibility, reference
agreement and hardware calibration are separate statuses. A model can predict
time well without validating capacity or physical feasibility. No equal-cost,
thermal, native wafer training-time or hardware-accuracy claim is implied.

## Source organization and evidence

`workloads/` defines work; `architecture/` physical resources; `adapters/` binds
and integrates; `execution/` manages admission, lifetimes and timing;
`analysis/` independently audits; `experiments/` only orchestrates. These are
under `src/wafer_sim/`. Fixed controls are in `configs/`, regressions in `tests/`.

Maintain one branch, `main`. `third_party/` delivers
[pinned ordinary upstream files](docs/EXTERNAL_SOURCES.md) with notices preserved;
reviewed native changes are in `patches/`. Raw inputs, events, builds and large
results stay on eex005, with source/input/binary/environment/result hashes.
Compact accepted reports are indexed in [MILESTONES.md](docs/MILESTONES.md).

Historical commands remain available through `wafer-sim boundary-design`,
`group-sharing`, their analysis commands and `goal-replay`. They do not launch
the new candidate machine implicitly. The
[GOAL protocol](docs/LLAMA16_PROTOCOL.md), [source audit](docs/UPSTREAM_AUDIT.md)
and [cleanup evidence](docs/results/remote-cleanup-001/REVIEW.md) remain preserved.
