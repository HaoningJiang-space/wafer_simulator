# CSR dependency backend and ordered readiness

This is the first implementation of the data-layout/frontier ideas assessed in
[HETEROSTA_TRANSFER.md](HETEROSTA_TRANSFER.md). It is an additive patch over the
completion, topology-reference, runtime-array and node-reuse patches. The
author submodule and previous binaries remain frozen.

## Exact boundary

`patches/booksim-csr-frontier.patch` replaces the native trace's vector of
successor vectors with CSR row offsets and contiguous successor IDs. Loading
uses two passes over the existing JSON DOM, with no temporary vector per row.
Both dense-but-unsorted instruction IDs and unsorted successor lists retain
their reference semantics. Initial roots still enter in file order.

Mutable remaining-dependency counters, timestamps, CPU reservations, progress
and network state remain separate from the static graph. One instruction's
completion updates its successors and compacts newly ready IDs into a reusable
frontier, preserving row order. It then submits that frontier before processing
any other completion. This is safe because the submission callback only queues
events and reserves CPU lanes: it does not recursively complete instructions or
inspect another successor's dependency counter.

This boundary deliberately excludes batching multiple completed instructions.
A zero-duration join inserted by one completion can precede an already-due
event in the completion heap. Merging them into an unordered frontier changes
CPU reservations, subsequent message injection, and potentially application
time. Network arbitration and credit phases continue to use the existing core.

For 5,324,230 operations and 9,002,700 edges on the server's 64-bit ABI, the two
CSR arrays contain 114,615,448 bytes. The previous vector headers plus logical
edge payload contain at least 199,803,120 bytes, excluding allocator overhead
and spare capacity. This arithmetic is not an RSS or speed measurement: JSON
DOM allocation and allocator retention remain, and network execution can still
dominate elapsed time.

## Instrumentation and layering

- Native `trace_dependency_graph.hpp`: flat static graph storage.
- Native `trafficmanager.cpp`: ordered dependency update and resource submission.
- Native `trace_frontier_profile.hpp`: optional constant-size histograms, with
  no per-event logs or allocations.
- `analysis/dependency_profile.py`: independent histogram/conservation readback.
- `experiments/runner.py`: enables profile output and requires its audit when
  the campaign requests instrumentation.
- `configs/llama16_csr_frontier.json` and remote scripts: registered full-input
  comparison and eventual exact input/event-hash acceptance.

`dependency_profile.json` is separate from the unchanged application event
format. It records successor edges and newly ready tasks per completion, plus
completions per active application cycle. The latter includes causally ordered
zero-duration chains; it is not a count of independent GPU work. This stage does
not profile router/port/VC parallelism or establish a CPU/GPU crossover.

Readback requires every instruction to complete, every static edge to be
processed once, and roots plus newly ready instructions to equal the full
instruction count. Histogram totals, bounds, maxima and CSR byte counts are
checked. Initial roots are independently reconstructed from the original graph.
Incomplete profiles are rejected as full-run evidence.

## Acceptance

Run builds and verification only on eex005. Native semantic regressions include
CPU callback order, a zero-duration heap insertion ahead of an already-due
event, shared successors, and malformed dependency rows. Compare the frozen
node-reuse binary against the CSR candidate on identical unit inputs and demand
byte-identical application reports and identical network metrics. These checks
are correctness tests, not synthetic performance experiments.

The formal candidate is `runs/llama16-full-006-csr-frontier`, using both complete
placement traces, unchanged payload and dependencies, seed 1, and fixed clocks.
Its reference is `runs/llama16-full-005-node-reuse`. After independent full audits,
the wrapper compares the complete `trace.json` and `events.jsonl` hashes as well
as application and network results. The profile is enabled in the candidate;
wall-time comparisons include that overhead. Concurrent runs and earlier
debugger sampling make wall-time ratios observational.

Build/test/run results will be recorded below after remote verification. No GPU
kernel or completed full-capture acceleration is established by this change.
