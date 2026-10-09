# Frozen policy traces: critical chain and DMA contract checks

Freeze all pre-existing source, machine controls and accepted evidence at
`014130dde70eec86b86af1b0364c9a974267eef5`. Add analysis and its regressions only;
run them on hn072. Analyze the existing 18 applications, verify saved bytes,
reconstruct bindings and recheck execution plus the recorded critical chains.
There are no new simulations, replay experiments, timing inputs or parameter
scans. Large event/derived tables remain on the experiment server.

## What the accounting measures

Reconstruct one execution-dependency/resource critical chain per run using the
unchanged checked chain reader. Its intervals must cover [0, makespan) without
gaps/overlap. Separate compute, SRAM, DRAM bank serialization, bank trailing
latency, external store, controller command/channel and network protocol roles.
Network intervals remain observed ready-to-all-flits-complete durations. Slice
them into ready-to-generation, generation-to-first-injection, injection span,
and last-injection-to-completion; these are elapsed intervals, not exclusive
router/credit causes. Selected chains may change operations across policies.
Their differences close the makespan arithmetic but are not independent causal
contributions, and omitted network-internal dependencies remain opaque.

For each logical movement, reconstruct payload fragments, array/channel
serializer intervals and message readiness/injection/delivery. Measure same-
transaction bank/channel busy overlap and bank/network-pending overlap, first
payload readiness relative to transaction start, fragment release span and
transaction completion. Latency is separate from serializer occupation. Report
matched movements and both distributions and critical examples; do not add
transaction medians to obtain application time.

Use actual flit routes and directed-link arrival times only for post-execution
diagnosis. For each selected critical message's link-use window, count its own
flits, other fragments of the same logical movement and different transactions.
These are actual shared service windows, not queue-delay estimates. Compare
semantic flit routes and source injection order across the shared-interface
whole/pipeline runs, where interface identities are fixed. Match payload flits
by transaction plus byte offset; match request/ack flits separately. Record
release/injection activity in fixed 256-cycle bins. Activity is not saturation.

## DMA and receive definitions

The code enforces four logical end-to-end window positions **per transaction**.
Measure a fragment position over [source phase ready, destination phase finish),
including queued source service, network and destination commit. Aggregate these
positions and useful bytes by associated controller; they need not be resident
inside that controller. Release at a boundary precedes reuse at the same boundary.

Also report active transactions from controller command readiness to final
destination commit as one explicitly defined descriptor-lifetime proxy. Report
the broader transaction launch-to-finish population separately. Neither is a
hardware descriptor model: hardware may have a different lifetime or use several
descriptors per transaction. Bank/channel FCFS, command rate and full-object
staging capacity do not impose a controller-wide descriptor/fragment count cap.
Report the existing staging reservation peak and limit separately.

Compute an observational receive envelope from useful flits arriving at
ejection+1, subtracting each fragment only at destination phase completion.
This counts assembled/uncommitted data under atomic fragment commits, including
partially received fragments. It is an envelope, not certified FIFO residency:
partial consumption during serialization is not recorded, no explicit RX resource
is admitted, and native endpoint credit return is not tied to the subsequent SRAM
or bank commit in these runs. User confirms no hardware descriptor, slot or RX
budget is available. Contract status must therefore remain **unmodeled/uncertified**;
observed count above four does not by itself establish an implementation bug.

## Message batching and research boundary

Inspect the frozen native trace injection implementation and config. Trace mode
generates single-flit packets (`head=tail=true`, packet ID=flit ID), one ready
message batch only when that source's partial-packet queue is empty. Thus 254
versus 1,445 messages changes batches, readiness and source ordering; it does not
change the wire packet size or add packets beyond the same 92,525 flits. Source
generation/injection order and fabric service can still change together.

No observational metric can uniquely split the 2,442-cycle relative benefit
among earlier supply, stage overlap and changed generation/service ordering.
State supported mechanisms and unresolved alternatives explicitly. Keep both
machine/policy contracts as declared candidates. v1 is the numerical reference
for its already registered D1 experiment only; no hardware-based principal
contract is selected without controller/DMA/RX implementation evidence. Do not
extend D1 or compare its old numbers to pipeline S in this task.
