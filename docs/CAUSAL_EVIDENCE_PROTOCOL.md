# R2.2: evidence consumers independent of exact state transitions

The [accepted receipt](results/causal-evidence-001/REVIEW.md) covers the seven
frozen cases and three modes. Preserve G1, the AST G2.1
prototype, accepted records and all machine/transaction controls. No Native or
application run. Full stays the default, with the original result schema.

The exact transition updates MessageProgress and event counts before notifying
its consumer. Full constructs legacy event tables. Counters constructs no event
rows and returns an explicitly limited completion summary. Compact writes raw
stream segments; schema 1 reserves affine repeat segments for the later macro
migration. The decoder in analysis has no producer or solver imports.

R2.2 leaves source deques and eager packet metadata unchanged. Path/timestamp
metadata in that existing packet state remains allocated in every mode; sink
separation alone is not a claim of constant memory or counters-only packet state.

Run the same seven frozen G1 demands independently in all three modes. Compare
every default snapshot and seven-field semantic progress boundary, including
final reverse-credit drain. Compare Full prediction bytes with archived R1;
independently expand the persisted Compact record and require complete event
equality. Derive expected completion/counters from original full events, rather
than using the candidate's summary as its own oracle. Counters cannot supply a
full flit audit or reconstructable record. Inject changed/missing/duplicate
records and ensure the decoder/comparator rejects them.

Use clean main, same-source remote tests, fresh directories and source/input/
interpreter/environment/result identities. Keep full records on hn072. Re-read
stored candidates and ledgers without replacing them with fresh predictions.

```bash
cd /Projects/haoning/wafer_simulator/source
PYTHONPATH=src ../.venv/bin/python scripts/test_causal_evidence_remote.py \
  /Projects/haoning/wafer_simulator/runs/causal-evidence-tests-NEW
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.experiments.causal_evidence \
  /Projects/haoning/wafer_simulator/runs/causal-evidence-NEW \
  --r1 /Projects/haoning/wafer_simulator/runs/causal-transition-002 \
  --tests /Projects/haoning/wafer_simulator/runs/causal-evidence-tests-NEW/TESTS.json
PYTHONPATH=src ../.venv/bin/python -m wafer_sim.analysis.causal_evidence_study \
  /Projects/haoning/wafer_simulator/runs/causal-evidence-NEW \
  /Projects/haoning/wafer_simulator/runs/causal-evidence-readback-NEW
```
