# Registered full-capture comparison

No smoke runs, input prefixes, dependency deletion, or generated-workload
fallback. The generated `fixed-state-002` campaign was stopped and marked
`formal_evidence=false` on eex005. Semantic unit tests are software checks.

## Input and provenance

- Author network repository: `spcl/nw-design-for-wsi`,
  `9470042fb2d8b5368556e46cc75ac818dbf31522`.
- ATLAHS source: `spcl/atlahs`,
  `fb51a99f908e550318056ebb3e084f3d2fff55bd`.
- Official data URL:
  `http://storage2.spcl.ethz.ch/traces/ai/llama/Llama7B_N4_GPU16_TP1_PP1_DP16_BS32/llama.goal`.
- Server-only input:
  `/home/wangziheng/wafer_simulator/downloads/atlahs/llama16/llama.goal`.
- Bytes: 383,857,060. SHA-256:
  `5f360f2936fffa0813772b967ca1c78763c098a19421633564ff3581b06372ca`.

All 13,881,203 lines were read. The file contains 4,432,750 `calc` operations,
445,740 sends, 445,740 receives, and 8,556,960 completion dependencies. All
message keys match uniquely with equal sizes; adding arrival dependencies
leaves an acyclic graph. No input edge was removed. The full input contains
303,228,749,760 payload bytes and requires 151,889,580 2000-byte flits.

Four GOAL ranks are hosts, each with NIC IDs 0..3 and CPU IDs 0..40. Preserve
all 164 CPU lanes. Map the 16 sorted `(host,NIC)` identities to compute
reticles by the same row-major rule in both placements. CPU lanes retain
their identities and durations; they are not additional physical reticles.

## Fixed controls

Compare `baseline` and `ours_rotated`, 200-mm rectangular LoI. Both have 20
compute endpoints; 16 are active. Use 1-GHz network clock, 2-TB/s links,
2000-byte flits, 1 VC, 32-flit buffers, 4-cycle routers, adaptive selection,
the author's cycle-breaking routing, and seed 1. Keep all original work and
dependencies identical. Report differing router/link costs rather than claim
equal total network area or bandwidth. Execution has a 12-hour wall limit per
arm; a limit is a failed/incomplete run and never an application result.

Every `calc` occupies its declared CPU lane for its unchanged duration. The
CPU policy is FCFS in deterministic dependency-ready callback order. Sending
waits for CPU availability, has zero additional CPU issue cost, then competes
for the finite BookSim injection/network resources. Sending completes after
all message flits arrive. A receive also waits for its local dependencies.
These are declared target replay policies, not calibrated GPU instruction
execution or the ATLAHS eager/rendezvous implementation.

## Model boundary

ATLAHS's `goal_gen/ai/nccl_goal_generator/generator_modules/`
`data_dependency_modules/inter_node_dependency.py` uses `calc` for local gaps,
reduction/copy work, and intra-host GPU transfers. Their durations remain
fixed here. The file exposes inter-host messages to the changed network; it
does not expose all intra-host transfers for migration onto WoW links. A
completed result predicts this full captured schedule under the fixed local
model, not the original WoW paper workload or native wafer training time.

## Required evidence

Both arms must finish every operation and payload flit. Independent readback
checks every original dependency and matched arrival, CPU non-overlap, exact
local work duration, message timestamps, injection capacity, and terminal
completion. It reconstructs the observed critical chain with CPU contention
edges and requires local-work cycles plus message-service cycles to equal
application completion exactly. Compare these with mean network packet
latency, hop count, and injection wait; do not sum overlapping rank waits.

Keep full traces, compiled binaries, raw logs, per-operation events, and
intermediate graphs on eex005. Only small provenance/audit/result summaries
belong in the source checkout. One seed and mapping support this paired case,
not a general placement-ranking conclusion.
