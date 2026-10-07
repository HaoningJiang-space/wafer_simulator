# Tensor effects and byte-region values

Collective integration now uses the same byte-version model. See
[source-port binding and runtime lifetimes](COLLECTIVES.md#source-ports-to-resident-versions)
for the boundary between assigning a producer version and publishing ready
target data. The [complete source join](results/collective-values-001/REVIEW.md)
retains unresolved allocation/layout evidence explicitly.

The workload frontend must distinguish a tensor reference, a live allocation,
and an immutable value. The same recorded tensor ID can refer to several
storages; multiple tensor views can refer to one allocation; a partial in-place
write changes only some of its contents. Neither an ID nor a storage address is
a logical data version.

`workloads/tensor_versions.py` implements explicit allocation generations,
exact strided byte footprints and immutable read-version records. A view adds
no allocation or data write. A partial write splits the byte provenance while
leaving the untouched bytes associated with their original producer. Allocation
starts uninitialized unless initial data is explicitly declared. An unresolved
write invalidates affected provenance; a later read fails instead of retaining
an obsolete producer. Reuse of a source allocation identity advances its
generation and rejects stale aliases. Rank and device belong to the identity.

The input contract requires explicit storage sizes, strides, allocation
boundaries and a valid access order. Missing strides do not become contiguous
strides. Exact irregular footprints exceeding the representation limit fail
instead of rounding a view to its bounding box. This module does not infer
source concurrency, choose a target schedule or allocate wafer memory. Values
are a precursor to the immutable spatial workload; the full capture is not yet
lowered into that workload.

`workloads/tensor_effect_binding.py` connects supported write/view rules to
this value model when exact allocation/span bindings are provided. It resolves
all input versions before a write and rejects missing bindings, cross-rank
identities and unsupported effects. It supplies no captured-tensor layout or
allocation size by default. The copy → view → accumulation regression verifies
that a later read resolves to the correct earlier writer without charging the
view as a second allocation.

`workloads/chakra_effects.py` classifies source call IO into allocations, aliases,
explicit writes, schema-declared potential mutations, functional signatures,
storage rebinding and unresolved calls. Nested tensor lists retain argument
paths. Copy/fill overwrite their destination without an old-value read; GEMM
accumulation reads the old destination, and its workspace stays separate.
Schema annotations alone do not establish full-write extents or tensor-byte
reads. Operator work and byte access remain unresolved for generic signatures.

`analysis/chakra_effects.py` extracts a ledger for every source node, including
GPU implementation records and metadata. It preserves parent and source-order
relations separately. The ledger describes calls; it is not a flattened DAG.
Parent and child effects overlap and must not both be charged. Meta-device
tensors are flagged separately and are not target storage/compute activity.

The exact observer source linked by Chakra is retained in
`third_party/references/pytorch`. Its IDs come from pointer lookup, its offset
comes from `storage_offset()`, and it records strides separately from shapes.
The pinned Chakra conversion copies IO values/shapes/types; its protobuf IO
format has no stride field. The reference does not establish the capture's
build version. A future frontend may reconstruct some layouts from explicit
view arguments, but cannot assume that arbitrary captured tensors are dense.

`tests/test_tensor_versions.py` checks transpose/slice/broadcast footprints,
partial overwrite, allocation reuse, undefined reads, copy versus accumulation,
and nested references. A deterministic independent per-byte oracle checks 200
overwrites. These are semantic tests, not smoke workloads or performance data.

Run full-source extraction on eex005 with `PYTHONPATH=src`, the isolated Chakra
Python environment and `scripts/inspect_tensor_effects_remote.py OUTPUT`, where
OUTPUT is a fresh absolute directory. The entire 16-rank identity from the
accepted source inventory is required. `EXTRACTED.json` means complete source
extraction only; it does not mean a complete target execution or application.

The [full-source result and validation](results/tensor-effects-001/REVIEW.md)
record all 4,530,939 nodes and 53 semantic tests. Full ledgers stay on eex005;
the repository contains compact checked results and artifact hashes.
