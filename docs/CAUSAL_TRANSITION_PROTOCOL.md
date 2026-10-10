# R1: explicit state and ordinary one-cycle transition

Status: registered implementation, not yet an equivalence receipt.

Preserve legacy `adapters/causal_merge.py` (SHA-256
`24831579b2d0c49d11ab1003daef490754dba5d92e80b68c30da0fdbd1e9cf41`),
its accepted seven-case evidence, and the accepted AST-derived G2.1 prototype.
Do not redirect either reference to the new core. R1 introduces only
`execution/causal/state.py`, `transition.py` and their comparison/remote entry
points. Macro migration, sinks, compact format redesign and G2.2/G2.3 are deferred.

## State and order contract

`initialize(contract, messages, cycle_limit)` creates mutable `CausalState`
containing explicit sources, routers, ordered channel events, packet metadata,
finite demand and counters/full evidence. `step_one_cycle(state)` consumes the
next clock boundary and advances exactly one cycle. Its order is: ordered
channel arrivals/credits/sends/sink consumption; source generation/injection;
router Evaluate decisions using pre-update ownership; VC/switch commit and
scheduling; drain test. No later router consumes a newly scheduled positive-
delay channel event during the same cycle. No VC request is newly eligible
because of a switch release earlier in that cycle's Update.

EventQueue retains `(cycle, global insertion sequence, payload)`. Same-clock
events remain in insertion order, not sorted by kind or flit identity. Message
finish and network drain are distinct; deadlines without drain are incomplete.

`state.snapshot()` is detached and immutable. It includes full issuing IDs,
pending message heap order, exact owner/deadlines/pointers/credit, ordered future
events and sequence IDs, live metadata, finite remaining work, generations,
counts/stalls/peaks and cycle budget. Historical retired evidence is excluded
from the ordinary snapshot, not execution: it is compared in the complete
result. `snapshot(include_history=True)` additionally copies every generated
packet and full event history. Snapshot generation is optional and never a
service decision input. It imports no analysis or experiment code.
Uninjected metadata is included as lossless contiguous identity segments;
every queued record is checked, so a different message/source/epoch creates
a distinct segment and is detected before injection. This coalesces snapshot
copies only; the ordinary source remains an explicit deque.

## Independent equivalence gate

Run all seven unchanged G1 cases with no macro. Save ordinary candidate output
before any reference observation. The offline verifier then observes unchanged
G1 cycle boundaries and independently constructs a comparable projection of
its locals. Reference schedule call order establishes expected sequence IDs.
An independent shadow engine generates its own events; no observed reference
arrival, credit or grant is submitted to it.

Compare every pre-cycle state plus final drained state, fail at the first
different cycle/field, and retain a streamed boundary digest ledger. Compare
all final flit, service, allocation, arrival, credit, stall, peak, finish and
drain fields, and the previously accepted G1 prediction bytes. Wrong credit,
owner, deadline or future event must fail at its first changed boundary. Pure
analysis readback must restore saved predictions, authenticate all artifacts,
regenerate only the independent reference, and check ledger/summary consistency.
All new tests and experiments run on hn072. No new Native/applications or speed
claim are part of this behavior-preserving gate.

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_causal_transition_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-transition-tests-NEW
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.causal_transition \
  /Projects/haoning/wafer_simulator/runs/causal-transition-NEW \
  --tests /Projects/haoning/wafer_simulator/runs/causal-transition-tests-NEW/TESTS.json \
  --g1-evidence /Projects/haoning/wafer_simulator/runs/causal-closure-002
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.causal_transition \
  /Projects/haoning/wafer_simulator/runs/causal-transition-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-transition-readback-NEW
```

Full evidence is intentionally retained in R1. This is not R2 sink separation
or R3 macro migration, and does not remove AST rewriting from the frozen G2.1
reference. New ordinary development no longer depends on that mechanism.
