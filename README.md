# Wafer-Scale Simulator

**Current objective:** define a wafer computer independently of one network
baseline, then determine which spatial resource details its simulation needs.

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

The [first machine acceptance](docs/results/wafer-machine-001/REVIEW.md) completed
three full same-work cases: 23,903 / 27,096 / 75,032 cycles for near, offset and
concentrated bank placement. All 183 related tests, three event audits and
three native command replays pass; 65 artifact hashes and exact compiled-input
equivalence were rechecked. These validate integration under the declared
policy, not physical calibration or superiority of a new simulation method.

## Current entry point (eex005 only)

Local work is source inspection, editing and Git. Builds, tests and execution
run on `wangziheng@eex005`, under `/home/wangziheng/wafer_simulator`.
Use fresh output directories and existing pinned native binaries.

```bash
cd /home/wangziheng/wafer_simulator/source
export PYTHONPATH=src
/home/wangziheng/wafer_simulator/.venv/bin/python scripts/test_wow_target_remote.py \
  /home/wangziheng/wafer_simulator/runs/wafer-machine-tests-NEW
/home/wangziheng/wafer_simulator/.venv/bin/python -m wafer_sim.experiments.wafer_machine \
  --tests /home/wangziheng/wafer_simulator/runs/wafer-machine-tests-NEW/SEMANTICS.json \
  --output /home/wangziheng/wafer_simulator/runs/wafer-machine-NEW
```

This runs three complete declared machine-integration cases; it is not a
topology search, full Llama reproduction or memory-abstraction accuracy study.
Data placement differs while logical work, task placement and machine stay fixed.
No timeout or truncated work can produce a completion receipt.

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
