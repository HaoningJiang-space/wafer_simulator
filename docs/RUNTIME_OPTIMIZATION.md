# Further runtime optimization — 2026-10-06

## Evidence and choice

Twelve debugger samples from the two **complete** ATLAHS replay processes in
`llama16-full-003-topology-ref` found no whole-topology copies. Nine samples
were in network input/evaluation/output traversal, one in a per-flit timestamp
map lookup, one in allocator request destruction, and one in credit-set
allocation. This small sample identifies places to inspect; it does not measure
their CPU-time fractions. The raw stacks and sampling durations remain on eex005:
`/home/wangziheng/wafer_simulator/profiles/llama16-full-003-topology-ref/`.
Attachments paused the two processes for approximately 12 seconds in total.

The code inspection supports two exact implementation changes:

1. `AnyNet::Evaluate` visits routers in their original construction order.
   At this pinned revision, all other timed modules are `FlitChannel` and
   `CreditChannel`; their `Evaluate` methods are empty. Channel `ReadInputs`
   and `WriteOutputs`, router internal speedup, arbitration and credit timing
   retain their original behavior.
2. Complete-trace instruction state uses vectors indexed by the already-dense
   lowered IDs instead of per-field red-black trees. Native parsing now checks
   the contiguous ID contract before indexing. Negative/missing dependencies
   and duplicate IDs still fail explicitly. An unoccurred timestamp is `-1`;
   cycle zero remains a valid recorded event. Initial CPU readiness follows
   file order, successor callbacks follow stored reverse-edge order, and event
   reports remain in ascending ID order.

This changes storage representation and removes empty calls. It neither merges
flits nor changes simulation time steps. Sparse native IDs are outside this
candidate's accepted interface; project workload lowering already requires
dense IDs. The reference builds are retained separately.

Other sampled costs, especially allocator and credit-set allocation, are left
for a later change: their ordering and buffer semantics warrant a separate
implementation and acceptance check. Do not change VC count, buffering,
arbitration or message sizes to make this implementation comparison faster.

## Layers and acceptance

- `patches/booksim-runtime-opt.patch`: additive native implementation patch,
  applied after completion and const-reference routing corrections.
- `scripts/build_runtime_opt_remote.sh`: isolated remote build and patch
  integrity manifest; does not overwrite any running reference executable.
- `tests/test_semantics.py`: completion, credit/idle, CPU ordering and malformed
  index regressions. These are correctness tests, not workload experiments.
- `configs/llama16_runtime_opt.json` and
  `scripts/run_runtime_opt_full_remote.sh`: unchanged complete capture, both
  placements and all fixed controls, with the new implementation recorded.
- `scripts/verify_full_replay.py`: independent acceptance after both complete
  captures finish and pass the application audit. Requires identical full
  input/event hashes, completion times, critical-chain contributions, network
  metrics and physical resources.

The new full run is `llama16-full-004-runtime-opt`; its direct reference is
`llama16-full-003-topology-ref`. The latter is already paired with unoptimized
`llama16-full-002`. No prefix or synthetic workload is used for performance
evidence. Wall-time ratios include concurrent host work and debugger pauses
and must be identified as observations rather than isolated benchmarks.

The isolated build succeeded on eex005. Binary SHA-256:
`0ab4444523c416b7554d654b89f4102cbf211a81f86b13655297646c00f6db15`.
Runtime patch SHA-256:
`a2aa0296a2df5568fa0a5faa78f79a57a1dc34e0763a10cf49566d17301177bf`.

All 15 semantic regressions pass (`logs/tests-runtime-opt-001.log`). The two new
ordering/parser regression methods also pass on the const-reference control
(`logs/tests-topology-ref-ordering-001.log`). Twelve saved reports, including
the intentionally incomplete case, have identical input and report SHA-256
hashes and identical network metrics across implementations. Evidence:
`logs/runtime-opt-semantic-equivalence.json`.

Full replay equivalence and end-to-end speedup remain pending until the watcher
writes `runs/llama16-runtime-opt-equivalence.json`.
