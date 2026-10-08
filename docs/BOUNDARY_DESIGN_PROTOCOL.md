# Frozen boundary models: design-gain prediction

Question: at fixed local policy, does simplifying the memory/network boundary
misestimate the Baseline minus Rotated application-time difference?

Freeze execution, native hooks, adapters, upstream sources and binary at the
accepted implementation. Only orchestration, analysis, public statuses and
documentation change. Reuse the accepted boundary worker without modification.

## Controls and registered decisions

[Registration](../configs/boundary_design.json) fixes two complete TP8 direct-root
blocks (s16/s64), two placements, request_atomic/burst_256, and
serial/pipeline/bounded: 24 configurations. Copy the accepted input descriptors;
only placement geometry changes. Retain row-major logical binding, seed 1,
32 B/cycle shared memory, 256 KiB/region, 2 TX/8 RX slots and the deducted
20,000 B. Full-object visibility, rank-local outputs and all dependencies stay.
Network is native BookSim in every arm; do not combine the packet candidate.

Both geometries are exported by the pinned author code. Save endpoints, worker
assignments, coordinates, resource counts and topology hashes. Baseline export
must equal its accepted export. Within one placement the three models use the
same target/input identity; across placements logical work and local policy
must agree. Network resource costs need not match; report the difference.

Each configuration uses three cold processes with identical CPU affinity and
full logging. Interleave placements and rotate mode order between repetitions.
All 12 Baseline cells must reproduce the complete accepted execution records,
not just makespan. Their repeated cost measurements do not expand workload
coverage. Historical wall times are not combined with these measurements.
Keep initialization, execution, serialization, audit and lifetime RSS separate.
Do not add stage costs from different processes or multiply old speedups.

For each shape/policy, compute delta_m = T_m(B) - T_m(R) and
gap_error_m = delta_m - delta_bounded = error_B - error_R.
Report all signed cycles and raw ranking agreement. A **100-cycle absolute**
gap-error target and **100-cycle design-indifference band** are declared before
running; they are research decision tolerances, not hardware precision or
statistical confidence intervals. Also report exact values so readers can use
another budget. Do not divide by a near-zero reference gap. Application/message
tolerances remain those in the original boundary protocol, unchanged.

## Statuses and evidence

Keep these independent in the public cell summary:
- execution_completed;
- semantic_audit_passed;
- capacity_status = feasible / violated / unmodeled;
- reference_agreement, with separate application/message flags;
- hardware_calibration_status = uncalibrated_local_resources.

serial FIFO capacity is unmodeled. pipeline overflow is a valid diagnostic
execution with violated target capacity, never a feasible-design winner.
bounded self-agreement is labeled reference, not independent measured accuracy.
The manifest separates target resource/policy, abstraction and implementation/
measurement. Timeout or audit failure prevents COMPLETE.json.

Use existing independent byte/lifetime/timing/occupancy and critical-chain
audits. Replay one native command stream per configuration as interface evidence,
not an independent hardware/network model. Require all hashes, repeats and the
complete 24-cell matrix. Record mapping and resource differences explicitly.
Attribution uses matched logical messages, actual paths, memory-service waiting,
and existing critical chains; overlapping waits are not added to makespan.

## Deliverable and stop rule

Deliver model_decision_table.csv, per-cell statuses, paired messages, two figures
(design gaps and contemporary execution cost), and model_selection.md.
Evaluate whether model errors cancel between designs and whether that depends
on local policy. No predetermined speedup or reversal. If simple timing suffices,
retain it within that scope; keep capacity/message limitations separate.
Close this milestone before independent workload scaling or component calibration.
No new FIFO/NoC, collective, mapping search, thermal or runtime optimization.
