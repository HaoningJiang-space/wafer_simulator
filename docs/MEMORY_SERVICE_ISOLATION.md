# Memory service contract × endpoint abstraction

Registered before new application execution. This study retains Baseline,
row-major, direct-root, TP8, complete s16/s64, 32 B/cycle shared regional memory,
the same BookSim binary/configuration, 2 TX / 8 RX slots and carved SRAM budget.
It does not calibrate WoW DMA hardware or choose a new architecture algorithm.

## Question and confounding boundary

The accepted request-atomic contract gives serial/pipeline/bounded times of
12534/13583/13583 (s16) and 51966/55944/55944 (s64). Native packetization is fixed
at 2000 bytes. DMA memory requests currently inherit that packet size, whereas
ordinary compute-side reads/writes can occupy a shared port for an entire object.

Serial versus pipeline also changes data release times, source message admission
and destination write readiness. It is NOT a pure on/off overlap intervention.
Whole-message read-before-injection cannot literally buffer an arbitrary message
in two TX slots. Serial remains an abstraction under test, not a physically
executable alternative DMA with hidden full-message buffers. No fake capacity
is added to manufacture an orthogonal experiment.

We instead hold each memory arbitration contract fixed across all three existing
abstractions, and change that contract on a separate axis. The clean feedback
contrast remains pipeline versus bounded. This factorial comparison identifies
policy sensitivity and interaction, not a unique additive causal allocation of
the previously observed difference to overlap alone.

## Two explicit memory contracts

1. `request_atomic` (accepted): FCFS, nonpreemptive complete submitted request.
2. `burst_256`: all memory clients, DMA AND ordinary operations, submit successive
   bursts of at most 256 valid bytes to the same FCFS port. Only the first burst
   is eligible at request time; a next burst requests service when the preceding
   burst finishes. One outstanding burst per logical request. Other ready
   requests may interleave. Stable existing event tie ordering is unchanged.

256 is a declared diagnostic assumption, chosen independently of the 2000-byte
network width. It is not an inferred GPU/WoW bus transaction size. The tail burst
contains only remaining payload. Each burst uses ceil(bytes / service rate);
the configured service latency applies per burst (zero in these controls).
The original logical request completes only after all its bursts. A packet
cannot be injected until ALL payload bytes have been read, and RX credit waits
for ALL corresponding write bursts. No partial-object consumer visibility.
Compute and network service are never split by this memory option.

Capacity, logical memory bytes, MAC/add work, original message identities and
flit counts stay fixed. Any change in integer-rounded busy cycles is reported.
Both contracts are target-policy hypotheses. Comparisons across contracts are
policy interventions, not model accuracy against measured hardware.

## Bounded execution matrix and checks

Two complete shapes × two contracts × serial/pipeline/bounded = 12 cells;
three cold-process repeats each, order rotated, same CPU affinity/full logging.
Run request_atomic cells as compatibility controls and require entire execution
records to equal the accepted boundary-004 counterparts. No new workload,
mapping, collective, bandwidth point, buffer capacity or native build.

Before applications: hand-derived two-client FCFS burst schedules, partial
burst and per-burst latency, unchanged unsplit compute/network, no early packet
supply/credit, work conservation, audit tampering rejection, complete collective
life cycle and deadline tests. An independent reader reconstructs burst demand
amounts from original work; it does not invoke execution's splitting helper.

For each contract separately report serial/pipeline error against bounded using
the existing <=2% AND <=100-cycle application and <=5% AND <=20-cycle message
screens. RX feasibility is separate from time accuracy. Also report source read
windows, interleaving clients, critical chain, work, service counts, costs and
peak storage. For each shape define:

    gap(q) = T_pipeline(q) - T_serial(q)
    interaction = gap(burst_256) - gap(request_atomic)
    feedback(q) = T_bounded(q) - T_pipeline(q)

The interaction says how the boundary contrast depends on memory policy. It is
not the isolated cycle cost of overlap and it does not establish architecture
ranking. Native command replay checks protocol determinism, not another network
implementation. Stop after this attribution; do not launch Rotated until the
target-policy interpretation is documented.
