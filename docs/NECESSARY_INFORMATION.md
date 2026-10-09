# Necessary information and boundary-preserving computation

The research object is the closed execution of a declared machine, workload,
placement and policy. Changing the memory organization or transaction policy
changes that object. Changing the solver tests an approximation of the same
object. The v1 whole-object and shared-interface ideal-pipeline contracts remain
separate; neither is selected as hardware truth from its layout ranking.

The physical resource graph identifies contention. The causal graph identifies
when data and requests may reach those resources. A method needs both. Different
components can use different internal granularities if their shared resource
identities and supply, arrival, completion and feedback boundaries agree.

## Omitted information, distinguishing cases and evidence

“Observed” below refers to saved executions or explicit implementation behavior.
“Constructed” denotes a reasoning example, not a measured native intervention.
An approximation can fail without uniquely identifying which omitted mechanism
caused its failure.

| Omission / compression | Distinguishing case | Existing evidence | Supported conclusion and limit |
|---|---|---|---|
| Independent message duration without background state | Same endpoints/payload, empty versus occupied path | [Isolated responses](results/isolated-response-001/REVIEW.md) and [D0 applications](results/independent-spatial-service-001/REVIEW.md), observed | Isolated service is insufficient for the registered v1 A/B gains. The intervention clears all background/history; peer traffic counts do not allocate causal cycles to individual peers, arbitration, buffers or credit. |
| Whole route active from source-ready, with propagation added afterwards | Same ready flows, but data reaches their common service point at different times | [D1 contract](SHARED_SPATIAL_SERVICE_PROTOCOL.md), observed implementation; local-arrival example below, constructed | Immediate end-to-end sharing can conflate source eligibility with local arrival. The registered staggered cases vary source-ready times; they do not independently vary propagation to a common point. Application error does not uniquely establish this as the cause. |
| End-to-end flow fairness without input-queue identity | Same three flows and common output, different merge/input structure | Existing D1 `three-shared` and `two-source` components, observed unequal native message completion; branch-fairness example, constructed | Max-min over flow routes is a candidate rule, not a native arbitration law established by those measurements. Unequal completion times alone do not measure steady-state fairness or isolate input arbitration. |
| Only total bytes / final duration, without supply boundaries | Same objects and nominal rates, whole versus fragmented supply | [Periphery policy experiment](results/memory-periphery-001/REVIEW.md) and [matched critical chains](results/memory-periphery-attribution-001/INTERPRETATION.md), observed | B improves from 31,303 to 23,561 cycles while its W payload envelope remains 6,177 cycles. Supply and composition matter. Fragmentation also changes request granularity, latency instances and FCFS interleaving; this is a combined-policy contrast. |
| Destination commit treated as source-visible feedback | Same destination commit, different return-notification arrival | [Ideal window contract](MEMORY_WINDOW_CONTRACT.md), observed implementation; delayed-notification contrast, constructed and unexecuted | Current commit visibility is explicitly global and immediate. Its physical impact is unquantified; no controller-wide DMA/RX budget or real completion protocol has been inferred. |

For the local-arrival example, let one resource serve one unit/cycle. Flow a
arrives there at cycle 0 with ten units; flow b is source-ready at cycle 0 but
reaches the resource at cycle 50. Local service can finish a at cycle 10. An
end-to-end rule sharing with b from cycle 0 can instead finish a at cycle 20.
Adding b's propagation delay after serialization does not remove a's fictitious
competition. This establishes a possible information loss, not a measured D1
application error or a proposed parameter correction.

For the branch example, two flows enter through one input and one through
another. If a service rule divides 32 units/cycle equally between inputs, then
divides the first input's share between its two flows, the rates are 8/8/16.
Equal end-to-end flow sharing gives 32/3 each. Both are declared examples; the
native rule must be checked using actual arrival and arbitration evidence.

The [registered D1 comparison](results/shared-spatial-service-001/REVIEW.md)
tests a bundle: deterministic minimum-hop routes, immediate whole-path
occupancy, equal-weight max-min allocation and post-serialization propagation.
Its routes and ready events are generated independently. Native paths, service
durations and ready offsets are read only after prediction as diagnostics.
Neither concurrent component error nor closed-loop application error identifies
a unique missing state. D0 still uses native C2C/I/O while D1 replaces all
traffic; their difference is not a pure intervention on DRAM sharing.

## A criterion for preserving state

Let a compression retain z = Pi(x). If two detailed states with the same z,
under the same future inputs, produce scalar target outputs separated by more
than 2 epsilon, any common prediction must exceed epsilon error in at least one
state. This follows from the triangle inequality. It motivates distinguishing
cases before adding state; it is not an established error bound for this code.

For one useful-data stream of D bytes, useful boundary progress can be written
as source-produced P, network-injected I, destination-arrived A and
destination-committed C, with 0 <= C <= A <= I <= P <= D. Protocol bytes and flit
padding are separate work. These counters describe boundaries, not four assumed
physical FIFOs. Source-visible completion is another boundary; the current ideal
policy deliberately identifies it with destination commit.

## Next method question, not an implemented backend

The [first detailed S profile](results/native-service-profile-001/REVIEW.md)
measures native advancement, interface work, recording, serialization and audits.
A lighter record mode is acceptable only
after its message completion and application events match the detailed mode.
If repeated service computation is the relevant cost, investigate whether a
local service process can be advanced in a batch
while preserving its arrival, service order, capacity and completion boundaries.
Stop a batch at a new arrival, service completion, arbitration change, window
transition, feedback return or the executor's requested boundary. Retain the
actual service object's identity where flow identity is insufficient. This
targets repeated computation before substituting a new physical sharing rule.
It does not claim that arbitrary native arbitration admits long stable batches.

Validate the service operator with identical inputs and initial states first;
then let complete executions generate their own future requests. Native
application timestamps can supply offline diagnostic inputs, but cannot be used
as prediction inputs in the independent closed-loop comparison. Track the first
different boundary as well as the final critical chain. No queue/credit model,
event-compressed backend, runtime fidelity switch or new workload is implemented
by this milestone.

Timing error, signed design-gap error and reference choice regret remain separate.
D0's A/B misselection at 6×6 costs 658 reference cycles, despite its 6,870-cycle
gap error; allowing Local reduces its global regret to zero. The existing 2%
application and 100-cycle gap budgets stay fixed. Average MAPE is not a certified
per-design error bound. A future shared, single-copy workload should create
natural placement choices; these repeatedly examined GEMM points are regressions,
not independent holdouts. No novelty or hardware-accuracy claim is established
by this research framing.
