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

The [registered v1 D1 comparison](docs/results/shared-spatial-service-001/REVIEW.md)
is complete: 81 applications, 18 native replays and 256 tests; 152 existing
component records revalidated. D1 recovers all layout-pair directions and lowers
application MAPE to 1.201%, but passes only 8/9 application points and 0/9
100-cycle gap budgets. Complete fresh workers are 8.03–13.81× faster than S;
prior calibration is separate. D0/S frozen events reproduce exactly. Both D0
and D1 already select Local globally, with zero reference choice regret.
This is a partial result for one fixed hypothesis, not a reason to retune it.

The [source-order and local-merge diagnosis](docs/results/source-order-001/REVIEW.md)
uses saved components/applications and four component-only Python probes. Ordering
one head per source restores the common-source finish times, but its second head
still starts 60 cycles after native selection. Three distinct-source flows remain
inaccurate; a shared output records 501/501/1,002 flits from two input branches.
All 69 saved S critical messages have zero source-generation wait, whereas
two-plus-one local input structure occurs in 6×6/7×7 B critical responses.
Source ordering explains the component counterexample, but is not established as
the primary application-gap cause. That historical study added no native or application run.

The [local-service reconstruction](docs/results/local-service-001/REVIEW.md)
is complete: six small Native observations preserve full accepted events, with
zero new application runs. The focal single VC filters inputs before switch
allocation; overlapping components have competing VC requests but no multi-input
switch requests. A local FIFO/ownership/pipeline replay computes eligibility from
observed arrivals and credit returns, matching all 36,864 service-clock comparisons
and 22,506 allocator-call checks. This is conditional diagnosis, not independent
network prediction, an application-gap result or a speedup claim.

The [G1 causal-closure test](docs/results/causal-closure-001/REVIEW.md) now
composes four local routers without Native arrival or credit inputs. Seven cases,
including staggered/queued sources and tight credits, match full flit/message,
service and drainage events. Fourteen completed Native component runs preserve
observer equivalence; 13 regressions and seven negative probes pass. This closes
independent prediction in the registered tree domain, with no application
integration or service-compression result.

The [stricter G1 audit](docs/results/causal-closure-audit-fix-001/REVIEW.md)
revalidates all seven saved cases with identical result bytes; 29 regressions
and 19 real-data negative probes pass without new Native runs. The subsequent
[read-only compressibility audit](docs/results/causal-compressibility-001/REVIEW.md)
finds repeated causal kernels and emitted boundaries in three fixed cases,
including credit-blocked service. Remaining work stays explicit: no cycle is
skipped in that audit. The subsequent
[G2.1 receipt](docs/results/causal-macro-single-001/REVIEW.md) verifies guarded
single-flow two-cycle batching with exact expanded events and entry/exit state.
At 32,768 flits it reduces 65,598 updates to 296 and yields 23.02× same-core
counters-worker acceleration; reconstructable evidence cost is separate.
This is not a general backend or a BookSim/application speedup.
The [R1 explicit core](docs/results/causal-transition-001/REVIEW.md) now exposes
state, immutable snapshots and one-cycle execution without AST or analysis
dependencies. Seven G1 cases match all 30,604 state boundaries and full saved
predictions; 56 targeted regressions pass. G1/G2.1 references remain unchanged;
macro migration and evidence-sink separation are still deferred.

The [information and boundary evidence](docs/NECESSARY_INFORMATION.md) separates
observed failures from constructed distinguishing cases. S remains the detailed
reference under each declared machine contract. Preserve necessary boundary
behavior before compressing repeated computation. Machine organization and
transaction policy remain separate research axes.

The [first S cost profile](docs/results/native-service-profile-001/REVIEW.md)
covers 6×6/7×7 B: four controlled executions preserve complete events and
native protocol bytes. Native advancement and flit/path recording both matter;
JSON and auditing also cost time. Evidence-path work with explicit equivalence
checks is independent engineering, not a prerequisite for the source/merge
study. No lightweight mode or event-compressed backend is published.

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
