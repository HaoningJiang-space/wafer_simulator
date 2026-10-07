# Spatial Workload Execution for Wafer-Scale Systems

Pinned author geometry and BookSim, complete same-workload execution, independent
completion checks, and placement comparison. Read [the source audit](docs/UPSTREAM_AUDIT.md)
for what is reused, repaired, and not claimed.

**Current research focus:** [aggregate reticle resource validity](docs/RETICLE_BOUNDARY_RESEARCH.md).
Freeze collective and mapping expansion. Distinguish parameter uncertainty,
abstraction error and changed hardware; compare accuracy/cost against a justified
reference for the same declared machine. Local NoC and boundary feedback remain
candidate mechanisms, not mandatory next modules. Existing rankings are validation cases,
not evidence that a detailed simulator is necessary. The generic cost sweep remains
deferred. A [bounded matched-path experiment](docs/results/transfer-granularity-001/REVIEW.md)
has now completed: two full blocks have only 0.367%/0.204% coarse application error,
but up to 15%/42.857% isolated message-service error. Whole-message hop-by-hop
service misses native pipelining. The coarse execution stage costs about half as
much here. This supports retaining it for the declared 2% application-time target,
not validating shared local-resource assumptions or sub-percent design gaps.

A [restricted packet-pipeline refinement](docs/results/packet-pipeline-001/REVIEW.md)
now reuses the event calendar with source-derived packet initiation timing.
On the same two complete blocks, application error becomes 0%/0.0154%, and
isolated service error becomes zero. The remaining maximum in-application
message error is 3.5714%, localized to service order on a shared output link.
Measured execution costs are about 2.4–2.5 times lower than BookSim here.
This optional model does not reproduce finite-credit/input arbitration or
adaptive routing, and does not replace the default backend or validate reticle
compute/SRAM aggregation. Both original backends retain exact accepted events.

The [memory–network boundary study](docs/results/memory-boundary-001/REVIEW.md)
now holds native BookSim fixed and compares whole-message stages, chunk service,
and finite receiving credit. Under the registered streaming-DMA hypothesis,
s16/s64 become 13,583/55,944 cycles, versus 12,534/51,966 for whole-message stages.
Chunk requests interleave with rank-local work on the shared memory port; overlap
does not imply a faster complete application. Immediate-credit chunk service
matches these makespans but exceeds the eight-slot RX budget (18/60 slots) and
misestimates individual message commits. The optional bounded endpoint model
preserves capacity and checked lifetimes, at higher measured execution cost.
This is conditional boundary-model evidence, not calibrated native wafer timing.
151 tests, 30 complete runs, 460 artifact hashes and 18 command replays passed.

The [memory-service isolation](docs/results/memory-service-isolation-001/REVIEW.md)
now separates native flit width from memory arbitration quantum. Applying the
same 256-byte burst contract to ordinary memory clients and DMA reduces the
streaming-versus-serial gap from 1,049/3,978 to 253/1,355 cycles (s16/s64).
Memory bandwidth, useful bytes and busy cycles are unchanged across the two
memory contracts within each boundary model; request interleaving changes.
Finite RX still changes message commits/capacity, not these application times.
This is policy interaction, not a measured pure-overlap penalty. All 36 complete
executions pass readback; request-atomic controls reproduce the earlier full
event records. The default remains unchanged; 256 bytes is a diagnostic assumption.

The [research direction](docs/RESEARCH_DIRECTION.md) derives a compute–memory–network
execution contract from spatial locality and finite resources. It separates
logical work, compute/data mapping, execution policy and target resources.
The [spatial contract v1](docs/SPATIAL_CONTRACT.md) implements separate work/data
identities, target binding and finite-region storage lifetimes. The
[timed resource backend](docs/TIMED_EXECUTION.md) now turns compute work, memory
bytes and network transfers into completion events using explicit target rates
and shared-resource queues. The first [complete analytical execution](docs/results/timed-execution-001/REVIEW.md)
finishes in 113 cycles, with separately checked compute, memory and network
rate interventions. This target execution capability is distinct from the
accepted full Llama path, which remains a conditional WoW replay with partial
communication retargeting.

