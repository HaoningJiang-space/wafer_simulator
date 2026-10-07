# Fixed Transformer block on two WoW placements

The registered experiment is `configs/transformer_wow_pair.json`. It runs the
entire already validated forward block from `configs/transformer_block.json`:
30 operators, 557,056 MACs, two logical workers and two root-gather/SUM/broadcast
collectives. No source capture or fixed source duration is substituted.

## Fixed and changed controls

Only author placement changes: `baseline` versus `ours_rotated`, both WoW LoI,
200 mm, rectangular utilization. The pinned author export supplies routers,
links, endpoints, coordinates, link propagation, router pipeline and VC/buffer
configuration. The 20 available compute endpoints are retained; two are active.
Logical workers map to the first two endpoints sorted by `(layer,y,x)`. This is
one fixed rule, not a search for favorable endpoint pairs. Actual endpoint IDs
and coordinates are reported in both arms.

The compute and memory parameters remain those of the accepted analytical
block: 256 KiB per region, 32 bytes/cycle shared read/write port, and the same
explicit arithmetic rates. Each target compute server has its region's memory;
all weights and activations retain the same logical worker ownership. These
parameters are common assumptions, not calibrated native WoW compute/SRAM.

Network clock is 1 GHz. The author links carry 16,000 bits/cycle: 2,000
bytes/cycle, one native flit/cycle. Every message uses `ceil(bytes/2000)`
single-flit packets. The 4,096-byte payload therefore uses three flits; the
extra 1,904 bytes consume network capacity but are not extra memory payload.
Heterogeneous link bandwidth or a mismatching flit width is rejected. Author
endpoint channels, router pipelines, adaptive cycle-breaking routing, one VC
and 32-flit buffers are preserved. Original network costs are not matched.

## Live execution interface

`execution/timing.py` retains compute/memory arbitration and finite storage.
When a source read completes, it submits the transfer to one persistent native
BookSim process. The process advances until the next external event boundary
or the first all-flit message completion. It preserves queues, credits, VC
allocation and router state between calls. The adapter does not restart the
network for each message and does not precompute future application traffic.

Boundary t precedes BookSim's interval `[t,t+1)`. A message may be submitted at
t before that interval is stepped. If its last flit ejects in native cycle c,
the completion callback is published at boundary c+1; destination memory writing
then uses its own service. This explicit conversion is checked against raw
native arrival cycles and is not a fitted latency term. Native arrivals precede
local callbacks at equal external boundaries. At application completion, remaining
credits drain separately; that drain does not extend application time.

`adapters/native/online_booksim.cpp` subclasses the accepted TrafficManager,
appends newly ready dependency-free messages, and calls its existing `_Step`.
All flit creation, network service and all-flit completion are reused. Passive
non-destructive channel observations record actual per-flit router paths and
link-arrival times. The separate adapter build links the accepted compiled
objects. Pinned sources, the selected patch and old standalone binary remain
unchanged; there is no second network implementation or optimization variant.

## Validation before paired execution

Native regressions cover a single flow and padding, simultaneous flows sharing
a directed link with a two-flit credit buffer, idle intervals, incomplete close,
and source read → network completion → destination write → consumer execution.
Missing flits and early completion records fail independent readback.

Each test and each full block arm also submits its **observed** message-ready
schedule to the unchanged standalone BookSim after live execution. Generation,
first/last injection, first ejection and final-flit arrival must agree exactly.
This is an interface oracle, not the source of the application's injection
schedule. Shared-network state and application feedback come from live execution.

The original 113-cycle analytical example must retain its entire event record;
Transformer numerical/work/lifetime and existing spatial semantic tests remain
required. The formal runner requires a clean commit and passing native tests at
that commit. Incomplete work never gets the final paired completion marker.

## Outputs and interpretation

Each arm reports application time, collective ready/admission/finish times,
native message waits and all-flit arrival times, actual routes, link activity,
memory residency, resource counts and an observed critical service chain.
Memory/compute service predecessors are included in that chain so waits are not
double-counted. Native message service remains an observed interval; it is not
expanded into a unique router-arbitration causal decomposition.

The existing coarse whole-message model also runs on each identical exported
graph. It adds a source-router pipeline per link and a final-router pipeline in
ejection, avoiding an omitted endpoint/router cost. Its shortest-hop routing,
serialization and queue policy differ from native adaptive flit execution.
This is a separately labeled approximation comparison, not an isolated
contention ablation and not Mstatic from the old full-capture protocol.

This two-worker conservative collective may have no simultaneous messages. If
so, conclusions concern path/service cost propagation through the forward block;
they do not establish a congestion advantage or general topology ranking.
No mapping sweep, new collective algorithm, Llama training, thermal or PDN is
part of this experiment.

## Reproduce on eex005

Start from a clean committed source checkout under the existing remote root.
Restore the bundled upstream sources and build the selected native backend
with the existing setup scripts if they are not present. Then:

```bash
bash scripts/build_online_remote.sh
export PYTHONPATH="$PWD/src"
ROOT=/home/wangziheng/wafer_simulator
"$ROOT/.venv/bin/python" scripts/test_wow_target_remote.py "$ROOT/runs/wow-semantics-NEW"
"$ROOT/.venv/bin/python" scripts/run_transformer_wow_remote.py \
  "$ROOT/runs/transformer-wow-NEW" "$ROOT/runs/wow-semantics-NEW/SEMANTICS.json"
"$ROOT/.venv/bin/python" scripts/analyze_transformer_wow_remote.py \
  "$ROOT/runs/transformer-wow-NEW" "$ROOT/runs/transformer-wow-attribution-NEW"
```

All output directories must be fresh. The last command is read-only analysis:
it verifies the complete run's artifact hashes, joins actual per-flit routes
to exported link costs, and pairs operation times. It launches no simulator.
The [first accepted result](results/transformer-wow-001/REVIEW.md) retains
the original execution commit separately from subsequent reporting code.
