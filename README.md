# WoW application-completion baseline

Pinned author geometry and BookSim, strict same-workload execution, independent
completion checks, and placement comparison. Read [the source audit](docs/UPSTREAM_AUDIT.md)
for what is reused, repaired, and not claimed.

Code layers: `workloads` → `adapters` → native BookSim → `analysis`;
`experiments` orchestrates these layers. `configs/` contains fixed controls;
`patches/` contains isolated upstream changes. Author source is a Git submodule.

Build, tests and experiments run on `wangziheng@eex005`. Local work is editing,
source review, and Git. The remote root is `/home/wangziheng/wafer_simulator`.

```bash
# On eex005, in the source checkout:
bash scripts/build_remote.sh
test_output=/home/wangziheng/wafer_simulator/runs/semantics-$(date -u +%Y%m%dT%H%M%S)
WAFER_TEST_OUTPUT="$test_output" PYTHONPATH=src \
  /home/wangziheng/wafer_simulator/.venv/bin/python -m unittest discover -s tests -p test_semantics.py -v
WAFER_NATIVE_REGRESSION_INPUT="$test_output" PYTHONPATH=src \
  /home/wangziheng/wafer_simulator/.venv/bin/python -m unittest discover -s tests -p test_goal_completion.py -v
PYTHONPATH=src /home/wangziheng/wafer_simulator/.venv/bin/python -m wafer_sim.cli \
  --config configs/llama16_fixed_state.json \
  --upstream /home/wangziheng/wafer_simulator/upstream/nw-design-for-wsi \
  --binary /home/wangziheng/wafer_simulator/build/booksim-fixed/rapidchiplet/booksim2/src/booksim \
  --output /home/wangziheng/wafer_simulator/runs/llama16-full-002
```

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

Performance work is tracked separately from architectural results:
[topology-copy diagnosis](docs/ROUTING_COPY_DIAGNOSIS.md) and
[dense trace state / empty channel evaluation](docs/RUNTIME_OPTIMIZATION.md).
The optimized builds use separate worktrees and the same full capture. Their
complete event histories must match their controls before accepting a speedup.
The subsequent [arbitration/credit node reuse](docs/NODE_REUSE.md) candidate
follows the same acceptance rule. [HeteroSTA method transfer](docs/HETEROSTA_TRANSFER.md)
records the source-based assessment of GPU execution opportunities and limits.
