# Memory-periphery organization and transaction policy

Post-run clarification: the unchanged window feedback is
[ideal_commit_visibility](MEMORY_WINDOW_CONTRACT.md). The contrast changes
service/request granularity and latency instances as well as overlap. The
original registration below remains the campaign record; its results have
since passed [stronger acceptance checks](results/memory-periphery-audit-fix-001/REVIEW.md).

Register before applications against v1 source `2c4ed6b`. Preserve old machine,
results and D1 candidate. Run new tests/components/applications only on hn072.
D1 application validation is deferred; its completed component captures remain
evidence for the registered hypothesis, including unequal native service at a
two-level merge and a common source.

## Declared organization and distinct services

The v1 physical inventory, rates, capacities, geometry, links and native binary
stay fixed. v1 gives each bank a separate endpoint. The new organization gives
each controller one bidirectional network interface shared by its partitions.
SRAM interfaces remain separate; the external controller has one partition.
Storage regions/ports and controller IDs stay distinct. New endpoint numbers
are contiguous and their map is part of the organization identity. There is
one native injection/ejection endpoint and one router port per interface, not
one per bank. This changes the declared network attachment/port organization;
it is not an equal-physical-cost comparison or a change of simulator fidelity.

Bank `/port` is an independent analytical array-side serializer at 32 B/cycle,
followed by 30 cycles of pipelined latency. Controller `/channel` is the shared
peripheral data path at 64 B/cycle. Neither includes the other or the network
interface. These are distinct declared services, not product-derived values.
The external store retains its existing rate/latency. Channel and bank work
must each equal the payload byte count. Latency does not retain a serializer.
The aggregate compute node is a declared reticle-region gateway/service,
not an area/performance-calibrated full reticle or an individual PE; its
256 MAC/cycle, SRAM and supply ratios are retained assumptions.

## Fixed transaction policies

Whole-object policy is unchanged: read request -> command -> full bank service
-> full channel -> full response -> SRAM write. Write: SRAM read -> full data
arrival -> command -> full channel -> full bank commit -> acknowledgement.

Pipeline uses a fixed 4,096-byte DMA fragment, with at most four fragments in
flight **per transaction**, including bank/source read, channel, network and
destination write. The next fragment in a window slot waits for that slot's
prior destination commit. A final short fragment contains exact remaining
bytes. This is a declared DMA choice, not a DRAM command or row size. No size or
window sweep, performance fitting or layout adjustment belongs to this study.

Read: one request and one command precede all bank fragments; each fragment
then traverses channel -> network -> SRAM. Independent bank requests serialize
on the same bank port and their trailing latencies may overlap. Each bank
fragment has the existing analytical latency; it is not a newly added command.
Write: SRAM fragment -> network; one command follows the first received
fragment; each received fragment then traverses channel -> bank. One ack waits
for every bank fragment commit. All fragments use the same physical IDs.
C2C SRAM-to-SRAM movement keeps the existing whole-object policy. External
controller traffic follows the same periphery policy as DRAM traffic.

Atomic whole-operation admission, full-object SRAM/controller reservations,
retirement-time staging release, sequential operands, compute work, output
publication and logical dependencies remain unchanged. The four-fragment
window uses the existing reserved staging; no unlimited intermediate buffer
or free capacity is introduced. Data is published only after the whole operation
and its final response/ack completes. This isolates service overlap from a
different allocation/lifetime policy. It is not a finite-VC/buffer certification.

## Six application cells and independent checks

6x6 A=`clustered_local`, B=`remote_balanced`: v1 whole, shared-interface whole,
shared-interface pipeline. Three fresh-process rotated repetitions: 18 complete
applications. Compare interface change at whole-object policy, then policy
change at fixed shared organization. This three-arm chain does not identify
the interaction with pipeline under bank-specific endpoints.

Before applications check 64 KiB reads/writes and two-bank shared-controller
reads in all three conditions (nine components). Semantic regressions check
remainder coverage, controls, byte/work conservation, explicit interface
ownership, pipelined latency vs occupation, window backpressure, sequential
operands, publication and incomplete execution. Reproduce v1 A/B execution
hashes exactly, and compare old/new v1 exported topology and config bytes in
the same directory. Preserve core execution/storage and upstream source.

Independent audit derives logical moves from work/placement; verifies exact
fragment coverage, demands, controls, causal dependencies, window limits and
native endpoints/routes, then reuses service/dependency/capacity/lifetime audit.
Replay every component and first application repetition's six native command
streams. Missing bytes/messages, dependency truncation, timeout, changed v1
events or nonrepeatable results prevent a COMPLETE receipt.

Report application cycles, signed A-B gap, 100-cycle ranking, policy/interface
effects, actual A/B regret of the old preferred layout under each condition,
traffic arrival/injection summaries, and bank/channel resource work/occupancy.
The 100-cycle prediction-gap and 2% prediction budgets remain registered for
D0/D1; these changed machines/policies are not prediction errors against v1.
They are not holdout generalization. Local's old global-optimum result remains.
Record full-worker and phase wall/CPU times, Python/native RSS, artifact bytes,
source/binary/input/environment/result hashes. Calibration is zero for this
native policy comparison; validation and replay costs are separate. Keep large
event/capture files on hn072, publish compact checked records.
