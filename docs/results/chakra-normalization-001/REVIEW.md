# Complete source read and partial logical-work recovery

Checked on eex005, 2026-10-07. All 16 published Chakra rank files were read;
no source prefix, reduced model or new BookSim experiment was used. The
normalizer recovers mathematical work and logical operand bytes from supported
operators. It does not yet produce a complete executable spatial workload.

| Observation | Checked value |
| --- | ---: |
| Complete rank files | 16 |
| Input bytes | 2,189,722,129 |
| Source nodes | 4,530,939 |
| Recovered matrix primitives | 123,520 |
| `tex_ts::te_gemm_ts` / `aten::mm` | 122,880 / 640 |
| Dense MACs across these recorded primitives | 25,808,286,682,972,160 |
| Additional accumulation adds | 1,968,705,634,304 |
| Matrix primitives with a directly linked GPU child | 24,704 |
| Semantic tests passed | 15 |

These are full-file inventory totals, not work per training step or measured
GPU utilization. The CPU dispatcher records include `ProfilerStep#1` through
`#10`; 82,240 matrix records have no step reachable through their control-parent
chain. Only 20% of normalized matrix records have a direct GPU child. Source
logical scope and linked device-event coverage must be reconciled before
defining a complete training execution window. No missing scope is silently
assigned to a step or deleted.

## What is implemented

- `workloads/chakra.py` reads official protobuf records with strict framing,
  preserves offsets and distinguishes clean EOF from a truncated record.
- `analysis/chakra_source.py` inventories every source node and preserves
  control-parent hierarchy separately from execution/data dependencies.
- `workloads/chakra_work.py` recovers rank-scoped tensor/storage references,
  shapes, element sizes, matrix work and logical operand bytes. Source duration
  remains an annotation; it is never converted to a work amount.
- Dense TransformerEngine GEMM uses its 22-argument ABI and the pinned author
  GEMM implementation to interpret transposes and destination accumulation.
  Accumulation retains an old-destination input and additional scalar adds.
  Source GPU workspace is not charged as target wafer scratch space.

The TransformerEngine reference revision is `e5edd6c`; the capture's exact
library build is not established. Unsupported fused/FP8 forms are rejected,
not treated as dense GEMM. No TransformerEngine kernels were installed or run.
The official Chakra schema/reader revision is `9ff3e3e`. Both sources are
delivered in [the main repository](../../EXTERNAL_SOURCES.md).

## Validation and evidence boundary

The [validation receipt](VALIDATION.json) independently decodes all 16 files
using the official reader and compares node counts and consumed bytes. It also
checks the entire normalized ledger, using operand element counts to verify
MAC conservation independently of the normalizer's transpose formulas. Input,
schema, source, environment and artifact identities are in
[SOURCE_SUPPORT.json](SOURCE_SUPPORT.json) and [DECODED.json](DECODED.json).
[The test log](tests.log) covers framing failures, tensor references, matrix
dimensions, transpose conventions, accumulation and unsupported signatures.

All source data-dependency graphs are closed and acyclic. Each rank retains an
unresolved control parent `0`; control hierarchy is not promoted to execution
dependencies. Closure alone does not establish target-independent semantics:
the source converter also uses ordering/synchronization information when
constructing dependencies.

The public files share the `Llama7B_N4_GPU16_TP1_PP1_DP16_BS32` configuration
label with the earlier source. Their collective counts differ: this set has
3,200 AllGather, 160 AllReduce and 3,136 ReduceScatter device events, whereas
the accepted GOAL-source inventory has 19,216, 1,200 and 18,816 respectively,
plus 16 Broadcast events. This is not an established same-capture replacement
for M0/M1. Their completion times must not be compared as a model-only change.

## Remaining work and reproduction

The next input-model work is tensor version/alias resolution, remaining
operator and collective semantics, and a complete declared execution scope.
Raw tensor IDs and addresses do not yet define immutable objects or their
lifetimes. Target compute/memory service parameters and timed shared-resource
execution remain separate work after this input is supported. There is no new
wafer application time in this milestone.

Raw files stay in `/home/wangziheng/wafer_simulator/downloads/atlahs/llama16-chakra`.
Full source inventories and the detailed work ledger stay in
`/home/wangziheng/wafer_simulator/runs/chakra-source-003`. Independent validation
is in `runs/chakra-source-validation-001`. The earlier interrupted inventory
has no completion marker; `003` is the accepted full-file result.

For reproduction on eex005, first restore bundled sources and set up the
pinned schema environment with `scripts/setup_chakra_remote.sh`. Run
`scripts/inspect_chakra_remote.py` with `PYTHONPATH=src`, the schema environment's
Python and a fresh absolute output directory. Run the 15 Chakra unit tests,
then pass the inventory directory, another fresh output directory and test log
to `scripts/validate_chakra_remote.py`. The recorded normalization commit is
`9781d2b`; independent full validation used `69c0cd6`.
