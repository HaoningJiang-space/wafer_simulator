# WoW application-completion simulator

Pinned author geometry and BookSim, complete same-workload execution, independent
completion checks, and placement comparison. Read [the source audit](docs/UPSTREAM_AUDIT.md)
for what is reused, repaired, and not claimed.

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
`f530c82`; they are not maintained implementation choices. The ongoing complete
runs and their automatic event comparisons remain intact. See
[run status](docs/LLAMA16_RUN_STATUS.md), [CSR semantics](docs/CSR_FRONTIER.md),
and [HeteroSTA transfer](docs/HETEROSTA_TRANSFER.md).
