# Upstream reuse and completion contract

Inspected author repository: https://github.com/spcl/nw-design-for-wsi
Pin: `9470042fb2d8b5368556e46cc75ac818dbf31522` (initial commit).

Reuse directly, through adapters:
- `run_experiment.construct_system_for_single_design`: actual WoW placements.
- `analyze_topology.add_global_reticle_ids/add_neighbor_information`: connectivity.
- `export_to_rapidchiplet`: router representation and physical link latencies.
- `rapidchiplet.booksim_wrapper`: topology/config serialization.
- Modified author BookSim: routing, finite buffers, switch/link arbitration.

Omelet was inspected as an alternative. Its gem5/Garnet packaging-aware framework
is useful for later technology work; replacing the author's BookSim now would
change both topology adapter and simulator and weaken baseline attribution.

The WoW config explicitly says the Llama traces are too large for GitHub. The
`traces_goal/` directory contains only a placeholder. ATLAHS lists a separate
public trace collection at https://storage2.spcl.ethz.ch/traces/ (16/64/128-GPU
Llama 7B captures). It is not the missing WoW trace set; download attempts on
2026-10-06 failed. No measured Llama trace is included in the present campaign.

## Source findings requiring semantic regression tests

1. `_HandlePacketWithZeroDependencies` increments instructions simulated on
   readiness, before network delivery or timed compute completion.
2. Compute-only terminal nodes propagate duration only to successors, so a
   terminal duration is not itself represented by a completion event.
3. `_SingleSim` tests the readiness-based count as a termination condition.
   It can leave ready messages unissued, and the final drain does not advance
   the application's `global_current_cycle`.
4. A message completes when the *marked* last flit arrives. Each flit is a
   separately routed packet. With different paths, that is not necessarily the
   last payload flit to arrive.
5. Idle skipping checks data flits but does not require all credits to drain.
6. The GOAL converter truncates labels, ignores unmatched sends, and deletes
   dependencies to break cycles. Do not use that converter for completion claims.

Our patch changes trace completion semantics only. Traffic mode, placement,
physical link latency, router pipelines, routing, and buffers remain upstream.
Compute/join nodes complete at explicit times; messages complete after every
payload flit arrives; incomplete runs fail; all events are exported. Idle
skipping waits for both data and credits and is checked against no skipping.
A separate Python reader checks every dependency, operation duration, message
and flit count, and application terminal time.

## Scope and fairness

The initial workload is a complete generated synchronous data-parallel training
schedule: fixed forward/backward work, ring reduce-scatter/all-gather, optimizer,
and iteration dependencies. It is a conditional schedule experiment, not a
Llama execution capture or a calibrated GPU compute model. Reduction arithmetic
is not independently timed. The conservative ring step waits for outgoing and
incoming completion; no claim about an optimal NCCL algorithm is made.

200-mm rectangular LoI, 20 active ranks, same workload JSON, fixed 1-GHz network,
2-TB/s links (2000-byte flits), 1 VC and 32-flit buffers. Rank mapping is explicit
and fixed by the same policy across arms. Compare four author placements and
two mapping policies, three seeds. Total network resource costs differ and are
reported; this is not a fixed-total-network-area or fixed-total-bandwidth study.
No power, thermal, DVFS, native execution or physical signoff claims.

BookSim includes its BSD-style LICENSE.md. The top-level author artifact has no
repository-wide license file. Retain it as a pinned external dependency and do
not relicense its contents. Our patch retains original notices.
