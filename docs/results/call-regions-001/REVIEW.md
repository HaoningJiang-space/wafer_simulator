# Complete call ownership before target execution

The frontend now assigns disjoint ownership to supported call subtrees while
retaining every source node and dependency port. This prevents charging a
recognized operator again for its nested implementation. Unsupported parents
remain residual records; they cannot be charged alongside their children until
their decomposition is defined. This is a workload-representation result, not
a simulation speedup or a complete target workload.

Implementation and full processing used commit
`89f66562e338c8480acfefc646ad08a02387a3e5` on eex005. The
[73 semantic tests](tests.log) and [independent complete-source readback](VALIDATED.json)
pass. The input is the entire previously validated 16-rank Chakra effect ledger,
with the accepted matrix-work records joined by rank, original node ID, operator
and byte offset. No prefix or selected training step was used.

| Quantity | Full input / result |
|---|---:|
| Source records, each assigned exactly one owner | 4,530,939 |
| Resulting source regions | 3,598,591 |
| Multi-record regions | 902,748 |
| Internal records assigned to an enclosing owner | 932,348 |
| Original parent references retained | 4,530,939 |
| Original source data-dependency entries retained | 5,258,091 |
| Regions expanded because their quotient introduced a cycle | 0 |

No original record or internal dependency is deleted. Owner and original
endpoints are both retained, including repeated references. Parent root 0 stays
an external call sentinel. Parent edges are not inserted as task dependencies.
Both the original and region data-dependency graphs pass independent acyclicity
checks. The analytical interleaving regression exercises cycle refinement;
this particular full input did not require it.

The [region summary](REGIONS.json) separates supported recipes and residual
source records:

| Region recipe | Count |
|---|---:|
| Same-storage view metadata | 1,117,930 |
| Chain returning the same uninitialized allocation descriptor | 559,511 |
| Previously normalized matrix operator and its device implementation | 123,520 |
| Explicit write operator and its device implementation | 245,552 |
| Residual source record without a complete subtree recipe | 1,552,078 |

These are source-representation counts. In particular, all 123,520 matrix
records retain their shape-based work, but this does not establish that every
record is a distinct executed training operation. CPU compiler/profiling scopes
and sparse GPU-child coverage still require execution-scope interpretation.
The residual count includes wrappers, unsupported operators and unbound device
records; it is not a count of necessarily irreducible target operations.

The implementation separates source-call ownership (`workloads`), independent
readback (`analysis`) and complete-input orchestration (`scripts`). The
[contract](../../CALL_REGIONS.md) explains accepted recipes and why asynchronous
CPU launch/GPU completion ports cannot be replaced by one timed region event.
Allocation generations and exact byte footprints remain unresolved for the
capture. Neither original elapsed time nor source stream order is promoted to
target computation or target scheduling.

The next frontend work is explicit collective input/output roles, communicator
membership and completion conditions, followed by the remaining compiled-scope
and tensor-layout/allocation rules. In particular, a coalesced collective's
output buffers can be input arguments while its returned value is a Work handle;
source IO position alone cannot define data availability. These rules must
preserve original ports before target resource binding or application timing.

## Reproduction evidence

The fixed input identities are in
[`configs/llama16_call_regions.json`](../../../configs/llama16_call_regions.json).
Full owner, region and dependency ledgers (186 MiB) remain at
`/home/wangziheng/wafer_simulator/runs/call-regions-002` on eex005.
`VALIDATED.json` lists their hashes; only compact receipts and reports are in Git.
[STARTED.json](STARTED.json), [ENVIRONMENT.json](ENVIRONMENT.json) and
[SEMANTICS.json](SEMANTICS.json) record the source, interpreter, packages and
test identities. The environment includes the existing NetworkX dependency;
no new external repository was introduced.

The first full invocation stopped while loading matrix records because the
adapter required TE's optional epilogue field on `aten::mm`. The corrected
adapter preserves the two accepted record schemas; its regression is included
in the 73 passing tests. The failed invocation log remains remotely as
`runs/call-regions-001.log`; it has no success marker.

No new BookSim experiment ran. The frozen native binary and combined patch
were rechecked after processing and retain SHA-256
`9807d4a81c07e29bf1f40dec11fbc9dad9f64d66319c6dbdd5103c04b4256255`
and `2e44498b90fd5f06c6ff58a09141d38c6dd1979d477a6d7fcb93118ff9f40344`,
respectively. M0/M1 application results remain the previously accepted
conditional replay results.
