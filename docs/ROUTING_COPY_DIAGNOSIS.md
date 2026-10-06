# Full-run performance diagnosis — 2026-10-06

> Historical implementation record. Old patch, config and script paths below
> refer to Git commit `f530c82`. The working tree now maintains one combined
> implementation; see [current entry points](IMPLEMENTATION.md).

The complete capture has 151,889,580 flits, and the reused BookSim network
executes each active cycle on one CPU thread. This is a substantial baseline
cost, but it does not explain away avoidable implementation work.

The upstream virtual `routing_function::route` accepts the entire nested
`vector<map<int,map<int,tuple<int,int,int>>>>` topology **by value**.
`modular_routing_anynet` passes the shared topology to it for flit routing.
Each call therefore deep-copies the topology and subsequently destroys it.
Helper functions also pass the same structure by value during initialization.

Live inspection of full run 002 found:

- Both native processes have one thread, about one fully occupied CPU core,
  approximately 9.2 GiB RSS each, and zero process swap usage.
- Cumulative physical reads/writes were negligible after trace loading;
  the server had approximately 180 GiB of available memory.
- Eight debugger stack samples, alternating between the two real runs,
  caught four topology-copy stacks, two topology-destruction stacks, and two
  ordinary network-step stacks. These are hotspot evidence, not a statistically
  precise attribution of CPU time.
- Sampled network step counts were much smaller than global application cycles
  (e.g. baseline 3,325,790 steps vs 39,326,590 application cycles), confirming
  that idle-time skipping is active. The current run is not stepping through
  every nanosecond of local computation.

Raw samples and scalar observations remain on eex005 in
`/home/wangziheng/wafer_simulator/profiles/llama16-full-002/`.
Debugger attaches briefly pause execution (about 18 seconds total across the
eight samples, plus the initial sample). Full-run wall ratios involving this
reference must disclose that overhead and concurrent host workloads.

## Correction and acceptance

`patches/booksim-topology-ref.patch` changes topology parameters to const
references. Missing endpoint adjacency returns an immutable empty map, matching
the old temporary-map behavior for interconnect routers. Router/link parameters,
route-selection algorithms, buffer arbitration, CPU-lane policy, event order,
workload sizes and completion rules are unchanged by design.

The candidate is built in a separate worktree:
`/home/wangziheng/wafer_simulator/build/booksim-topology-ref`.
Binary SHA-256:
`a7542739f11cb117c12bfe05304885741da554542a5e44b30a16382486c1bbc7`.
Routing patch SHA-256:
`26f8aa69a76b6af6d7607661e99277037083e6bff44382452f1cc0e2294c72c9`.

The 13 semantic regressions pass for the candidate. Saved native completion
reports are compared directly with the unoptimized implementation before
launching the complete candidate capture. These are correctness checks, not
performance experiments on reduced inputs.

Keep complete run 002 executing as the reference. Complete run
`llama16-full-003-topology-ref` uses the same full capture and physical controls.
After both finish and pass their independent audits, `verify_full_replay.py`
requires exact full input and per-operation event hashes, completion times,
critical-chain contributions, network metrics and resource configurations.
The watcher writes `runs/llama16-topology-ref-equivalence.json` only on success.
Until then, full-capture equivalence and end-to-end speedup remain pending.
