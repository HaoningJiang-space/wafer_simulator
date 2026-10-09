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
their extra service time. This test adds no U2 and does not establish a minimal
queue/credit model.

The [independent spatial service baseline D0](docs/results/independent-spatial-service-001/REVIEW.md)
is now accepted: 1,700 independently calibrated endpoint/size conditions,
3,460 component captures, 81 U1/D0/S application executions and 209 tests.
D0 restores Local's 23,903 cycles and selects Local globally at every size;
application MAPE falls to 6.724%. It still chooses the wrong A/B layout at
6×6/7×7, with gap errors of 6,870 / 7,608 cycles versus the unchanged 100-cycle
budget. Correct single-flow/path service is useful but insufficient for that
tradeoff. Calibration uses no full-S timings, routes or overlaps. Prediction
is cheaper, with its 628-second calibration cost reported separately.

The [memory-periphery policy comparison](docs/results/memory-periphery-001/REVIEW.md)
now completes six 6×6 A/B cells, 18 applications, nine components and 15 native
replays. Giving each controller one shared interface leaves whole-object times
at A=30,645 / B=31,303 cycles. At that same organization, fixed 4 KiB fragments
and a four-fragment window give A=25,345 / B=23,561: the preferred member changes
from A to B. Original v1 events reproduce exactly. This shows policy sensitivity
of this restricted layout judgment; it does not replace the accepted v1 results
or validate hardware. The pipeline includes external-controller traffic and
keeps full-object reservations, operand order and retirement rules.

The [acceptance repair and revalidation](docs/results/memory-periphery-audit-fix-001/REVIEW.md)
now rejects incorrect publication plans, semantically inconsistent summaries
and invalid actual NIC port budgets. All 27 saved executions pass the stronger
reader and reproduce the original results; 239 remote regressions pass.
No new application simulation was needed. The window is explicitly
[ideal_commit_visibility](docs/MEMORY_WINDOW_CONTRACT.md), with no remote
notification delay and no controller-wide DMA or certified RX budget.
The [saved-trace analysis](docs/results/memory-periphery-attribution-001/INTERPRETATION.md)
finds earlier supply and changed critical chains; B improves without observed
source packet-order or route changes, and its critical payload envelopes do
not uniformly improve. Neither declared contract is selected as hardware truth.

The [registered D1 candidate](docs/SHARED_SPATIAL_SERVICE_PROTOCOL.md) is retained
under v1. Its component study completed; its application matrix has not run.
Machine organization and transaction policy remain explicit declared contracts;
their accepted comparison and repair rounds are closed.

The [public periphery APIs](docs/PUBLIC_PERIPHERY_API.md) separate compilation,
execution and supplied-event audit from private study/server orchestration.
`PYTHONPATH=src python scripts/test_public.py` runs the portable semantic suite;
`wafer-sim audit-periphery` audits small input/event JSON without application
lowering, a native process or server configuration. The registered contracts
and f91824d behavior remain the baseline.
The [checked extraction](docs/results/public-periphery-api-001/REVIEW.md) passes
254 formal and 141 portable regressions, retaining 11 fixed-case event/state
identities and all 15 registered inputs. Three saved native components audit
through the public API; no application matrix was rerun.

## Current entry point (hn072 only)

Local work is source inspection, editing and Git. Builds, tests and execution
run on `hn072@143.89.78.72`, under `/Projects/haoning/wafer_simulator`.
Use fresh output directories and existing pinned native binaries.

```bash
cd /Projects/haoning/wafer_simulator/source
export PYTHONPATH=src
../.venv/bin/python scripts/test_wow_target_remote.py \
  /Projects/haoning/wafer_simulator/runs/periphery-tests-NEW
../.venv/bin/python -m wafer_sim.experiments.revalidate_periphery \
  --source /Projects/haoning/wafer_simulator/runs/periphery-applications-001 \
  --output /Projects/haoning/wafer_simulator/runs/periphery-revalidation-NEW \
  --tests /Projects/haoning/wafer_simulator/runs/periphery-tests-NEW/SEMANTICS.json
```

This revalidates the saved [periphery comparison](docs/MEMORY_PERIPHERY_PROTOCOL.md)
with current semantic checks. Its original native campaign enforces exact frozen
source files; reproduce it at pinned `1c7a84a` in an isolated checkout, with that
checkout's own same-source test receipt. Do not relax that gate to rerun on main.
Historical D0 orchestration enforces exact frozen source files; reproduce that
study from pinned `dc18ed1` in an isolated checkout. Current main preserves v1
behavior through regression, export equivalence and accepted A/B event hashes.
The repaired reader records its own source, archived source compatibility,
same-source tests and event-derived values separately from old receipts.
The [D0 contract](docs/INDEPENDENT_SPATIAL_SERVICE.md) explains calibration,
bounded lookup and independent audits. No timeout or truncated response can
produce a completion receipt. Future approximation comparisons must fix the
organization and policy first. This study adds no native buffer/credit intervention.

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
