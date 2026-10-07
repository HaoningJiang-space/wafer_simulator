# Collective recovery and layout preservation

The blanket tensor-evidence requirement is replaced by per-call recovery.
The full read-only join at `3e1dd69` retains **all 33,632 source collective calls**,
their dependency ports, GPU implementations and waits. It compares every saved
source-port record against the accepted input after writing. See
[SUMMARY.json](SUMMARY.json), [STARTED.json](STARTED.json) and
[VALIDATED.json](VALIDATED.json) for counts, input hashes and output hashes.

| Recovery result | Calls | Meaning |
|---|---:|---|
| Bound without tensor payload | 320 | 20 explicitly matched barrier instances; rendezvous semantics, no calibrated control latency |
| Forward existing input | 1,600 | Singleton broadcasts; recipe is known, upstream value binding still required |
| Supported payload collective | 416 | 20 allgathers and six SUM allreduces across 16 ranks; exact accesses/producers still needed |
| Unresolved collective | 31,296 | 29,792 missing communicator/sequence calls plus 1,504 calls with unresolved reduction operators |

These categories partition the original call set. Missing-evidence counters
overlap and must not be added to count calls. Only the 320 barrier participation
records have completed tensor binding; no payload-bearing capture call is
reported as fully version-bound. Matching still yields 2,790 instances, of which
1,646 currently have supported logical semantics.

The supported count decreased from the earlier snapshot because 1,120 singleton
allreduces no longer assume an opaque ReduceOp is an identity. PREMUL_SUM in the
pinned source can scale data at group size one. The earlier 24 unresolved
multi-rank reduction instances remain unresolved. This is a correction to the
semantic coverage claim, not lost source work.

## Execution fixes and validation

An explicitly proved singleton broadcast or SUM allreduce on the same tensor
argument retains its input version. It creates no new writer, output allocation
or memory-copy action. Entry still requires ready data; the output hold precedes
input-consumer retirement, and the allocation survives for later consumers.
Operation dependencies still gate downstream work even if the input value was
already ready. Multi-rank and mutating operations retain their normal completion
and storage rules.

[137 semantic tests](tests.log) passed at `dd6c3cf`, recorded in
[SEMANTICS.json](SEMANTICS.json). The earlier 132-test receipt for `3e1dd69` gates
the full recovery join and remains on the server, with its hash in STARTED.json.
Coverage includes barrier rendezvous, missing/ambiguous identity, opaque
singletons, source preservation, ready-data versus completed-operation state,
forwarding lifetime, capacity failure, stale storage generations and exact
noncontiguous byte footprints.

The [Chakra conversion patch](../../../patches/chakra-preserve-layout.patch)
preserves nested source strides in optional protobuf attributes. Four
[actual-converter tests](converter/tests.log) passed at `6ced60b`
([receipt](converter/VALIDATED.json)): legacy output is byte-identical;
existing fields are unchanged; serialization preserves noncontiguous layout;
malformed supplied metadata is rejected by the reader. The first isolated test
attempt lacked the generated storage schema import; the harness was repaired
before this passing validation. No pinned author file was edited.

Explicit strides now feed exact source footprints and checked access bindings.
They do not establish allocation lifetime, producer identity or access ordering.
The old converted capture contains no such new metadata and is unchanged.

## Source availability and remaining work

The [server-side availability receipt](AVAILABILITY.json) records the published
directory returning HTTP 200 and five author-convention rank-0 host/device/
linked/profiler JSON paths returning HTTP 404. This bounded probe does not prove
the files are unavailable everywhere. No source capture was downloaded locally.

The remaining 29,792 communicator/sequence identities cannot be reconstructed
reliably from the available fields. Resolving them requires same-capture
pre-conversion evidence with those identities, or a separately identified new
capture that records them. Unresolved ReduceOps and input producer/lifetime
evidence also remain necessary. The conversion patch prevents future stride
loss; it does not retroactively restore missing fields.

Full recovery artifacts stay under
`/home/wangziheng/wafer_simulator/runs/collective-recovery-001` (4.8 MiB).
The isolated converter check is in `runs/chakra-layout-patch-002` (2.0 MiB).
No new application, mapping or smoke simulation ran. Frozen BookSim006 binary
SHA-256 remains `9807d4a81c07e29bf1f40dec11fbc9dad9f64d66319c6dbdd5103c04b4256255`;
its patch SHA-256 remains `2e44498b90fd5f06c6ff58a09141d38c6dd1979d477a6d7fcb93118ff9f40344`.
There is no new application performance, native wafer timing or thermal claim.
