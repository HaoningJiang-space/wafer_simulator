# Frozen-model external coverage: two TP8 groups

Registered before execution, with `5de7a2f` closing boundary enhancement.
Only workload composition, orchestration and analysis change. Every pre-existing
file in workloads/adapters/architecture/execution/third_party/patches must retain
its frozen Git identity. New namespace/placement helpers do not alter lowering,
resource admission, timing, credit, memory arbitration or native binaries.

Use complete s64 forward blocks (batch 1, hidden 64, heads 8, FFN 128, TP8),
direct-root SUM, rank-local publication, memory 32 B/cycle with 256-byte bursts,
256 KiB/reticle, unchanged compute rates, 2 TX/8 RX slots of 2000 bytes carved
from the same SRAM. Native BookSim, 1 GHz, seed 1; no packet approximation.
These are declared local-resource assumptions, not measured WoW calibration.

In each placement sort endpoints using the existing row-major rule. Assign the
first eight to A and the next eight to B. Keep rank order within each group.
Save endpoint IDs, coordinates and physical budgets BEFORE running any case.
No endpoint search or fallback if the two groups show little interference.

Run A alone at A's position, B alone at B's position, and A+B together at time
zero in ONE executor and ONE native network. The two groups have no logical
dependencies, messages, allocations or local memory/compute resources in common.
Their paths may share physical network resources. Collective rank identities
remain local to each collective; all objects/operations have distinct namespaces.
Each solo must be an exact logical and placement projection of the combined run.
A-only must also recover the prior s64/burst_256 full execution after removing
its namespace, for both models and both placements.

Matrix: 3 scenarios x 2 placements x {serial,bounded} = 12 cells, three fresh
subprocess repetitions each. Rotate model order and alternate placement order.
Use one CPU pair, full identical logging, separated graph/init/execution/close/
serialization/audit timings, CPU/RSS and host load records. Old wall times are
not combined with these cost measurements. Geometry export is reused by hash.

Audit complete dependencies, payload/flits, memory work, storage and output
publication with existing independent checks; verify all repeated full events
and replay each cell's native command stream. Hash every raw artifact. Source,
input, environment and native identity are recorded. No overwrite of old runs.

Report group final-output availability AND operation retirement; compare each
group against its own solo at the same location. Combined application time is
the completion of all work, not the sum of group times. Confirm actual directed
link/router intersection from recorded paths. Temporal overlap and shared-path
use alone do not establish saturation or prove a delay is caused by contention.
Pair messages by stable logical identity and distinguish ready-relative service
changes from absolute shifts. Keep adaptive routing and arbitration unchanged;
network-mediated effects can include different route/service order.

For each scenario compare Baseline minus Rotated under serial with bounded.
Retain the prior 100-cycle absolute gap budget and +/-100-cycle indifference
band. Passing the gap budget does not prove a stable winner near the band.
Serial RX status remains unmodeled; bounded capacity must be feasible. Bounded
is a mechanism reference, not silicon truth. Report absolute-time error too.

Stop after the paired report and cost/coverage judgment. Failure to meet the
budget records an applicability limit; it does not authorize another model.
No new collective, mapping search, bandwidth sweep, FIFO, NoC or thermal work.
