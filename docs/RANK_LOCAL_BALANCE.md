# Rank-local publication and memory resource balance

The logical AllReduce declares SUM, participants, operands and bytes. Target
`ExecutionPolicy` selects the existing `direct_exchange_rank_order_sum`
algorithm, separately from `rank_local` or diagnostic `global_retirement`
publication. This milestone used direct-root only; the subsequent
[fixed-tree study](TREE_SPATIAL_PROTOCOL.md) adds a second algorithm separately.

Each local immutable output becomes visible only after its declared destination
write requirements complete. Data dependencies use these per-object events;
explicit control dependencies still wait for operation retirement. All rank
inputs and atomic capacity reservations are required at admission, unchanged.
The application completes only after every operation retires, not after the
first output. Collective staging, inputs and producer-owned output reservations
remain pinned until retirement; an output must also outlive every consumer.
This conservative lifetime permits internal broadcast reads even when a local
consumer has already finished. It is not rank-local collective entry or streaming.

Independent readback checks final writes, per-object availability, control
dependencies, full retirement, capacity, work conservation and FCFS service.
Critical chains follow data-ready events and explicit control-retirement events
separately. Native BookSim and its reference remain unchanged.

## Registered experiments

1. Re-run the existing eight-head TP4/TP8 × row-major/nearest-root × two author
   placements, first with historical global publication and then rank-local.
   Check the former against accepted times and full service/phase records.
   Only the publication policy changes in the same-revision comparison.
2. Use `configs/transformer_resource_balance.json`: same eight-head TP8 block,
   row-major, SUM algorithm, compute rates, capacities, network seed and
   geometry; common memory port rates 32, 64, 128, 256, 512, 1024 B/cycle.
   The 32 point must reproduce the corresponding rank-local study arm.
   Compare work/mapping/network identities throughout, compute parameters with
   the memory-rate field removed, and both placements at each rate.
3. Report completion time, all output-ready/retired clocks, successor starts,
   observed critical-service chain, tail ranks and native communication waits.
   Use bandwidth sensitivity and chain composition to identify memory-sensitive,
   compute-limited or network-sensitive ranges. A crossover or growing topology
   gap is an observation to test, not an acceptance requirement to manufacture.

No new workload, mapping sweep, native compute calibration, matched physical
cost, thermal or PDN claims. Historical evidence remains immutable.

## Reproduce on eex005

From a clean committed `source` checkout, with `PYTHONPATH=src`, use runtime
`.venv/bin/python` (all output directories must be fresh absolute paths):

```sh
python scripts/test_wow_target_remote.py TESTS
python scripts/run_transformer_wow_remote.py GLOBAL TESTS/SEMANTICS.json --study --global-completion-control
python scripts/run_transformer_wow_remote.py LOCAL TESTS/SEMANTICS.json --study
python scripts/run_transformer_wow_remote.py BALANCE TESTS/SEMANTICS.json --balance
```

Each arm includes live native execution, independent timing/lifetime readback,
standalone native network replay of the observed schedule, and the existing
coarse network control. Only an entirely checked run receives `COMPLETE.json`.

Read back the accepted runs without further simulation:

```sh
python scripts/analyze_resource_balance_remote.py HISTORICAL GLOBAL LOCAL BALANCE ANALYSIS
python scripts/plot_resource_balance_remote.py ANALYSIS FIGURES
```

`HISTORICAL` is the accepted `transformer-collective-study-001` directory.
The [accepted report](results/rank-local-balance-001/REVIEW.md) records all concrete
run paths, source revisions, results and evidence boundaries.
