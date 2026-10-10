# G2.1: guarded two-cycle transition on the existing G1 state machine

Status: registered implementation/validation work, not an accuracy or speedup
receipt. This gate covers one source-0 message to endpoint 3 under the exact
primary G1 contract. Multi-source traffic, two-flit buffers, other routes and
G2.2/G2.3 are excluded. Accepted G1 source and evidence stay byte-pinned.

The implementation reuses the pinned G1 transition body. A checked mechanical
derivation exposes its cycle boundary, substitutes equivalent lazy homogeneous
source-label storage and compressed evidence containers, and replaces final
materialization. It does not change arrival handling, source admission,
VC/switch decisions, output scheduling, reverse credits or retirement order.
The derived ordinary Python source and its hash are saved for review. An
unmodified G1 run is the independent reference; a macro-disabled run of the
same derived core isolates the effect of skipping service computation.

## Translation and guard

The kernel includes ordered live FIFO labels/metadata, ownership, exact pending
switch deadlines, pointers, credit balances, source eligibility and every
ordered in-flight event. It uses integer tuples, not Python tracing or JSON.
Clock and live flit labels may translate; generation epochs do not. Remaining
source and receiver work and diagnostic counters remain explicit.

The guarded region has a single generated homogeneous message, no pending
external demand, the fixed source/route/contract, and positive finite remaining
work. No other input/output can request service. Under these conditions the
pinned transitions are equivariant under simultaneous clock and flit-label
translation: comparisons use deadlines/eligibility and resource state, while
labels identify interchangeable single-flit packets. Source-empty, receiver
completion and deadline exits must remain outside the batch. This structural
argument, not three observations alone, licenses repetition.

Require three observed two-cycle transitions with the same complete kernel,
progress and emitted template. Per period the fixed signature consumes one
source flit and one pending ejection; source stalls increase by one, router
stalls stay unchanged, and peaks are unchanged. All credits and in-flight
events are internal to the recurring kernel. The macro count is bounded by
`min(source_remaining-1, receiver_remaining-1, (cycle_limit-now-1)//2)`.
The final source/receiver unit and deadline boundary are never skipped.

One macro translates the bounded live frontier and in-flight events, moves the
source suffix cursor, updates counts/stalls, and appends a repeat descriptor.
It never constructs one dictionary per skipped flit/event. Normal execution
resumes for the tail and final credit drain. A periodic output count alone,
an absent credit, changed owner or unmatched event cannot authorize a batch.

## Verification and cost

On hn072, compare unmodified G1, macro-disabled derivation and macro-enabled
derivation for the frozen sizes and delayed release. Expand compact evidence
outside timed execution and require complete prediction equality, including
all allocations, flits, services, credits, peaks, stalls, finish and drain.
At each macro entry/exit independently capture the original G1 boundary and
compare logical kernel, finite counters, deadlines and next events. Inject
wrong ownership/credit/event/counter states and ensure rejection. Timeout is
incomplete even when a macro was taken.

Benchmark 1,024/8,192/32,768 flits, three shuffled repetitions, fixed CPU
affinity and identical counters-only output for macro off/on. Record physical
cycle updates, skipped logical cycles, macro count, prediction wall time,
complete worker wall time, CPU and peak RSS. Report source/recording benefits
separately from macro off/on acceleration. Compact evidence and full expansion
have separate costs; counters-only execution is not a full flit audit.

Use fresh directories, clean main, same-source tests, source/interpreter/input/
environment/result hashes. Preserve all failed attempts and large evidence on
hn072. Do not retune the contract, use Native internal events, or claim a general
network backend, application-gap result or hardware calibration.
