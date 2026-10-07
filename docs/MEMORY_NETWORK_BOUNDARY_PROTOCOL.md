# Memory–network boundary: registered conditional target contract

This study fixes the accepted BookSim router/link/routing configuration. Network
pipeline work is closed. It tests the shared whole-read/message/whole-write
abstraction under an explicitly streaming DMA design hypothesis, not measured
WoW endpoint hardware. No GPC network, new collective, mapping or thermal work.

## Machine contract

- Same SRAM service IDs and rates: reads and writes share the existing regional
  FCFS byte server. No extra memory port or bandwidth. Same whole-object consumer
  visibility, operation retirement and atomic capacity admission.
- DMA handles at most one message per source endpoint until its final flit is
  injected. Read requests are issued in message order, one flit payload at a
  time, reserving a TX slot before requesting memory; two TX slots per endpoint.
- RX has eight fixed flit slots per endpoint. TX/RX occupy `(2+8)*2000=20000`
  bytes carved from the original 256 KiB SRAM budget, for ALL comparison arms.
  These slots are separate from router input VC buffers and object reservations.
  Final-object and collective receive staging allocations remain unchanged.
- The native router's sink-facing credit account is initialized to eight slots;
  all internal router input/output credit capacities remain the author values.
  This is endpoint capacity configuration, not an internal-router algorithm change.
- Reference: each packet is injectable only after its payload read completes;
  its TX slot releases at the injection end boundary. A received packet occupies
  an RX slot through destination write completion. Credit then returns over the
  existing native credit channel (at most one credit per endpoint per cycle).
- A final partial packet reads/writes only valid bytes; network charging remains
  ceil(message_bytes / flit_bytes). No new per-chunk padding or logical messages.
- Endpoint arrivals are processed before local completions at the same boundary;
  all local completions at that boundary precede the next native cycle.
- Receiver can accept arbitrary packet arrival order into pre-reserved object
  offsets. Consumers wait until the entire object is committed. No early compute.

## Three abstractions, one declared machine budget

1. `serial`: existing whole-read -> native message -> whole-write, immediate
   sink credit return. This deliberately omits DMA buffer occupancy and is the
   model under test; it does not claim these resources are physically infinite.
2. `pipeline`: chunk read/inject/write and bounded TX, immediate sink credit
   return. RX occupancy is measured; overflow is reported as abstraction failure,
   never used to claim physical feasibility.
3. `bounded`: same chunk services, with RX credit withheld until write completes.

All arms reserve the same endpoint storage. Comparison 1->2 changes service
interleaving/granularity; 2->3 changes destination credit return ONLY. Chunk
rounding is reported separately from logical bytes. Partial payloads carry their
original message identity and ordinal. No cost is derived by fitting reference.

## Acceptance registered before experiments

Semantic gates: byte/flit conservation, read-before-inject, no bounded FIFO
oversubscription, commit-before-publication, dependency/lifetime/capacity audit;
serial compatibility with accepted events when the unchanged input fits the
reduced usable capacity; transparent adapter vs original native timestamps.
Four complete mechanism conditions: single transfer, source-limited transfer,
multi-source/single-sink write service, shared paths with one slow receiver.
Use analytical recurrences for isolated packet read/arrival/write service and
native trace replay with recorded releases/credits as independent interface check.

Then existing complete s16 and s64 Baseline/row-major/direct-root/TP8 forwards,
unchanged compute, 32 B/cycle shared memory, seed 1. Three cold-process repeats
per arm; rotate order, two fixed host CPUs. No Rotated until model validation.
If fixed 20000 B reservation makes a case infeasible, report it; do not enlarge
SRAM or silently drop work. Application error target <=2% AND <=100 cycles;
per-message commit error target <=5% AND <=20 cycles. Both conditions must pass;
these are explicit screening goals for this small-block comparison, not native
hardware calibration nor thresholds copied from network accuracy work.

Record event identities, source/binary/input/environment hashes, occupancy and
credit events, full-object commit and application time. Separate initialization,
execution, serialization and independent audit wall/CPU cost; lifetime RSS is
labelled, native and Python separately. Report conditional scope if target
service assumptions determine the outcome. Stop at the least detailed model
meeting these declared goals; do not add router microarchitecture to erase tails.