The [complete Transformer forward block](docs/TRANSFORMER_EXECUTION.md)
now executes on the same backend: 30 operations, two SUM AllReduces and 557,056
MACs. Its [initial result](docs/results/transformer-execution-001/REVIEW.md) was
15,862 cycles under the original generic lowering, with separate resource-rate
controls; the collective correction below supersedes that lowering. Dense numerical equivalence passes. These
parameters are analytical, not calibrated WoW compute or SRAM specifications.

The block now uses the existing **collective action DAG** with the live author
WoW network. This fixes the generic binder's duplicated root result write and
allows independent gathers to overlap. The [corrected TP2 pair and bounded
TP4/TP8 study](docs/results/collective-execution-001/REVIEW.md) report
**12,550 cycles on Baseline and 12,918 on Rotated** for the original four-head
TP2 block. A serialized-action control separates 256 cycles from corrected
materialization and another 256 from overlap. The old 13,062/13,430 result is
retained with a correction notice; its 368-cycle placement gap remains.

The separate eight-head study observes 3/7 simultaneous messages at TP4/TP8.
Row-major and nearest-root mappings change the placement ordering, but the
differences are small. TP8 nearest-root lowers average message time yet increases
application time: shared root-memory service and the last critical broadcast
matter. All twelve corrected/control/study arms pass independent execution and
standalone BookSim timestamp checks. See [collective timing](docs/COLLECTIVE_TIMING.md)
and the [network interface](docs/TRANSFORMER_WOW_PROTOCOL.md).

The [rank-local and memory-balance result](docs/results/rank-local-balance-001/REVIEW.md)
now separates each rank's output readiness from collective retirement. All eight
existing TP4/TP8 cases retain their completion times despite earlier local work;
the tail rank still determines the next collective and final output. A fixed TP8
row-major memory-bandwidth sweep from 32 to 1024 B/cycle changes Baseline/Rotated
from 12,534/12,452 to 4,461/4,225 cycles. The gap is nonmonotonic across the sweep.
The high-bandwidth range is compute dominated with greater network sensitivity,
not a demonstrated network-bandwidth bottleneck. See the
[completion policy and experiment protocol](docs/RANK_LOCAL_BALANCE.md).

The [fixed binary-tree study](docs/results/tree-spatial-001/REVIEW.md) adds a
second spatial communication structure at three existing memory regimes. Both
algorithms move 114,688 logical bytes and perform 14,336 collective adds per
block. Tree spreads endpoint and memory pressure, but adds partial-result
memory service and communication depth. Direct-root favors Rotated; this fixed
tree favors Baseline at all three points. At 1024 B/cycle the pairs are
4,461/4,225 (direct) and 4,697/5,005 (tree). Rotated's lower tree byte-hops and cut
traffic coexist with a longer serialized critical branch. This is a conditional
algorithm/topology interaction, not evidence of network saturation or a universal
placement ranking. Six direct arms were reused and six tree arms added; 130 tests
and all twelve current-code readbacks pass. See [protocol](docs/TREE_SPATIAL_PROTOCOL.md).

The research question is whether a WoW Logic-on-Interconnect placement with
better network metrics also completes the same AI workload sooner, and which
execution costs must be modeled to make that judgment. The current block study
compares Baseline and Rotated under fixed operating conditions. The earlier
full-capture experiment tests a separate boundary: original GPU-cluster-local transfers represented as fixed
`calc` costs versus those same transfers competing for target wafer resources.
Remaining measured intervals and reduction/copy costs stay fixed. This is a
controlled workload-model comparison, not calibrated native wafer training
time. Thermal modeling and further simulator optimization are deferred.

The repository maintains one native implementation: the selected CSR-frontier
version, including the preceding completion, routing-reference, dense-state and
node-reuse changes. The combined `patches/booksim-wafer.patch` applies directly
to the pinned author revision. There are no alternative optimization builds or
configs in the working tree. See [selection and verification](docs/IMPLEMENTATION.md).

