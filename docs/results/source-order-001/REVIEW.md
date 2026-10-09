# Source ordering and local merge: saved-data mechanism test

**Result:** native source ordering explains the common-source component
counterexample, but source ordering alone is not a supported primary explanation
for the registered application gap errors. Local input structure is visible both
in the three-flow component and in larger B-layout critical responses. It is the
next discriminating service question, not an already validated replacement rule.

This study adds a component-only ordered-source probe and an authenticated
reader. S, D0, D1, their machine/policy inputs and accepted results are unchanged.
No new application backend, native execution or application execution is added.

## Scope and identity

- Analysis and four semantic tests ran on `ee4e072` as `hn072`, from
  `34f10cee725317a1efc7b1b85fb8993d4fc3b890`.
- Readback covers 16 saved component records: S and D1, two repetitions, four
  conditions. Four new Python probes use repetition zero's D1 inputs only.
- Application diagnosis reads repetition zero for all nine S and nine D1 cells,
  plus the nine saved S critical chains. It is post-prediction diagnosis of
  separate closed loops, not a controlled replay of identical application demand.
- Sixty selected artifact hashes match the accepted component/application
  manifests. This is selected readback, not a rerun of all prior audits or tests.
- [CHECKED.json](CHECKED.json), [TESTS.json](TESTS.json),
  [RESULTS.json](RESULTS.json) and [CRITICAL_WINDOWS.json](CRITICAL_WINDOWS.json)
  retain numerical evidence. Full queue/pair details remain on the server.

The accepted manifest identities are:

```text
components:   44ca1ce850c3e47e536bed18929d76f0dd0feedd0f90bec800f2823c637ccc93
applications: 72ee96e40b592e671309e42f3efc6375664e6005ab2eb8138e05381e2f445cfb
```

They are checked against the published
[D1 acceptance](../shared-spatial-service-001/VERIFIED.json). The original S
binary remains `d37fc5551d90adb03f2595f9e23ef0199b39be3a572f315ef154bad172d93beb`;
this analysis launches no binary. New tests record Python executable identity.

## Common source: selection waits for injection queue drainage

The pinned [TrafficManager::_Inject()](../../../third_party/nw-design-for-wsi/rapidchiplet/booksim2/src/trafficmanager.cpp)
checks `_partial_packets[input][c].empty()` before selecting a new message.
`ready_messages` orders `(ready cycle, message ID)`. Selection constructs all
single-flit packets of that message in the source's pending injection queue.
Under the current trace contract, a later message cannot preempt that queue.
Drainage, rather than complete destination reception, permits the next selection.

For `two-source-stagger-0`, both 65,536-byte messages are ready at cycle zero on
endpoint 0:

| Native boundary | Message 0 | Message 1 |
|---|---:|---:|
| Message generated / selected | 0 | 1,988 |
| First injection | 0 | 1,989 |
| Last injection | 1,987 | 4,035 |
| First ejection | 33 | 2,102 |
| Last ejection | 2,079 | 4,148 |
| Completion boundary | 2,080 | 4,149 |

At message 1's selection, 46 message-0 flits have not yet completed reception.
Thus a gate at message-0 destination completion would implement a different
policy. Across the selected components and all 2,139 saved S application
messages, generated clocks agree with
`max(ready, previous same-source last injection + 1)`; no mismatch is observed.
This checks the recorded generation boundary, not every injection/credit event.

## Minimal ordered-source probe: correct finishes can conceal wrong boundaries

The [probe](../../../src/wafer_sim/analysis/source_order.py) retains D1's own
routes, resource capacities, max-min calculation and propagation constants.
Only one message per source may serialize at a time; waiting heads are ordered
by `(ready, ID)`. The source is released at **fluid serialization end**. The
previous message can remain in propagation. No native route, clock, effective
bandwidth adjustment or fitted 60-cycle correction is a prediction input.

