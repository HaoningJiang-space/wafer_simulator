# S cost profile before behavior-preserving acceleration

Native advancement and detailed evidence both cost time. Within the timed
native Step sections, remaining BookSim work accounts for about 53–56%, and
adapter channel/flit recording for 44–47%. Python JSON and independent audit
are also significant. This supports first examining redundant evidence and
serialization work while retaining S's service rules. It does not establish
that all cost is logging, that IPC dominates, or that suppressing logs alone
would yield a tenfold speedup.

No lightweight mode or event-compressed backend is implemented in this round.
S remains the detailed reference for the declared machine; D0 and D1 remain
comparisons. Hardware representativeness is a separate question.

## Controlled observations and equivalence

On hn072, fixed **6×6 B and 7×7 B** v1 whole-object inputs each run once with
Python `cProfile` and once with a cost-instrumented native binary: four
controlled profiling executions. Workers inherit the original CPU affinity
`[18,19]` before their imports. All four **complete execution objects and native
protocol logs are byte/identity exact** against the accepted unprofiled S runs,
including messages/flits, services, capacity, publication and makespan. Each
worker runs the original independent S audit. No bandwidth, route, arbitration,
bank, notification or execution policy changes.

[CHECKED](CHECKED.json) authenticates 62 profile artifacts and all four saved
execution/protocol readbacks against the published D1 reference manifest.
The [negative checks](NEGATIVE_CHECKS.json) reject a changed Step count and an
early output timestamp. They are two audit fault injections, not two more
applications. D1's 256-regression receipt belongs to its own `385426a` source;
it is not relabeled as a same-source profile test count.

Profile source is `5b774cc`; isolated native build source is `0c9c0af`; final
compact readback source is `80e3687`. Source/build/binary/config/environment and
result identities are in [STARTED](STARTED.json), [ENVIRONMENT](ENVIRONMENT.json),
[BUILD_MANIFEST](BUILD_MANIFEST.sha256) and [RUN_COMPLETE](RUN_COMPLETE.json).
The accepted binary remains
`d37fc5551d90adb03f2595f9e23ef0199b39be3a572f315ef154bad172d93beb`.
The cost-only binary is
`b9b5bb0d05db0833a351b34f69191fced18641eaa10590e01be8f666c0ae3848`.
Its different identity is retained, not normalized or disguised as the old
binary. Exact event/protocol checks establish equivalence on these two inputs.

The build copies pinned ordinary `third_party` source into an isolated server
directory, applies the unchanged `booksim-wafer.patch`, and instruments only a
copy of the project's online wrapper using
[online-booksim-cost-profile.patch](../../../patches/online-booksim-cost-profile.patch).
No in-place third-party or accepted binary edits. The migration retained binary
products, not objects; the isolated build therefore regenerates objects. Missing
flex/bison were unpacked from Ubuntu packages under project `deps`, without
changing system settings or installing system packages. Their bytes are in
[PARSER_TOOLS](PARSER_TOOLS.sha256). `perf_event_paranoid=4` disallows hardware
sampling; no privilege or system-policy change was attempted.

There are also **five exploratory profiling executions**: one Python pilot and
the first four-run batch with the broader CPU set. All have exact events and
protocols; their raw records remain on the server and are excluded from the
controlled figures below. No accepted raw artifact is overwritten. The first
incomplete build and the successful isolated build are separate directories.

## Unprofiled baseline costs

These are medians of the three fresh workers already measured in the
[registered D1 study](../shared-spatial-service-001/REVIEW.md), at the same two
input/CPU settings. No profiled sample is used as a speed benchmark.

| Wall seconds | 6×6 B | 7×7 B |
|---|---:|---:|
| Complete fresh worker | 10.510865 | 16.121864 |
| Graph/binding | 0.035589 | 0.047293 |
| Configuration | 0.373584 | 0.374063 |
| Native initialization | 0.024478 | 0.024274 |
| Execution, including synchronous native requests | 5.442964 | 9.080965 |
| Network close and network JSON output | 1.308487 | 2.023816 |
| Execution JSON output | 0.655674 | 0.950447 |
| Worker independent audit | 1.710690 | 2.178305 |

Phase medians need not sum to the whole-worker median. Imports, final hashes and
metadata also occur outside the named phases. The detailed output is intentional
validation work, not pure solver cost. Child CPU is recorded separately in the
underlying study, and is not added to synchronous waiting wall time.

## Native service versus recording

Each following number is one instrumented elapsed section, not exclusive CPU
and not an unprofiled baseline measurement. All active native cycles still
execute once. The retirement-record timer excludes the call to the author
`TrafficManager::_RetireFlit`; it times adapter JSON/path-record construction.
The `_Step` timer includes that callback; subtracting the callback avoids
double counting in the first row.

