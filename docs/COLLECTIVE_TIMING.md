# Timed collective actions

Transformer AllReduce is an explicit logical collective, not a generic
multi-output compute operation. The old generic lowering wrote one root-local
copy per output before forwarding it, charging an extra result write and an
extra local output allocation. The corrected root-gather/SUM/broadcast policy
materializes one root result and writes replicas only at their destinations.

`workloads/spatial.py` checks participant counts, input/output bytes and reduction
work against the logical operation. `adapters/collective_operation.py` reuses
`bind_collective` from `adapters/collectives.py`, maps its input/output identities
to immutable spatial objects, and exposes its action dependencies as an
`OperationPlan`. No second collective algorithm is implemented.

The target executor submits every ready action to the same compute/memory
calendar or persistent BookSim client. Each source read precedes its transfer;
all flits precede the destination write; the corresponding root operand read
precedes reduction; the single result write precedes broadcast reads. Independent
gathers can overlap. Root memory accesses still serialize on the declared port;
concurrency does not give each action a private bandwidth supply.

All participant inputs and atomic output/staging reservations are required at
entry. Each rank output now becomes visible after its own final write; data
consumers may proceed before collective retirement. Explicit control dependencies
still wait for retirement. Inputs, staging and producer-owned output reservations
remain pinned through retirement and outputs also outlive their consumers. This
retains internal broadcast safety. There is no rank-local early entry or streaming.
The older global publication policy is available as `global_retirement` for a
controlled comparison. See [rank-local semantics and resource balance](RANK_LOCAL_BALANCE.md).

The independent timing audit checks action identity/dependencies, every service,
whole-operation completion, resource sharing and storage lifetime. Critical-chain
reconstruction uses action-DAG joins rather than a serial list. Sequential
ordinary operations retain their previous event semantics.

## Acceptance and controlled extension

1. Semantic cases check one root result write, unchanged reduction work, a
   hand-derived 25-cycle two-rank collective, concurrent gathers, shared finite
   storage, malformed dependencies and destination-write completion. Native
   concurrent collective requests must also match standalone BookSim timestamps.
2. Re-run the original four-head TP2 block. Preserve the old 13,062/13,430 result
   as historical evidence with a correction notice. `--serial-control` runs the
   same corrected actions in topological serial order, separately measuring the
   result-write correction and the benefit of independent-action overlap.
3. Only after these pass, `--study` runs the predeclared eight-head block in
   `configs/transformer_collective_study.json`: TP4/TP8, Baseline/Rotated, and
   row-major/nearest-root. Eight cases total; no mapping search. TP8 cannot use
   the original four-head whole-head partition, so this is explicitly a distinct
   workload registration. Within each TP all four cases share logical work;
   different TP degrees retain the declared replicated normalization work and
   collective algorithm, and are not asserted to have equal aggregate work.

`nearest_root` anchors the first row-major compute endpoint, then takes nearest
planar positions, with fixed coordinate/ID ties. It uses geometry, never measured
performance. Both mapping rules apply unchanged to both placements. Rates,
capacity, seed, network widths, collective algorithm and routing remain fixed.
These are analytical local-resource assumptions and original unmatched-cost
WoW designs, not calibrated hardware or a general topology ranking.

Run on eex005 after a clean commit (add `--global-completion-control` to reproduce
the historical publication policy used in the original twelve arms):

```bash
export PYTHONPATH="$PWD/src"
ROOT=/home/wangziheng/wafer_simulator
"$ROOT/.venv/bin/python" scripts/test_wow_target_remote.py "$ROOT/runs/collective-tests-NEW"
"$ROOT/.venv/bin/python" scripts/run_transformer_wow_remote.py \
  "$ROOT/runs/collective-tp2-NEW" "$ROOT/runs/collective-tests-NEW/SEMANTICS.json"
"$ROOT/.venv/bin/python" scripts/run_transformer_wow_remote.py \
  "$ROOT/runs/collective-serial-NEW" "$ROOT/runs/collective-tests-NEW/SEMANTICS.json" --serial-control
"$ROOT/.venv/bin/python" scripts/run_transformer_wow_remote.py \
  "$ROOT/runs/collective-study-NEW" "$ROOT/runs/collective-tests-NEW/SEMANTICS.json" --study
```

Every directory is fresh. Source, environment, native binary and input hashes
are recorded. A completion marker requires both placements for every registered
case, independent execution readback, and exact native interface comparison.