| Common-source prediction | Message 0 finish | Message 1 finish | Message 1 source-service begin |
|---|---:|---:|---:|
| S | 2,080 | 4,149 | Generated 1,988; first injection 1,989 |
| D1 | 4,128 | 4,149 | Both participate from ready 0 |
| Ordered-source probe | 2,080 | 4,149 | 2,048 |

The completion errors fall from `[2048, 0]` to `[0, 0]`. This strongly supports
source order as an explanation of this counterexample. However, the probe's
second head starts 60 cycles after native selection, or 59 after first injection.
It has **not** recovered the native source-release boundary. D1's effective
serialization duration and native injection-queue drainage are different
quantities; equal final completions do not make them interchangeable.

Four remote tests cover serial heads with outstanding propagation, distinct
sources retaining D1 sharing, future source eligibility, and the native
injection-drain gate. They validate the probe's stated rules, not a physical NIC
or a full causal service model.

## Three-flow merge: source ordering is insufficient

All three messages in `three-shared` have distinct source endpoints. Consequently
the ordered-source probe leaves D1 predictions unchanged. Native and D1 routes
agree for every flit in these selected cases, so a path mismatch does not explain
their component differences.

| Ready stagger between messages | S completion cycles, messages 0 / 1 / 2 | D1 and probe completion cycles | Probe signed errors |
|---|---|---|---|
| 0 | 6,176 / 6,175 / 4,148 | 6,218 / 6,218 / 6,218 | +42 / +43 / +2,070 |
| 509 | 5,730 / 6,239 / 5,186 | 4,946 / 5,964 / 6,219 | −784 / −275 / +1,033 |
| 3,000 | 2,122 / 5,122 / 8,122 | 2,122 / 5,122 / 8,122 | 0 / 0 / 0 |

At directed output 24→36, messages 0 and 1 enter from router 12; message 2
enters from router 25. The sink-arrival window is the intersection of the three
messages' observed output-arrival spans, including the final cycle.

| Stagger | First arrival at shared router, 0 / 1 / 2 | Output sink-arrival window | Output flits, 0 / 1 / 2 | Input-12 / input-25 counts |
|---|---|---|---|---|
| 0 | 50 / 28 / 7 | [94, 4,101) | 501 / 501 / 1,002 | 1,002 / 1,002 |
| 509 | 49 / 537 / 1,025 | [1,046, 5,139) | 511 / 512 / 1,024 | 1,023 / 1,024 |
| 3,000 | 49 / 3,028 / 6,007 | No common interval | No overlap count | No overlap count |

This distinguishes source eligibility, local arrival and upstream input
identity. Observed approximately equal aggregate input counts are consistent
with branch-level sharing rather than global equal-flow sharing. They are not
an independent proof of a fixed input-fair arbitration law: these records lack
grant decisions, credit-return clocks and VC eligibility. The windows also do
not certify simultaneous queue occupancy throughout the entire interval.

## Application relevance: no queued source heads on the S critical chains

`source wait` below is **generated − ready**, not first-injection delay or
downstream backpressure. A D1 same-source pair overlaps the two flows' fluid
service intervals; “critical” means at least one token is on the saved S chain.

| Size / layout | S source-delayed messages | S critical network messages | Critical messages with source wait | D1 same-source active pairs | Pairs touching S critical chain |
|---|---:|---:|---:|---:|---:|
| 4 / Local | 0 | 9 | 0 | 2 | 0 |
| 4 / A | 1 | 7 | 0 | 4 | 1 |
| 4 / B | 0 | 7 | 0 | 2 | 0 |
| 6 / Local | 0 | 9 | 0 | 2 | 0 |
| 6 / A | 1 | 7 | 0 | 4 | 1 |
| 6 / B | 0 | 7 | 0 | 2 | 0 |
| 7 / Local | 0 | 9 | 0 | 2 | 0 |
| 7 / A | 0 | 7 | 0 | 1 | 0 |
| 7 / B | 0 | 7 | 0 | 2 | 0 |

