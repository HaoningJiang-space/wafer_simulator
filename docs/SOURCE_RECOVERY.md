# Source recovery and conversion repair

The accepted 16-rank Chakra capture lacks some information needed to bind a
target workload. Two separate mechanisms are involved: the source must record
the facts, and conversion must preserve them. Target execution cannot restore
facts absent from both stages by interpreting elapsed time or call order.

## Changes to the maintained frontend

`workloads/collective_recovery.py` recomputes communicator matches and produces
per-call recipes. Matched barriers bind an empty tensor contract. Singleton
broadcast and known SUM allreduce on the same tensor argument forward an
existing value; they do not write a new version or allocate/copy another output.
Ordinary calls retain explicit missing evidence. Their source ports, dependency
edges, GPU implementation and waits remain in the recovered ledger.

The previous singleton reduction assumption was too broad: the pinned
`ProcessGroupNCCL.cpp` supports PREMUL_SUM, which can scale input even at group
size one. The matcher and logical model now require known SUM for reductions.
Opaque singletons remain unresolved. The pinned Chakra BROADCAST enum is 5;
the frontend's previous value 3 is corrected independently of the source data.

## Preserve layouts before conversion loses them

The pinned observer records nested input/output strides. Chakra's IOInfo has
only values, shapes and types, and the pinned converter does not copy strides.
`patches/chakra-preserve-layout.patch` adds optional JSON string attributes:

- `wafer.inputs.strides.v1`
- `wafer.outputs.strides.v1`

Their nesting is exactly the original IO argument nesting. Missing source
strides produce no attribute; no contiguous default is generated. The patch
changes no original IO field, dependency, name, duration or existing attribute.
It applies to the pinned author source under `third_party/chakra` in an isolated
copy, never in place. `scripts/verify_chakra_layout_remote.py` tests the actual
patched converter against the unmodified converter on eex005, including a real
protobuf serialization round trip.

`workloads/chakra_layout.py` decodes these attributes and computes exact byte
spans from shape, element stride, element size and storage offset. Holes,
scalars and zero-stride views are explicit. `access_from_layout` binds these
spans only to a caller-proved live storage generation, checking identity and
capacity. It does not initialize data, infer an allocation epoch, or determine
ordering. `analysis/chakra_effects.py` preserves optional layouts in future
effect ledgers and rejects malformed present metadata. Old captures remain
unchanged and layout-unknown.

## The remaining source boundary

The pinned PyTorch reference has parameter recording in ordinary collectives
and allreduce_coalesced, but not in allgather_into_tensor_coalesced or
reduce_scatter_tensor_coalesced. This is a source explanation consistent with
the missing group/sequence records, not proof of the unpublished capture's
exact PyTorch build. ProcessGroup and ReduceOp appear as opaque Objects in this
capture. Tensor byte ratios and matching call ordinals cannot identify them.

To resolve those calls, obtain the same capture's pre-conversion host/linked
ET and device trace with communication identity, or make a separately identified
capture that records ordered group membership, group sequence, ReduceOp and
source argument layout. Preserve the host and linked JSON before conversion;
the author's `et_to_chakra.sh -r` removes linked JSON. Allocation generations,
mutations and producer/consumer ordering need their own evidence as well.

The public directory inspected from eex005 exposes the 16 converted `.et` files;
the GOAL/Nsight directory is a different source and does not establish same-
capture identity. No data from those two sources is silently merged. A new
capture would be a new input baseline, not a repaired copy of the old one.

These repairs establish semantic bindings and prevent layout loss on future
conversions. They do not claim full native wafer execution, calibrated target
compute or memory time, or a new Baseline–Rotated performance result.