| Instrumented section, seconds | 6×6 B | 7×7 B |
|---|---:|---:|
| BookSim `_Step`, excluding adapter retirement records | 1.740938 | 3.270102 |
| Adapter channel observation/path records | 0.659278 | 1.175047 |
| Adapter retired-flit/message records | 0.905674 | 1.423763 |
| Native request JSON parse | 0.003044 | 0.004824 |
| Native reply JSON dump | 0.196626 | 0.279611 |
| Reply write/flush, potentially blocked by consumer | 0.180483 | 0.202346 |
| Active native Steps | 22,103 | 26,886 |
| Recorded flits | 92,525 | 125,844 |
| Timed reply bytes, excluding initial hello | 36,132,656 | 51,960,728 |

The 53–56% / 44–47% comparison uses only `_Step` plus channel observation;
it is not a share of total application or process time. Remaining `_Step` work
still includes native statistics, allocation and retirement; it does not isolate
router arbitration alone. Initialization, reply construction/copies, destruction
and other sections are not exhaustively partitioned. Writes can overlap the
Python consumer and contain blocking; cross-process numbers must not be summed
as disjoint wall-time contributions.

## Python interface, JSON and audit

The profiler covers worker function execution after initial driver imports.
Self/cumulative times include waiting and nested calls. Values below are from
the original accepted binary, not the cost-only binary.

| Python observation, seconds | 6×6 B | 7×7 B |
|---|---:|---:|
| `select.select` self time | 3.920408 | 6.348580 |
| `_receive` cumulative | 5.053025 | 8.117086 |
| JSON encoder `iterencode` self | 1.758700 | 2.759170 |
| JSON decoder `raw_decode` self | 0.526090 | 0.939454 |
| `write_json` cumulative | 1.239215 | 1.878441 |
| `object_digest` cumulative | 0.496805 | 0.846795 |
| Worker audit phase wall, with profiling overhead | 2.457150 | 3.978934 |
| `audit_messages` calls / cumulative | 2 / 1.446350 | 2 / 2.335375 |

`_receive` contains JSON decode/re-encode and waiting. `select.select` largely
waits for native computation/output; calling all of it Python↔C++ transport
overhead would be wrong. `write_json` and `object_digest` include encoder work,
so these rows overlap. Audit subroutines also nest; their cumulative times are
not additive. Two message-audit traversals are observed in the current acceptance
path; removing one requires maintaining the independent checks it provides.
[SUMMARY](SUMMARY.json) includes top self-time functions and selected call counts;
full function tables and profiler dumps stay on hn072.

The original profile launch field named `process_wall_seconds` included parent
evidence readback. Original receipts remain untouched. The compact readback
explicitly renames it `launch_including_parent_readback_seconds`; missing
worker-only wall samples are **not reconstructed**. Later launcher code stops
worker timing before readback. Neither value enters a speedup claim; the
unprofiled complete-worker benchmark above is unaffected.

## Decision and next boundary

The first optimization candidate should be the **evidence path**: repeated
detailed JSON materialization, protocol duplication, close/result serialization
and overlapping audit traversals. Measure a concrete change while retaining
required full evidence in validation runs; a lightweight mode must separately
prove the same message completions, operation services, output readiness,
capacity behavior and application result. This profile does not certify an
unimplemented compact audit or a buffer capacity it does not observe.

Native advancement remains substantial after identifying recording cost. If
recording improvements do not meet a declared scale/cost requirement, investigate
compression of repeated local service computation while preserving arbitration,
queues, credits and all boundaries that can change future service. Current
timers do not identify safe skip intervals. No congestion coefficient, fairness
weight, effective-rate adjustment or new queue/credit approximation is proposed.

This is a bounded two-input cost diagnosis under v1, not new hardware evidence
or general profiling of all layouts/policies. The
[necessary-information framework](../../NECESSARY_INFORMATION.md) distinguishes
the solver experiment from machine/policy fidelity. Both whole and ideal pipeline
remain declared contracts, with unprovided controller-wide DMA/RX budgets.

## Reproduction

Use the user-scoped flex/bison tools and JSON headers on hn072. The build script
requires a fresh isolated build directory. Current launcher explicitly matches
reference affinity and published manifest identity.

```sh
cd /Projects/haoning/wafer_simulator/source
bash scripts/build_cost_profile_remote.sh \
  /Projects/haoning/wafer_simulator/build/booksim-cost-profile-NEW
env PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.profile_native_service \
  --output /Projects/haoning/wafer_simulator/runs/s-native-profile-NEW \
  --binary /Projects/haoning/wafer_simulator/build/booksim-cost-profile-NEW/online_booksim
```

Raw controlled root: `runs/s-native-profile-002`; compact checked readback:
`runs/s-native-profile-analysis-002`; isolated build:
`build/booksim-cost-profile-002`. Original profile/source receipts pin their
versions; current launcher additionally separates its worker/readback timer.
Compact published byte copies are verified against those roots. Large traces,
profiles, JSON tables and all failed/exploratory records remain server-only.
