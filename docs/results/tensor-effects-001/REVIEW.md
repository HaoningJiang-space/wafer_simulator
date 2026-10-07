# Tensor values and full-source effects, 2026-10-07

This milestone implements data-value versioning and identifies the source-call
semantics needed before a complete spatial workload can be lowered. It adds no
source-duration scaling, target application result or new placement experiment.

The [value model](../../TENSOR_VERSIONS.md) now distinguishes live allocation
generations from immutable contents. Exact views share storage, partial writes
change only affected bytes, and uninitialized or invalidated reads fail. The
effect binder resolves inputs before writes; copy overwrites and accumulation
read-modify-write have different dependencies. It requires explicit allocation
and footprint bindings and does not reconstruct missing layout or order.

## Full-source observations

All sixteen files were processed and independently compared with their output
ledgers. These are source-record counts, not execution time, target memory
capacity, kernel invocations or amounts of physical traffic.

| Observation | Count |
| --- | ---: |
| All retained nodes | 4,530,939 |
| All retained source control references | 4,530,939 |
| All retained source data-dependency entries | 5,258,091 |
| CPU-side calls | 4,426,751 |
| Calls classified as alias/view | 1,991,776 |
| Calls classified as uninitialized allocation | 668,137 |
| Calls with explicit write rules | 484,177 |
| Calls containing meta-device tensors | 32,624 |
| Distinct `(rank, tensor_id)` identities | 474,755 |
| Such identities observed at multiple `(storage_id, device)` locations | 228,120 |

The last two rows sum the per-rank fields in [EFFECTS.json](EFFECTS.json). They
show why a tensor ID cannot be used as an immutable data-object identity. They
do not distinguish object-pointer reuse from explicit storage rebinding.

Call hierarchy matters too: 1,947,908 CPU-side calls have CPU children, and
2,478,843 are CPU leaves. Counting both a parent and its implementation would
duplicate logical work/effects. Selecting all leaves is also insufficient:
292,218 leaves are unresolved, 98,592 have only a functional schema, 19,792
rebind storage, 1,152 declare mutations without a resolved write extent and
576 have unsupported descriptors/rules. These categories are retained, not
discarded. An unresolved child can sometimes be explained by a supported
parent; coverage must therefore be decided on call subtrees, not names alone.

## What this resolves, and what remains

The implementation now represents the value dependencies required by slices,
copies and in-place updates, without treating views as fresh data or allocations
as initialized values. Source inspection also separates metadata and device
implementation records from candidate logical operators.

The complete capture has **not** been converted into a runnable spatial DAG.
Source-call extraction deliberately leaves `allocation_epochs_resolved=false`
and `exact_footprints_resolved=false`; the version engine is applied only when
those bindings are explicit. Parent/child selection, layout recovery, allocation
boundaries, compiled/fused work and collective completion semantics remain.
Captured source order is retained as evidence, not declared target scheduling.

The next concrete frontend work is a disjoint call-subtree lowering: choose a
supported parent or its supported implementation children, preserve every
uncovered subtree, and carry data versions and completion dependencies across
the selected boundaries. The full
[leaf inventory](cpu_leaf_effects.csv) locates compiled-call and communication
cases. In particular, `CompiledFunctionBackward`, `CompiledFunction`,
`Torch-Compiled Region`, the coalesced NCCL calls and captured Triton calls need
explicit semantics; names alone cannot supply work or mutation extents.
No fixed timing is substituted to declare those cases complete.

## Validation and reproducibility

[SEMANTICS.json](SEMANTICS.json) and [tests.log](tests.log) record **53 passing
tests on eex005** at `8891ad6`: 18 tensor-effect/version tests, 15 existing Chakra
tests and 20 spatial-contract tests. An independent byte-array oracle checks
200 partial overwrites. The binder tests cover copy → view → accumulation,
undefined reads, rank separation and preservation of destination bindings.
The receipt includes Python, source/test hashes and the unchanged 006 native
binary and patch hashes.

[VALIDATION.json](VALIDATION.json) checks every ledger node against the raw
source: identity, byte offset, name, domain, both dependency lists and tensor
descriptors. It also checks role references, alias storage identity, allocation
versus initialized write, GEMM old-destination reads and workspace separation.
Extraction used `a67ce3d`, full readback used `981091b`; the later `8891ad6`
change strengthens explicit binding validation without changing extraction.
The older readback receipt names its original 52-test log; SEMANTICS.json is
the current 53-test acceptance. These checks validate declared software
semantics, not physical service calibration.

Raw inputs remain in `downloads/atlahs/llama16-chakra` under the eex005 project
root. Full compressed ledgers remain in `runs/tensor-effects-001` (about
282 MiB); readback outputs are in `runs/tensor-effects-validation-001` and
semantic checks in `runs/tensor-semantics-003`.
[EXTRACTED.json](EXTRACTED.json) records the remote artifact hashes. Only compact
results are delivered here. There were zero new BookSim/application simulations.
