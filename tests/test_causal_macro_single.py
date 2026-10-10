"""Exact G2.1 boundary/expansion guards; formal tests run only on hn072."""
from copy import deepcopy
from pathlib import Path
import unittest
from wafer_sim.adapters.causal_macro import run,RangeQueue,expand_record
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.analysis.causal_macro_single import reference_boundaries,check_run,check_checkpoints
from wafer_sim.io import read_json

REG=read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')


class MacroSingleTests(unittest.TestCase):
    def demand(self,n,ready=0):return [dict(source=0,destination=3,flits=n,ready=ready)]
    def test_whole_predictions_match_for_warmup_tail_and_long_flow(self):
        for n in (1,64,127,128,1024):
            with self.subTest(flits=n):
                expected=simulate(REG['contract'],self.demand(n))
                for compress in (False,True):self.assertEqual(run(REG['contract'],self.demand(n),compress=compress).expand(),expected)

    def test_macro_end_state_matches_independent_original_boundary(self):
        candidate=run(REG['contract'],self.demand(1024),checkpoints=True)
        cycles=[r['state']['cycle'] for r in candidate.metrics()['checkpoints']]
        expected,boundaries=reference_boundaries(REG['contract'],self.demand(1024),200000,cycles)
        checked=check_run(candidate,expected,boundaries)
        self.assertGreater(checked['skipped_cycles'],1000)
        self.assertGreater(checked['checkpoints_checked'],0)

    def test_delayed_generation_epoch_is_preserved(self):
        demand=self.demand(1025,37)
        self.assertEqual(run(REG['contract'],demand).expand(),simulate(REG['contract'],demand))

    def test_no_tail_or_final_credit_drain_is_skipped(self):
        candidate=run(REG['contract'],self.demand(2049))
        metric=candidate.metrics();last=metric['batches'][-1]
        self.assertEqual(last['source_remaining_after'],1)
        self.assertLess(last['end'],candidate.compact()['messages'][0]['finish'])
        self.assertGreater(candidate.final_cycle,candidate.compact()['messages'][0]['finish'])
        self.assertEqual(metric['physical_cycle_updates']+metric['skipped_cycles'],candidate.final_cycle)

    def test_timeout_never_returns_complete_even_after_a_macro(self):
        final=simulate(REG['contract'],self.demand(1024))['final_cycle']
        for enabled in (False,True):
            with self.subTest(enabled=enabled),self.assertRaises(TimeoutError):run(REG['contract'],self.demand(1024),final-1,compress=enabled)
        self.assertEqual(run(REG['contract'],self.demand(1024),final).final_cycle,final)

    def test_counters_mode_cannot_impersonate_full_evidence(self):
        candidate=run(REG['contract'],self.demand(1024),evidence='counters')
        with self.assertRaises(ValueError):candidate.expand()
        self.assertGreater(candidate.metrics()['skipped_cycles'],0)

    def test_unsupported_merge_source_or_credit_contract_rejected(self):
        for c,m in [(REG['contract'],self.demand(64)+self.demand(64)),
                    (REG['contract'],[dict(source=1,destination=3,flits=64,ready=0)]),
                    (dict(REG['contract'],capacity_flits=2),self.demand(64))]:
            with self.assertRaises(ValueError):run(c,m)

    def test_mutated_ownership_credit_next_event_and_remaining_are_rejected(self):
        candidate=run(REG['contract'],self.demand(1024),checkpoints=True)
        checkpoints=candidate.metrics()['checkpoints']
        _,boundaries=reference_boundaries(REG['contract'],self.demand(1024),200000,[r['state']['cycle'] for r in checkpoints])
        for mutate in (lambda s:s['kernel']['routers'][0].__setitem__('owner',2),
                       lambda s:s['kernel']['source_credits'].__setitem__(0,32),
                       lambda s:s['kernel']['future'][0].__setitem__(0,999),
                       lambda s:s['remaining'][0].__setitem__(0,0)):
            bad=deepcopy(checkpoints);mutate(bad[-1]['state'])
            with self.assertRaisesRegex(ValueError,'Macro boundary state differs'):check_checkpoints(bad,boundaries)

    def test_range_queue_never_removes_the_tail(self):
        queue=RangeQueue();queue.reset(10,4);queue.skip(3)
        self.assertEqual((queue[0],queue[-1],len(queue)),(13,13,1))
        with self.assertRaises(ValueError):queue.skip(1)

    def test_persisted_templates_expand_without_model_execution(self):
        candidate=run(REG['contract'],self.demand(1024))
        self.assertEqual(expand_record(candidate.record()),simulate(REG['contract'],self.demand(1024)))
        bad=deepcopy(candidate.record())
        segment=next(s for s in bad['evidence']['service'] if s['kind']=='repeat')
        segment['period']=3
        with self.assertRaises(ValueError):expand_record(bad)
        bad=deepcopy(candidate.record());bad['evidence']['injections'][0]['rows'][0]+=1
        with self.assertRaisesRegex(ValueError,'time evidence differs'):expand_record(bad)
