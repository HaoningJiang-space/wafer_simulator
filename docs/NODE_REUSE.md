# Arbitration and credit node reuse — 2026-10-06

The sampled credit allocation is not a missing `Credit` object pool: upstream
already reuses those objects through `Credit::New/Free`. Its `set<int>` nodes
are freed by `Reset` and allocated again by each insert. `SparseAllocator`
similarly clears request maps and occupied-port sets every active round.

`patches/booksim-node-reuse.patch` uses C++17 node handles to extract and retain
these nodes. Later inserts update their key/value and return them to the same
standard ordered-container types. The request-node and occupied-port caches are
owned by each sparse allocator. The credit-node cache accompanies the existing
single-threaded global credit-object pool; `FreeAll` releases cached nodes.
This does not make the native simulator thread safe.

Request priorities, sorted iteration, duplicate-set behavior, arbiter update
order, credit emission/arrival cycles, VC count and buffer capacities retain
their previous definitions. Pools grow with the maximum node demand and retain
storage until teardown. Extracting/reinserting nodes has its own cost, so a
net wall-time benefit is a hypothesis requiring complete-run measurement.

## Checked artifacts on eex005

- Isolated build: `build/booksim-node-reuse`.
- Binary SHA-256:
  `30446d7e41cacf8d650e386f46dfd87028106df5554fa74062857a967231b192`.
- Patch SHA-256:
  `8a7e745b03197d4f5a04346f5b7fce068e242bf6b26de16e424c8284e95977ad`.
- Fifteen native/workload semantic regressions pass:
  `logs/tests-node-reuse-001.log`.
- Twelve regression input/report pairs match the runtime-opt control exactly,
  with identical network metrics: `logs/node-reuse-semantic-equivalence.json`.
- `runs/node-reuse-contract-002/` contains checked-container tests of ownership,
  map updates, set ordering/duplicates and multi-VC credit reuse. It also
  contains 500 rounds each of input-first, output-first and iSLIP arbitration
  against both actual builds, including conflicts, ties and removed requests.
  All 1,500 rounds have byte-identical grant outputs, SHA-256
  `94be0c92505e932d879eb5dd0ae0ca07a81366cd8fcf029c24d1bcec4b0e7315`.

The initial sanitizer link attempt in `node-reuse-contract-001` failed because
the system GCC installation lacks the ASan/UBSan runtime libraries. The completed
ownership tests use `_GLIBCXX_DEBUG` and `_GLIBCXX_ASSERTIONS`; they are not an
ASan/UBSan result. These correctness fixtures are not performance experiments.

## Full-capture acceptance

`run_node_reuse_full_remote.sh` registers `llama16-full-005-node-reuse` against
`llama16-full-004-runtime-opt`, retaining both placements and the complete real
capture. The post-run watcher requires exact full event/input hashes, completion
and network results after each independent audit. It writes
`runs/llama16-node-reuse-equivalence.json` only after passing. The existing
reference runs and binaries remain active and unchanged.

Run 005 passed the complete-input equality gate and launched both native arms
(observed PIDs 2186310 and 2186311) from clean source commit `e3899f8`.
End-to-end performance and full event equivalence are still pending.

The GPU/HeteroSTA investigation is a separate design assessment in
[HETEROSTA_TRANSFER.md](HETEROSTA_TRANSFER.md); this patch is a CPU implementation
optimization and adds no GPU execution or new simulation approximation.