Code layers separate `workloads`, `architecture`, target-binding `adapters`,
`execution` and `analysis`; `experiments` orchestrates these layers. Full-capture
replay uses native BookSim; the target resource calendar can submit live
transfers to that same kernel or use the retained coarse store-and-forward
model. The native adapter changes the driver interface, not the network kernel.
`configs/` contains fixed controls;
`patches/` contains isolated upstream changes. All reused external source is
included as [pinned ordinary files](docs/EXTERNAL_SOURCES.md) under `third_party/`.
A normal clone of this repository obtains all project source. The maintained
branch is `main`.

The current research sequence is a declared target-resource contract, matched
simulation abstractions, independent mechanism checks, complete-work prediction
errors and measured simulation cost. Existing collective/placement cases support
that comparison; further algorithms and mapping studies are deferred. Basic
geometry/connectivity/capacity remains part of the machine contract. Detailed
physical closure and power/thermal remain outside this milestone.

Current development has progressed from the complete A/fanout-B/AllReduce/C
unit to a separately defined Transformer forward block on both WoW placements. Old Chakra recovery
is frozen and is not a prerequisite. A supported full application remains a
later input. Mstatic remains a separate pending M0/M1 model comparison; the
block study does not rerun or replace the full-capture experiment.

Build, tests and experiments run on `wangziheng@eex005`. Local work is editing,
source review, and Git. The remote root is `/home/wangziheng/wafer_simulator`.

```bash
# On eex005, in the source checkout:
/home/wangziheng/wafer_simulator/.venv/bin/python scripts/restore_upstreams_remote.py
bash scripts/build_remote.sh
bash scripts/test_remote.sh /home/wangziheng/wafer_simulator/runs/semantics-NEW

# When starting a new full experiment, use a fresh output directory:
bash scripts/run_full_remote.sh /home/wangziheng/wafer_simulator/runs/llama16-full-NEW
```

The entry points use `build/booksim/rapidchiplet/booksim2/src/booksim` and
`configs/llama16_fixed_state.json`. Correctness tests retain the frozen author
binary at `build/booksim-reference/rapidchiplet/booksim2/src/booksim` only as a
regression oracle. Arbitration checks use saved reference-derived grants.
An optional second argument to `test_remote.sh` compares saved semantic events
against the selected implementation; it does not launch an older variant.

Every run keeps configuration, workload, mapped trace, endpoint map, native
configuration, raw stdout/stderr, binary/input hashes, per-event completion
report, independent audit, and paired comparison. Result directories must be
new. Wall-clock timeout is never treated as application completion.

The formal GOAL comparison uses the complete public ATLAHS Llama 7B 16-GPU capture,
downloaded **only on eex005**. It is not the missing WoW paper capture. See
[the registered controls and input limits](docs/LLAMA16_PROTOCOL.md).
For that campaign, generated workloads remain unit-test fixtures; no smoke or
prefix experiment substitutes for the full capture. Its `COMPLETE.json` requires
both full placement arms to pass the independent all-operation audit. The
separately named analytical target-execution units have their own contracts,
completion records and evidence limits, and do not replace this input.

Historical optimization notes and existing remote runs remain evidence. Their
old build scripts and incremental patches are recoverable at Git commit
`f530c82`; they are not maintained implementation choices. The completed full
runs and their automatic event comparisons remain recorded. Duplicate bulk
files in obsolete runs resolve to the identical retained 006 artifacts through
the [cleanup receipt](docs/results/remote-cleanup-001/REVIEW.md). See
[run status](docs/LLAMA16_RUN_STATUS.md), [CSR semantics](docs/CSR_FRONTIER.md),
and [HeteroSTA transfer](docs/HETEROSTA_TRANSFER.md).

The [placement attribution stage](docs/POSTRUN_PROTOCOL.md) has recovered both
critical chains and paired the complete message set from existing full events.

The [006 placement result and reviewed interpretation](docs/results/llama16-006/REVIEW.md)
are now available: mean packet latency falls by 14.7490%, while complete
conditional replay time falls by 0.13603%. Both full arms and attribution pass;
direct full-event equivalence to reference 002 has now
[passed for both placements](docs/results/model-boundary-001/implementation_equivalence.json).
The earlier report is preserved as a dated snapshot.

