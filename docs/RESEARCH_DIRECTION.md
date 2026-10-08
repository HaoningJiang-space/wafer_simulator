# Current research: reliable WoW design-gain prediction

Study how little execution state is sufficient to predict **data availability,
resource feasibility and design gains** on a declared spatial wafer machine.
The simulator already executes logical compute/memory/network work; rebuilding
that capability or recovering missing Chakra fields is not a prerequisite.

## Physical question and fixed target

WoW geometry determines which reticles connect, path lengths and shared network
resources. Source/receiver memory and port service determine when data can enter
and leave those paths. Dependencies turn data arrival into application progress.
These couplings matter to the extent that omitting them changes the requested
prediction. FIFO and FCFS mechanisms alone are not wafer-specific novelty.

Distinguish three comparisons:

| Comparison | What changes | Meaning |
|---|---|---|
| Target/policy | Memory quantum, hardware capacity, execution policy | Sensitivity to the declared machine |
| Abstraction | serial/pipeline/bounded within one target | Prediction error relative to the mechanism reference |
| Implementation | Source revision, data structure, logging/measurement | Cost to compute the same result |

Current compute/SRAM and DMA rules are analytical assumptions. Author WoW
network parameters are pinned model inputs, not automatically measured silicon.
Keep geometry, connectivity and finite capacity from the start; detailed physical
closure and thermal are outside this milestone. Omelet informs the evidence
structure (gap, targeted model, design consequence), not the target's physics.

## The completed milestone

The frozen study followed [BOUNDARY_DESIGN_PROTOCOL.md](BOUNDARY_DESIGN_PROTOCOL.md):

- two existing complete s16/s64 TP8 direct-root blocks;
- Baseline and Rotated, fixed row-major rule and saved endpoint coordinates;
- request_atomic and burst_256 target memory policies;
- serial, pipeline and bounded abstractions;
- native BookSim, existing resources/seed/buffer budgets, unchanged execution.

The matrix has 24 configurations. Twelve Rotated configurations add the missing
design column. Baseline remeasurement supplies contemporary cost controls and
must preserve all accepted events. No mapping or bandwidth search.

The [accepted result](results/boundary-design-001/model_selection.md) closes this
milestone: serial gap errors are +8/+44/+20/-12 cycles, within the declared budget;
two indifference classifications nevertheless differ. Reference gaps are 74/82
cycles, so no robust winner is claimed. pipeline agrees in time but violates RX
capacity in both designs. Retain these distinct uses and stop endpoint expansion.
The completed [registered coverage study](GROUP_SHARING_PROTOCOL.md) retained the
`5de7a2f` models and adds two disjoint TP8 groups in one native network. It uses
own-position solos and simultaneous execution to separate positional cost from
network-mediated interference. s64/burst_256, serial/bounded, two placements:
12 configurations, not a new algorithm or mapping search. The
[accepted coverage result](results/group-sharing-001/REVIEW.md) shows some shared
links and changed messages, but zero final group slowdown. Joint gap error is
+48 cycles, still within the registered budget. Retain the scoped simple-model
use; keep bounded for capacity/commit evidence. This is not strong-interference
coverage, and no further model or mapping sweep is launched automatically.

For each local policy q, report delta_m = T_m(B) - T_m(R) and
E_gap = delta_m - delta_bounded = error_B - error_R.
Absolute time bias can cancel in design gains; small opposite errors can change
a close ordering. Record signed cycles, raw ranking and the registered 100-cycle
indifference/error bands; do not magnify relative errors near zero.

Inspect matched messages and existing critical-chain/source-window records to
explain differences. Do not sum overlapping waits into an application time or
interpret a critical-chain fraction as an optimization limit.

## Acceptance and stop decisions

Execution completion, semantic audit, capacity feasibility, reference agreement
and physical calibration remain separate public states. pipeline overflow is a
diagnostic result, never a feasible winner. serial FIFO capacity is unmodeled.
bounded self-agreement is not an independent hardware-accuracy measurement.

Deliver one main decision table, a model-selection conclusion, a design-gap
figure and a same-version execution-cost figure. Preserve all accepted evidence.

If serial predicts design gaps accurately despite absolute bias, keep that
simple use case with its message/capacity limitations. If errors depend on
placement, retain only the state evidenced to explain the discrepancy. If target
policy dominates the conclusion, characterize that policy rather than add more
network detail. If results remain limited to small cases, close this milestone
and plan independent workload/scale coverage; do not search these cases for
another feature to implement. No preselected speedup or ranking reversal.

## Closed or frozen work

Old trace/Chakra recovery, collective/tree expansion, packet event alignment and
runtime hotspot optimization are frozen. Their results remain in the
[milestone index](MILESTONES.md). No new FIFO/NoC, SRAM banks, thermal/PDN,
collective algorithm, GPU acceleration or universal plugin framework is part
of this milestone. Further work is selected only after the design-gain conclusion.
