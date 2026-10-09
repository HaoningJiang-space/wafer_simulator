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

The [4×4/6×6/7×7 coverage study](docs/results/spatial-scaling-001/REVIEW.md)
is now complete: 27 cells, 81 executions and 27 native replays. With fixed
per-tile work/resources, remote balanced storage wins over clustered nearby
storage at 4×4, but loses at 6×6/7×7 in S. U1 predicts the opposite direction
at those two larger sizes; gap errors are 7,164 / 7,902 cycles. Capacity waits
are zero. This identifies a spatial service limitation in the uniform model,
not proof of network saturation or of a minimum required flit-level model.

The [isolated-response mechanism test](docs/results/isolated-response-001/REVIEW.md)
is complete. With the same graph and 65,536-byte response, zero to five C2C
hops leave injection span fixed at 1,987 cycles; each hop adds 21 cycles to
completion. Matched original-work responses instead exhibit much longer
injection spans and temporally shared outputs. Distance alone does not explain
their extra service time. Any future lightweight candidate must address shared
paths and overlapping demand as well as effective single-flow service. This
test adds no U2 and does not establish a minimal queue/credit model.

## Current entry point (hn072 only)

Local work is source inspection, editing and Git. Builds, tests and execution
run on `hn072@143.89.78.72`, under `/Projects/haoning/wafer_simulator`.
Use fresh output directories and existing pinned native binaries.

```bash
cd /Projects/haoning/wafer_simulator/source
export PYTHONPATH=src
../.venv/bin/python scripts/test_wow_target_remote.py \
  /Projects/haoning/wafer_simulator/runs/isolated-response-tests-NEW
../.venv/bin/python -m wafer_sim.experiments.isolated_response \
  --tests /Projects/haoning/wafer_simulator/runs/isolated-response-tests-NEW/SEMANTICS.json \
  --accepted /Projects/haoning/wafer_simulator/runs/spatial-scaling-001 \
  --output /Projects/haoning/wafer_simulator/runs/isolated-response-NEW
../.venv/bin/python -m wafer_sim.analysis.isolated_response \
  /Projects/haoning/wafer_simulator/runs/isolated-response-NEW \
  /Projects/haoning/wafer_simulator/runs/isolated-response-analysis-NEW
```

This reproduces the [registered isolation protocol](docs/ISOLATED_RESPONSE_PROTOCOL.md):
ten conditions, two fresh processes each, one native command replay per condition.
It reuses the accepted scaling evidence without rerunning applications. No
timeout or truncated response can produce a completion receipt. General scaling
and model enhancement remain closed. The next method question is whether a
cheaper shared spatial service approximation preserves the frozen layout
decisions; the present mechanism evidence does not preselect its implementation.

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
results stay on the active server, with source/input/binary/environment/result hashes.
Historical eex005 results are preserved in a fully verified compressed archive;
see [server relocation and recovery](docs/results/server-migration-001/REVIEW.md).
Compact accepted reports are indexed in [MILESTONES.md](docs/MILESTONES.md).

Historical commands remain available through `wafer-sim boundary-design`,
`group-sharing`, their analysis commands and `goal-replay`. They do not launch
the new candidate machine implicitly. The
[GOAL protocol](docs/LLAMA16_PROTOCOL.md), [source audit](docs/UPSTREAM_AUDIT.md)
and [cleanup evidence](docs/results/remote-cleanup-001/REVIEW.md) remain preserved.
