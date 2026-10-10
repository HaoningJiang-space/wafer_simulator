"""Compression opportunity diagnostics must not mutate or weaken causal state."""
from copy import deepcopy
from pathlib import Path
import unittest
from wafer_sim.io import read_json,object_digest
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.analysis.causal_compressibility import observe,encoded,intervals_union,audit_patterns

REG=read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')


class CompressibilityAuditTests(unittest.TestCase):
    def test_observation_preserves_all_prediction_and_input_bytes(self):
        contract=deepcopy(REG['contract']);messages=deepcopy(REG['cases'][0]['messages'])
        plain=simulate(contract,messages)
        observed,observer=observe(contract,messages,200000)
        self.assertEqual(object_digest(plain),object_digest(observed))
        self.assertEqual(contract,REG['contract']);self.assertEqual(messages,REG['cases'][0]['messages'])
        self.assertEqual([r['cycle'] for r in observer.rows],list(range(plain['final_cycle'])))

    def test_ownership_credit_and_future_order_remain_distinguishable(self):
        _,observer=observe(REG['contract'],REG['cases'][0]['messages'],200000)
        row=next(r for r in observer.rows if r['kernel']['future'])
        for mutate in (lambda k:k['source_credits'].__setitem__(0,0),
                       lambda k:k['routers'][0].__setitem__('owner',2),
                       lambda k:k['future'][0].__setitem__(0,99)):
            other=deepcopy(row['kernel']);mutate(other)
            self.assertNotEqual(encoded(row['kernel']),encoded(other))

    def test_finite_remaining_work_is_not_claimed_as_equal_full_state(self):
        _,observer=observe(REG['contract'],[dict(source=0,destination=3,flits=128,ready=0)],200000)
        seen={};found=False
        for row in observer.rows:
            key=encoded(row['kernel'])
            if key in seen and row['remaining']!=seen[key]['remaining']:
                found=True
                self.assertNotEqual(encoded([row['kernel'],row['remaining']]),encoded([seen[key]['kernel'],seen[key]['remaining']]))
            seen[key]=row
        self.assertTrue(found)

    def test_intervals_count_overlap_only_once(self):
        self.assertEqual(intervals_union([(0,8),(3,10),(10,11),(14,16)]),[[0,11],[14,16]])

    def test_audit_never_skips_cycles_or_advertises_idle_repetition(self):
        result,observer=observe(REG['contract'],REG['cases'][0]['messages'],200000)
        checked=audit_patterns(result,observer)
        self.assertEqual(checked['skipped_cycles'],0)
        self.assertFalse(checked['compression_implemented'])
        self.assertEqual(checked['processed_cycles'],result['final_cycle'])
        self.assertEqual(checked['observed_covered_cycles'],0)