All 69 critical messages have zero source-generation wait. The only two source
waits in the nine S executions are 35 cycles each, off the critical chains of
4 A and 6 A. Neither 6 B nor 7 B has a D1 same-source overlap touching the S
critical chain. These observations weaken source FIFO as the primary explanation
of current application gap error. They do not rule out indirect effects on later
demand, changes of critical chain, or source injection blocked by the network.
They also do not prove that a FIFO application variant would have no effect.

Local merging does appear in the larger B critical responses:

| Case / token | Selected common output | Target flits | Peer flits | Incoming resource groups in target's sink-arrival window |
|---|---|---:|---|---|
| 6 B `first17/phase/4` | 46→34 | 1,024 | `first11`: 1,013; `first5`: 1,002 | Router 58: target + first11 = 2,037; router 47: first5 = 1,002 |
| 7 B `first21/phase/4` | 56→42 | 1,024 | `first14`: 1,013; `first7`: 1,002 | Router 70: target + first14 = 2,037; router 57: first7 = 1,002 |

Peer names abbreviate the same `/phase/4` suffix. These post-prediction counts
show a two-plus-one input structure on actual critical responses. Their windows
differ from the component's common intersection; the aggregate ratio is not a
direct per-input rate comparison. [CRITICAL_WINDOWS.json](CRITICAL_WINDOWS.json)
contains all 13 selected critical-message windows with observed peer traffic,
including second reads and C2C/I/O traffic. No native overlap or route becomes a
prediction input in the probe.

## Research decision and stopping point

Keep D1 as the accepted fast approximate baseline, without fitting fairness,
bandwidth or mappings. The source-only probe fails the overlapping three-input
component and misses a source boundary even where its final times are exact.
It therefore does not justify a new application backend or application matrix.

The next narrow method test should preserve **local arrival and incoming input
identity**, and compare source-release and local-service boundaries as well as
destination finish. Source serialization cannot simply reuse D1's total fluid
service end. Establish any service/arbitration rule from the pinned native
contract and controlled component evidence; do not infer it from the 501:501:1002
count alone. This study does not establish that credit modeling is necessary,
does not implement event compression, and makes no algorithm-novelty claim.

S evidence-path optimization remains independent engineering work. Its local
recording-mode draft is paused and preserved, outside `main`; it has no build,
test, equivalence or acceleration claim. A single-copy shared-data workload is
deferred until a candidate passes these component boundaries. No current GEMM
point is relabeled as an independent holdout.

## Reproduction and preserved artifacts

On the experiment host, with fresh absolute output paths:

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.source_order \
  /Projects/haoning/wafer_simulator/runs/d1-components-001 \
  /Projects/haoning/wafer_simulator/runs/d1-applications-001 \
  docs/results/shared-spatial-service-001/VERIFIED.json \
  /Projects/haoning/wafer_simulator/runs/source-order-analysis-NEW
PYTHONPATH=src ../.venv/bin/python -m unittest discover -s tests -p test_source_order.py -v
../.venv/bin/python docs/results/source-order-001/derive.py \
  /Projects/haoning/wafer_simulator/runs/source-order-analysis-NEW \
  /Projects/haoning/wafer_simulator/runs/source-order-report-NEW
```

Original output roots are `runs/source-order-analysis-001`,
`runs/source-order-tests-001` and `runs/source-order-report-001`, under
`/Projects/haoning/wafer_simulator`. `DETAILS.json` remains server-side with SHA256
`2a72a381962dc48b7a5c99c87e7855220fc3eaa8cc0b99c1d12dbbdcd00d9df4`.
[DERIVED.json](DERIVED.json) authenticates the compact extraction and its script;
[PUBLISHED_COPIES.json](PUBLISHED_COPIES.json) records seven matching byte copies.
No accepted raw event file or receipt was overwritten.
