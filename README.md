# Spatial Workload Execution for Wafer-Scale Systems

Pinned author geometry and BookSim, complete same-workload execution, independent
completion checks, and placement comparison. Read [the source audit](docs/UPSTREAM_AUDIT.md)
for what is reused, repaired, and not claimed.

The [research direction](docs/RESEARCH_DIRECTION.md) derives a compute–memory–network
execution contract from spatial locality and finite resources. It separates
logical work, compute/data mapping, execution policy and target resources.
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

Code layers: `workloads` → `adapters` → native BookSim → `analysis`;
`experiments` orchestrates these layers. `configs/` contains fixed controls;
`patches/` contains isolated upstream changes. Author source is a Git submodule.

Build, tests and experiments run on `wangziheng@eex005`. Local work is editing,
source review, and Git. The remote root is `/home/wangziheng/wafer_simulator`.

```bash
# On eex005, in the source checkout:
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
runs and their automatic event comparisons remain intact. See
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

Current deliverables are the source table above, the
[target-resource mapping](docs/TARGET_RESOURCE_MAPPING.md) and the
[M0/M1 protocol](docs/MODEL_BOUNDARY_PROTOCOL.md). No new experiment is launched
by this documentation stage; static-cost modeling remains a next research question.
