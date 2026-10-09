# D0: independent spatial service, before application evaluation

Registered against `e3a1592`; new builds/tests/experiments use hn072 only.
The candidate machine, 4×4/6×6/7×7 complete work, three layouts, native binary,
execution/storage kernel and U1/S semantics remain frozen. No new shared-path
model, parameter/mapping search or BookSim mechanism intervention is included.

Question: how much of U1's application and layout error survives correcting
unloaded single-message service on the physical network? D0 retains U1's
bank/controller services, capacities, dependencies and retirement rules.
For each DRAM request, response, write or acknowledgement:

`finish = own_ready_cycle + isolated_service(physical_machine, endpoints, bytes)`.

DRAM messages are independent, including simultaneous messages from the same
endpoint or over the same links. C2C/IO uses the unchanged live native network
as in U1; omitted DRAM sharing with C2C/IO is also part of D0's approximation.
The application never submits DRAM flits to BookSim. Native C2C/IO completions
precede D0 completions on equal boundaries, following U1's ordering policy.

## Component calibration and leakage gate

Generate all required DRAM endpoint/payload tuples from the machine, complete
input DAG and registered layout rules **before any new application runs**.
Each tuple is measured in a fresh empty network with the exact frozen native
binary, seed, topology and router/link policy. Endpoint-specific calibration
allows the independent native routing policy to resolve physical paths; neither
paths nor timing from a full S run enter the table or predictor. This is an
empirical bounded baseline, not an analytical all-size/all-machine model.

Measure every tuple twice at idle readiness cycles 0 and 137; require identical
ready-to-completion duration, injection metrics and component route histogram.
Supplement this with sizes 1, 16, 63, 64, 65, 128, 256, 4,096, 16,384 and 65,536
bytes over 0–5 C2C hops plus HB on the 6×6 physical graph. These 60 tuples also
receive a third holdout at ready cycle 509. The holdout tests clock translation,
not extrapolation to unmeasured sizes/paths. Control messages and long payloads
are calibrated independently; there is no universal 32 B/cycle assumption.

Reject unmeasured machines/endpoints/sizes rather than interpolate. If empty
service depends on idle ready time, stop this registered constant-duration
table and report the limitation. Do not adjust bandwidth to match applications.
Record full-flit captures and independent byte/path audits, hashes of native
binary/config/topology, complete input and environment/source identities.
Independently read every component capture before releasing the immutable table
to application workers. Calibration orchestration accepts no full-S reference
argument; component generation is tested to reject application evidence reads.

## Fixed comparison and acceptance

Use the unchanged scaling registration's nine machine/layout inputs, three
fresh processes per U1/D0/S cell, rotating model order: 27 cells, 81 complete
executions. Require exact accepted full-event hashes for **all U1 and S cells**.
Check work/bytes/dependencies, output publication, storage and retirement for
each run; require zero capacity waits. Replay one native C2C/IO or S command
stream per cell (27). Do not label failed/time-limited work complete.

Report all signed application errors, the existing 2% application budget,
every paired layout gap, the primary A (`clustered_local`) minus B
(`remote_balanced`) decision, false ties and candidate-set regret. Keep the
100-cycle design indifference band and absolute gap-error budget unchanged.
No acceptance requirement forces D0 to pass; wrong direction and a correct
direction with an excessive gap error are different failures.

Meter component calibration and table bytes separately from graph/binding,
native initialization, execution, serialization, audit and replay. Include CPU,
Python/native RSS, native event counts and fresh-process repetition ranges.
Do not compare speed across experiment servers. D0 still uses native C2C/IO;
its speedup omits detailed DRAM events, and calibration is an amortized cost.

Evaluate same-message service error separately from application makespan:
`S-U1 = (isolated_zero_hop-U1) + (isolated_path-isolated_zero_hop)
       + (S-isolated_path)` for the already accepted long response example.
This is ready-to-completion accounting, not independent causal contributions
to application time, nor a partition among credit, buffers and arbitration.

If D0 restores the budgets and layout judgments, do not infer a need for a more
complex shared model. If it fails after validated isolated service, that supports
studying dynamic sharing for this frozen workload/layout set; it does not prove
which minimum state suffices, hardware accuracy or method novelty.