The [local-stage source audit](docs/LOCAL_STAGE_PROVENANCE.md) is complete.
It identifies the two dominant calc operations as composite measured intervals
and recovers 1,337,280 intra-host transfers. Complete M0 lowered traces and
contracts are unchanged. One [registered M0/M1 study](configs/llama16_model_boundary.json)
reuses M0 and has completed both M1 placements with those transfers on target resources.
Mapping experiments remain deferred; the native binary remains frozen 006.
The [accepted M0/M1 comparison](docs/results/model-boundary-001/REVIEW.md) records
a placement-gap change from 2.365264 ms to 13.118157 ms (completion-time reduction
0.136030% to 0.642944%). Both modeled completion times increase. This establishes
model sensitivity, not native wafer accuracy or a need for dynamic contention
instead of simpler target costs.

Earlier deliverables are the source table above, the
[target-resource mapping](docs/TARGET_RESOURCE_MAPPING.md) and the
[M0/M1 protocol](docs/MODEL_BOUNDARY_PROTOCOL.md). No new experiment is launched
by this documentation stage. Current development is complete-source workload
normalization; static versus shared costs remains a later abstraction comparison.

The [complete Chakra source check](docs/results/chakra-normalization-001/REVIEW.md)
has read all 16 published ranks and recovered 123,520 matrix primitives with
shape-derived work and operand bytes. The official reader agrees on all
4,530,939 nodes. Capture identity with the accepted GOAL input is not established;
tensor versions, remaining operators and target service timing are still needed
before full spatial execution. All raw files and the detailed ledger stay on
eex005. The [offline source restoration check](docs/results/source-bundle-001/VALIDATION.json)
also verifies all six bundled author trees and the frozen native patch.

The subsequent [tensor-value milestone](docs/results/tensor-effects-001/REVIEW.md)
adds explicit allocation generations, exact byte-region versions and call-effect
binding. All 53 semantic tests pass; complete effect ledgers preserve every
node and dependency in the 16-rank source. This milestone adds no application timing.

The [call-ownership frontend](docs/results/call-regions-001/REVIEW.md) now assigns
all 4,530,939 source records to 3,598,591 regions using explicit subtree recipes,
retaining every original dependency port. All 73 semantic tests and the full
16-rank independent readback pass. Supported parents own their implementation
records once; unresolved scopes stay explicit. Full target lowering still needs
collective completion, compiled-scope interpretation and layout/allocation
recovery before these regions can define wafer resource activity or timing.

The [collective frontend milestone](docs/results/collectives-001/REVIEW.md) recovers
operand roles and bytes for all 33,632 CPU collective calls in the full source.
Explicit identities match 3,840 calls into 2,790 instances; 29,792 coalesced calls
remain unresolved rather than being matched by order or size. The
[target collective contract](docs/COLLECTIVES.md) adds shared finite storage,
memory/network/reduction demands and rank-local completion. All 101 semantic
tests and the full-source readback pass. This is a resource-demand and completion
interface; tensor-version integration and calibrated application timing remain.

The [value/lifetime integration milestone](docs/results/collective-values-001/REVIEW.md)
connects matched collective ports to immutable tensor versions and shared finite
storage. Existing versions pass between collectives without a second input
allocation; consumers release them only after completion. All 119 semantic tests
pass. A complete join checks all 33,632 source calls and their implementation/wait
ports against the 4,530,939-node ownership/effect ledgers. Exact allocation
generations, layouts and access order remain explicit missing inputs for the
capture; no guessed versions or new application timing are reported.

The [current recovery result](docs/results/collective-recovery-001/REVIEW.md)
replaces the blanket missing-evidence decision with per-call recovery. All
33,632 calls and their original ports remain: 20 barrier instances bind without
tensor payload, and 1,600 singleton broadcasts have input-version forwarding
recipes. Unknown singleton reductions are now correctly unresolved, rather than
assumed identities. The target lifetime path forwards proved identities without
another write, allocation or copy. There are still 29,792 calls without explicit
communicator/sequence; none are guessed. The
[conversion repair](docs/SOURCE_RECOVERY.md) preserves optional original strides
and binds exact footprints to explicit live allocations. All 137 semantic tests
and four actual upstream conversion tests pass on eex005. This is not yet a
fully bound or timed target Llama workload.
