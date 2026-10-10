"""R2.2 sink independence and persisted-evidence fault injection."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import unittest
from wafer_sim.io import read_json
from wafer_sim.execution.causal import initialize, step_one_cycle, result, compact_record, completion_summary
from wafer_sim.analysis.causal_evidence import expand_record
from wafer_sim.adapters.causal_merge import simulate

REG = read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')
ONE = [dict(source=0, destination=3, flits=1, ready=0)]


class CausalEvidenceTests(unittest.TestCase):
    def finish(self, mode, messages=ONE, contract=None):
        state = initialize(contract or REG['contract'], messages, evidence=mode)
        while not state.complete:
            step_one_cycle(state)
        return state

    def test_same_future_state_at_every_boundary_across_three_sinks(self):
        messages = [dict(ONE[0], flits=19), dict(ONE[0], source=2, flits=23, ready=9),
                    dict(ONE[0], flits=3)]
        states = [initialize(dict(REG['contract'], capacity_flits=2), messages, evidence=m)
                  for m in ('full', 'compact', 'counters')]
        while not states[0].complete:
            for s in states:
                step_one_cycle(s)
            self.assertEqual(states[0].snapshot(), states[1].snapshot())
            self.assertEqual(states[0].snapshot(), states[2].snapshot())
            self.assertEqual(states[0].progress_snapshot(), states[2].progress_snapshot())
        self.assertEqual([completion_summary(s) for s in states], [completion_summary(states[0])]*3)

    def test_full_prediction_and_compact_expansion_equal_unmodified_g1(self):
        messages = [dict(ONE[0], flits=31), dict(ONE[0], source=1, flits=17, ready=13)]
        expected = simulate(REG['contract'], messages)
        self.assertEqual(result(self.finish('full', messages)), expected)
        self.assertEqual(expand_record(compact_record(self.finish('compact', messages))), expected)

    def test_counters_never_construct_event_rows_or_claim_full_audit(self):
        with patch('wafer_sim.execution.causal.evidence.event_row', side_effect=AssertionError('Recording')):
            state = self.finish('counters', [dict(ONE[0], flits=32)])
        summary = result(state)
        self.assertEqual(summary['messages'][0]['flits'], 32)
        self.assertFalse(summary['full_flit_audit'])
        self.assertEqual(vars(state.evidence), {})
        with self.assertRaises(ValueError):
            compact_record(state)
        with self.assertRaises(ValueError):
            state.snapshot(include_history=True)

    def test_evidence_record_is_detached_and_decodes_without_execution(self):
        record = compact_record(self.finish('compact'))
        with patch('wafer_sim.execution.causal.transition.step_one_cycle', side_effect=AssertionError):
            self.assertEqual(expand_record(record), simulate(REG['contract'], ONE))
        record['evidence']['retired'][0]['rows'][0]['router_path'].clear()
        with self.assertRaises(ValueError):
            expand_record(record)

    def test_missing_duplicate_unknown_or_mistimed_saved_evidence_is_rejected(self):
        good = compact_record(self.finish('compact', [dict(ONE[0], flits=8)]))
        changes = [lambda r: r['evidence'].pop('credits'),
                   lambda r: r['evidence'].__setitem__('unknown', []),
                   lambda r: r['summary']['messages'][0].__setitem__('finish', 999),
                   lambda r: r['evidence']['service'][0]['rows'][0].__setitem__('kind', 'unknown')]
        for change in changes:
            bad = deepcopy(good); change(bad)
            with self.assertRaises(ValueError):
                expand_record(bad)
        bad = deepcopy(good)
        bad['evidence']['service'][0]['rows'].insert(0, bad['evidence']['service'][0]['rows'][0].copy())
        bad['summary']['event_counts']['service'] += 1
        with self.assertRaisesRegex(ValueError, 'Repeated'):
            expand_record(bad)

    def test_wrong_mode_and_incomplete_completion_cannot_emit_receipt(self):
        with self.assertRaises(ValueError):
            initialize(REG['contract'], ONE, evidence='unknown')
        for mode in ('full', 'compact', 'counters'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                result(initialize(REG['contract'], ONE, evidence=mode))
