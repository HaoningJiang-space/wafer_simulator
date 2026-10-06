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

## Remote verification, 2026-10-06

The candidate compiled on eex005 with the complete five-patch stack. Binary
SHA-256: `9807d4a81c07e29bf1f40dec11fbc9dad9f64d66319c6dbdd5103c04b4256255`.
CSR patch SHA-256:
`2c2fd847f3dcebd100750e577cbaf760864e3edbe568a2d7623e0f2288ca510e`.
The build records both the patch-set digest and the resulting working-tree diff
in `.wafer-csr-frontier-patches`, including all added headers.

`scripts/test_csr_frontier_remote.sh` passed 18 semantic tests against each of
the frozen node-reuse and CSR binaries. Fourteen saved native cases have
byte-identical inputs/reports and identical network metrics. The candidate's
profile accounting passed; incomplete and deliberately corrupted readbacks were
rejected. Evidence is under
`/home/wangziheng/wafer_simulator/runs/csr-frontier-semantics-001/`, including
`equivalence.json` and both unit-test logs. These are correctness results only.

The first build attempt stopped before compilation because its script omitted
the node-reuse prerequisite. The script was corrected; that unbuilt worktree is
retained as `build/booksim-csr-frontier-incomplete-patch-list`. The candidate
above was built from a fresh worktree with all five patches.

The complete-capture comparison remains pending. No GPU kernel or full-capture
speedup is established by this change.

## Whole-input structure, before a GPU decision

The separate static inspection at clean commit `4206a08` read every operation
and both complete edge arrays on eex005. It recorded the graph-file hashes in
`runs/csr-frontier-static-001.json`; this was an input analysis, not a simulation
or performance run. There are 5,324,230 nodes, 9,002,700 edges and four roots.

| Successors per operation | Operations |
| --- | ---: |
| 0 | 4 |
| 1 | 3,534,686 |
| 2 | 1,783,180 |
| 3 | 10 |
| 4 | 14 |
| 16 | 64 |
| 256 | 5,152 |
| 512 | 1,088 |
| 768 | 32 |

About 99.88% of operations have only one or two successors. Another 6,272
operations have 256–768 successors, so the work is irregular rather than
uniformly wide. Static fanout bounds the newly ready work from one completion;
it does not say that all successors become ready then, that several completions
can be reordered, or that GPU offload pays for its transfer/synchronization cost.
The implementation preserves that distinction. The full-run profile measures
actual readiness; a GPU decision also needs service-order constraints and cost
measurements. No kernel-per-completion design is justified by total trace size.
