# A declared compute-wafer / memory-wafer machine

This document records the original **v1** integration contract. Its bank-specific
endpoints and whole-object policy remain available and its evidence is preserved.
The distinct controller-shared organization and bounded policy are described in
[MEMORY_PERIPHERY_PROTOCOL](MEMORY_PERIPHERY_PROTOCOL.md), with the
[checked six-cell comparison](results/memory-periphery-001/REVIEW.md). They do not
retroactively change v1 or provide hardware calibration.

The [acceptance repairs](results/memory-periphery-audit-fix-001/REVIEW.md)
revalidate the original evidence without changing its timings. Shared-interface
ports are checked after actual NIC attachments exist; v1 retains one port per
Store. The pipeline's [window contract](MEMORY_WINDOW_CONTRACT.md) explicitly
uses ideal remote-commit visibility and has no controller-wide hardware DMA
budget or certified RX capacity. Both policies remain declared candidates.

The integration defines the machine independently of one network generator,
compiles it into the accepted target execution interfaces and verifies actual
data paths. Hardware organization and numerical rates remain declared.
`nw-design-for-wsi` remains a pinned **Logic-on-Interconnect network baseline**.
Its Baseline/Rotated results and all accepted evidence stay unchanged.
The uncommitted benchmark-envelope draft was superseded before any run.

## Physical candidate and evidence

The candidate has one stitched compute wafer and one aligned memory wafer.
The latter contains explicit bank/controller peripheries, with one HB connection
to each corresponding compute tile. Memory peripheries are leaf gateways; they
provide no lateral transit fabric. An edge I/O gateway connects external storage.
Only compute tiles provide compute resources. Each owns a finite local SRAM.

Primary evidence motivates the mechanisms, **not their combination or rates**:

* [Lauterbach, The Path to Successful Wafer-Scale Integration, 2021](https://doi.org/10.1109/MM.2021.3112025)
  describes inter-reticle metal stitching in Cerebras. This supports a physical
  route for lateral connectivity; our mesh is not a Cerebras reproduction.
* [TSMC SoIC](https://3dfabric.tsmc.com/english/dedicatedFoundry/technology/SoIC.htm)
  describes heterogeneous WoW stacking and identifies high-yield nodes and
  same-size die designs as suitable conditions. It does not qualify the complete
  stitched-compute / DRAM-wafer combination proposed here.
* [WoW network paper v2](https://arxiv.org/html/2603.05266v2) describes a different
  LoI organization and aggregate compute-reticle routing. That organization
  remains supported through its existing adapter, not imposed by the new model.

All numerical values in `configs/wafer_machine.json` are **design assumptions**.
No memory/SRAM bandwidth, compute rate, link budget, yield or area is inferred
from a vendor marketing total. The declared 4x4 array occupies 104x132 mm within
a 300-mm wafer; the unused area is not secretly populated. It is a finite
candidate layout, not maximum utilization of the wafer. Each aligned region has
one aggregate compute service, 4 MiB SRAM, two 64 MiB banks, a shared controller
channel, and 1 MiB controller staging. Host staging is separately budgeted.
The memory-periphery logic and its physical cost still need implementation
characterization; being represented in a resource graph is not area closure.

Validation checks:

* footprints fit the wafer and do not overlap on one layer;
* C2C edges cross a shared compute-tile boundary and require explicit stitching;
* lateral wire latency respects the declared distance/pipeline bound;
* HB connects aligned, same-size, distinct layers and consumes signal budgets;
* signal counts and declared signaling rates determine directional bandwidth;
* router ports include local endpoints as well as physical connections;
* banks belong to their declared controllers and finite spatial capacity;
* an external gateway attaches at an exposed compute-array edge.

These are consistency checks. Bond pitch, signal budgets and signaling rates
are assumptions, not foundry design rules. Power/ground bonds, routing closure,
redundancy, yield, refresh, bank activation and thermal are not evaluated.

## Transaction and execution contract

The machine model contains physical identities/resources only. A new adapter
lowers logical objects plus placement into existing phases and reservations:

| Operation | Ordered path and service |
|---|---|
| Local SRAM access | Existing finite SRAM read/write port |
| C2C input | Source SRAM read, compute mesh transfer, destination staging write |
| Memory read | 16-byte request through compute mesh and HB; controller command; bank read; shared channel; data response; destination SRAM write |
| Memory write | SRAM read; payload through compute mesh and HB; controller command and shared channel; bank write; 16-byte acknowledgement |
| External input/output | Same transaction rule via the declared edge I/O link and host controller/store |

For a nearby bank the request/response uses HB only; remote banks additionally
use the compute mesh. Return data follows the reverse endpoint relation, not a
zero-cost remote-memory lookup. Every request/ack occupies at least one 64-byte
flit; payload padding is reported separately from useful bytes.

Controllers share a command server and a bidirectional data service among their
banks. Banks have independent byte serializers and a declared post-service
latency; this is a **pipelined analytical bank**, not JEDEC DRAM timing. Latency
does not keep the byte serializer busy. Channel and bank service are sequential
in this first contract; their overlap is not modeled. Command work is reported
separately, despite using byte demand units for compatibility with the calendar.

The policy is whole-object, request-atomic service (`memory_quantum_bytes=None`).
Input/output SRAM staging, final bank objects and whole-object controller
staging all consume explicit capacities. Controller staging is conservatively
reserved for the entire admitted operation, then released at retirement. This
may reduce concurrency; it is a declared policy, not a claim about an optimal
hardware controller. Requests/acks are protocol state, not additional logical
tensor allocations. There is no free unlimited receive FIFO certification.
Consumers see an object only after its required write/ack completes.

The existing execution/storage/calendar code and native binary are unchanged.
Native BookSim handles all network packets online. The adapter rejects physical
links that do not provide exactly one declared flit per cycle: heterogeneous
rates must not be silently rounded into identical native bandwidths.
Ordinary operations are supported initially. Collective-to-DRAM lowering is
rejected until its transaction contract is specified; existing SRAM collective
and historical WoW paths remain available through their existing adapters.

## Acceptance work, not an architecture ranking

`configs/wafer_machine_validation.json` registers 16 complete pairs of dense
float32 GEMMs, `Y_i = (X_i W_i) V_i`, with the second GEMM on the next logical
compute tile. One input is in host storage, the others initially in local SRAM;
weights and final results reside in banks. This exercises I/O, C2C, HB, bank
service and remote-memory responses without inventing traffic multipliers.
Dimensions are rows=32, hidden=128; all 32 operations must complete.

Three fixed placements move only bank homes: near the consumer, half-array
offset, or all at controller 0. Logical work, task placement, topology, rates,
capacity, seed and transaction policy stay identical. No placement search.
These complete declared cases establish machine integration, not a general
locality conclusion or a native Llama/wafer performance prediction.

Remote validation must retain full source/config/binary hashes, independently
audit work, request/response order, controller bytes, legal physical paths,
capacity and output publication, and replay every native command stream.
Tests include illegal unstitched links, HB misalignment, port/bond oversubscription,
an independently calculated single-read completion, insufficient staging and
premature output rejection. Timeout/incomplete work cannot produce COMPLETE.

The subsequent [U0/U1/S model comparison](results/memory-abstraction-001/REVIEW.md)
holds this machine and work fixed within each layout and is now complete.
Its model-selection evidence is separate from the integration acceptance above;
neither study establishes physical calibration.
