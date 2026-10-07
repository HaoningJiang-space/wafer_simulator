# Spatial Workload Execution for Wafer-Scale Systems

Pinned author geometry and BookSim, complete same-workload execution, independent
completion checks, and placement comparison. Read [the source audit](docs/UPSTREAM_AUDIT.md)
for what is reused, repaired, and not claimed.

The [research direction](docs/RESEARCH_DIRECTION.md) derives a compute–memory–network
execution contract from spatial locality and finite resources. It separates
logical work, compute/data mapping, execution policy and target resources.
The [spatial contract v1](docs/SPATIAL_CONTRACT.md) implements separate work/data
identities, target binding and finite-region storage lifetimes. It declares
service demands but does not yet predict time or retarget the full Llama capture.
The current implementation is a
conditional WoW replay with partial communication retargeting; it does not yet
implement a source-machine-independent workload model.

The research question is whether a WoW Logic-on-Interconnect placement with
better network metrics also completes the same AI workload sooner, and which
execution costs must be modeled to make that judgment. The current study
compares Baseline and Rotated under fixed operating conditions. It tests one
specific boundary: original GPU-cluster-local transfers represented as fixed
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
`execution` and `analysis`; `experiments` orchestrates these layers. The current
timed replay uses native BookSim. `configs/` contains fixed controls;
`patches/` contains isolated upstream changes. All reused external source is
included as [pinned ordinary files](docs/EXTERNAL_SOURCES.md) under `third_party/`.
A normal clone of this repository obtains all project source. The maintained
branch is `main`.

The research sequence is workload abstraction, target compute–memory–network
execution, layered validation, then a fixed-mapping Baseline–Rotated application
case. Subsequent studies jointly vary topology, mapping and workload. Basic
geometry/connectivity/capacity belongs in the first machine model; detailed
physical closure and power/thermal remain later work.

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

The formal input is the complete public ATLAHS Llama 7B 16-GPU GOAL capture,
downloaded **only on eex005**. It is not the missing WoW paper capture. See
[the registered controls and input limits](docs/LLAMA16_PROTOCOL.md).
Generated workloads remain unit-test fixtures only; no smoke/prefix experiment
is part of the formal campaign. `COMPLETE.json` is written only after both
full placement arms pass the independent all-operation audit.

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

The [collective frontend](docs/results/collectives-001/REVIEW.md) now recovers
operand roles and bytes for all 33,632 CPU collective calls in the full source.
Explicit identities match 3,840 calls into 2,790 instances; 29,792 coalesced calls
remain unresolved rather than being matched by order or size. The
[target collective contract](docs/COLLECTIVES.md) adds shared finite storage,
memory/network/reduction demands and rank-local completion. All 101 semantic
tests and the full-source readback pass. This is a resource-demand and completion
interface; tensor-version integration and calibrated application timing remain.
