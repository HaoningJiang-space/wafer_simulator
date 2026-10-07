# Call ownership before spatial execution

The full Chakra capture contains CPU dispatcher calls, their nested calls and
GPU implementation records. Summing all their effects would count some work
more than once. Selecting CPU leaves instead loses the semantics of operators
whose children are implementation details. The frontend therefore gives every
source record one owner while preserving the original call and dependency ports.

`workloads/call_regions.py` selects only complete subtrees supported by four
limited recipes:

* Views whose descendants are views on the same set of source storages. All
  intermediate view identities remain available in the source ledger.
* An uninitialized-allocation chain with exactly the same output descriptor.
  Multiple allocation siblings are not folded into one allocation.
* A previously normalized dense matrix call with only GPU implementation
  descendants. Its work references the accepted shape-based matrix record.
* An explicitly supported copy/fill/elementwise write with only GPU
  implementation descendants. This establishes ownership, not target service cost.

Unknown children, storage rebindings, compiler scopes and communication are not
silently absorbed. A parent without a complete recipe remains a residual source
record, alongside separately recognized children. That parent must not be
charged together with the children until a decomposition recipe exists. Meta
matrix calls and GPU collective children are not accepted as matrix execution.

Parent links describe call nesting. Source data dependencies describe the
converter's ordering, which includes more than tensor producer/consumer edges.
Neither becomes target scheduling order automatically. Every entry, including
duplicate dependency references, is emitted with its original node endpoints,
ordinal and owner endpoints. Internal references are retained. Root parent 0
is an explicit external sentinel, never an implicitly completed data dependency.

Some source work can interleave with a call's implementation. Contracting that
subtree can create a cycle in the region dependency graph even when the source
graph is acyclic. Regions in cyclic strongly connected components are expanded
to their original records. Downstream acyclic regions remain intact. This is
conservative source representation, not a new simulation or scheduling algorithm.
An acyclic region graph also does not justify replacing asynchronous CPU launch
and GPU completion with one timed event; their original ports remain necessary.

`workloads/chakra_regions.py` serializes ownership, region records and all original
edges. `analysis/call_regions.py` independently checks identities, complete
subtrees, recipes and exact edge multiplicities, using a separate Kahn graph
check. `scripts/lower_call_regions_remote.py` orchestrates the complete 16-rank
input pinned by `configs/llama16_call_regions.json`. No workload prefix is used.

The result is an intermediate source representation. Allocation generations,
strides, remaining operator semantics, communication completion and target
resource costs are still needed. `VALIDATED.json` certifies source ownership and
dependency preservation, not completion of a target application. No new BookSim
run or native-wafer performance claim is part of this milestone.
