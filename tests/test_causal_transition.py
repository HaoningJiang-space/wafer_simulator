"""R1 semantic and first-divergence regressions; run on hn072."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from wafer_sim.io import read_json
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.execution.causal import initialize, step_one_cycle, result, run
from wafer_sim.execution.causal.state import EventQueue
from wafer_sim.analysis.causal_transition import compare_cycles, StateDivergence
from wafer_sim.analysis.causal_transition import LedgerVerifier, check_saved_prediction

REG = read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')
ONE = [dict(source=0, destination=3, flits=1, ready=0)]


class CausalTransitionTests(unittest.TestCase):
    def test_one_cycle_is_explicit_and_finish_is_not_drain(self):
        state = initialize(REG['contract'], ONE)
        for cycle in range(50):
            self.assertEqual(state.now, cycle)
            self.assertIs(step_one_cycle(state), state)
        self.assertFalse(state.complete)
        self.assertEqual(state.evidence.ejections[0], [49])
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            result(state)
        while not state.complete:
            step_one_cycle(state)
        self.assertEqual(state.now, 64)
        self.assertEqual(result(state), simulate(REG['contract'], ONE))
        with self.assertRaisesRegex(ValueError, 'completed'):
            step_one_cycle(state)

    def test_same_clock_event_order_is_insertion_order(self):
        queue = EventQueue()
        queue.schedule(10, 'sink', flit=1)
        queue.schedule(3, 'credit', target='router', number=0)
        queue.schedule(10, 'arrival', router=2, input=0, flit=2)
        rows = queue.pop(10)
        self.assertEqual([r.sequence for r in rows], [0, 2])
        self.assertEqual([r.payload['kind'] for r in rows], ['sink', 'arrival'])
        self.assertEqual(queue.pop(3)[0].sequence, 1)

    def test_snapshot_is_read_only_detached_and_has_exact_deadline(self):
        state = initialize(REG['contract'], ONE)
        for _ in range(3):
            step_one_cycle(state)
        snap = state.snapshot()
        record = snap.to_record()
        self.assertEqual(record['routers'][0]['sw_ready'], 3)
        record['routers'][0]['credit'] = -100
        self.assertEqual(state.routers[0].credit, 32)
        with self.assertRaises(FrozenInstanceError):
            snap.payload = None
        step_one_cycle(state)
        self.assertEqual(snap.to_record()['cycle'], 3)

    def test_full_history_snapshot_and_result_do_not_alias_state(self):
        state = initialize(REG['contract'], ONE)
        while not state.complete:
            step_one_cycle(state)
        record = state.snapshot(include_history=True).to_record()
        record['all_work'][0][1]['router_path'].clear()
        projection = result(state)
        projection['service'][0]['cycle'] = -1
        self.assertEqual(state.work[0]['router_path'], [0, 2, 3])
        self.assertEqual(state.evidence.service[0]['cycle'], 2)

    def test_cycle_comparison_includes_final_credit(self):
        reference, checked = compare_cycles(REG['contract'], ONE)
        self.assertEqual(checked['boundaries_checked'], 65)
        self.assertEqual(checked['cycles_checked'], 64)
        self.assertTrue(checked['final_boundary_checked'])
        self.assertEqual(max(e['cycle'] for e in reference['credit_returns']), 63)

    def test_first_credit_difference_has_cycle_and_field(self):
        def change(state):
            if state.now == 7:
                state.routers[2].credit -= 1
        with self.assertRaises(StateDivergence) as raised:
            compare_cycles(REG['contract'], ONE, perturb=change)
        self.assertEqual(raised.exception.record['cycle'], 7)
        self.assertEqual(raised.exception.record['field'], 'state.routers[2].credit')

    def test_future_event_reorder_is_detected_before_consumption(self):
        def change(state):
            if state.now == 1:
                state.events.pending[2].reverse()
        with self.assertRaises(StateDivergence) as raised:
            compare_cycles(REG['contract'], [ONE[0], dict(ONE[0], source=2)], perturb=change)
        self.assertEqual(raised.exception.record['cycle'], 1)
        self.assertIn('events', raised.exception.record['field'])

    def test_owner_and_deadline_differences_cannot_cancel_at_finish(self):
        for field, value in [('owner', 1), ('sw_ready', 4)]:
            def change(state):
                if state.now == 3:
                    setattr(state.routers[0], field, value)
            with self.subTest(field=field), self.assertRaises(StateDivergence) as raised:
                compare_cycles(REG['contract'], ONE, perturb=change)
            self.assertEqual(raised.exception.record['cycle'], 3)

    def test_queued_packet_metadata_is_checked_before_it_is_injected(self):
        messages = [dict(ONE[0], flits=8)]
        def change(state):
            if state.now == 1:
                state.work[7]['message'] = 99
        with self.assertRaises(StateDivergence) as raised:
            compare_cycles(REG['contract'], messages, perturb=change)
        self.assertEqual(raised.exception.record['cycle'], 1)
        self.assertIn('issuing_work', raised.exception.record['field'])

    def test_same_source_queued_and_tight_credit_small_cases(self):
        messages = [dict(source=0, destination=3, flits=8, ready=0),
                    dict(source=0, destination=3, flits=3, ready=0),
                    dict(source=2, destination=3, flits=8, ready=2)]
        reference, checked = compare_cycles(dict(REG['contract'], capacity_flits=2), messages)
        self.assertTrue(checked['passed'])
        self.assertEqual(reference['messages'][1]['generated'], reference['messages'][0]['last_inject']+1)
        self.assertGreater(sum(reference['router_credit_stall_cycles']), 0)

    def test_deadline_including_drain_is_not_complete(self):
        with self.assertRaises(TimeoutError):
            run(REG['contract'], ONE, 63)
        self.assertEqual(run(REG['contract'], ONE, 64)['final_cycle'], 64)

    def test_no_arrival_or_native_field_is_accepted_as_input(self):
        with self.assertRaises(ValueError):
            initialize(REG['contract'], [dict(ONE[0], arrival=[2])])
        with self.assertRaises(ValueError):
            initialize(REG['contract'], [dict(ONE[0], ready=True)])
        with self.assertRaises(ValueError):
            initialize(dict(REG['contract'], num_vcs=2), ONE)

    def test_inputs_are_not_changed(self):
        c, messages = deepcopy(REG['contract']), deepcopy(ONE)
        run(c, messages)
        self.assertEqual(c, REG['contract'])
        self.assertEqual(messages, ONE)

    def test_delayed_boundary_has_no_early_generation(self):
        reference, checked = compare_cycles(REG['contract'], [dict(ONE[0], ready=37)])
        self.assertEqual(reference['messages'][0]['generated'], 37)
        self.assertEqual(checked['cycles_checked'], 101)

    def test_stored_output_is_checked_not_replaced(self):
        reference = simulate(REG['contract'], ONE)
        saved = deepcopy(reference)
        saved['credit_returns'][0]['cycle'] += 1
        with self.assertRaises(StateDivergence):
            check_saved_prediction(saved, reference)
        saved = deepcopy(reference)
        saved['service'].append(saved['service'][0])
        with self.assertRaises(StateDivergence):
            check_saved_prediction(saved, reference)

    def test_duplicate_missing_or_changed_boundary_ledger_is_rejected(self):
        import io
        good = io.StringIO()
        compare_cycles(REG['contract'], ONE, stream=good)
        rows = good.getvalue().splitlines(keepends=True)
        for bad in ([rows[0]]+rows, rows[:-1], [rows[0].replace('false', 'true')]+rows[1:]):
            with self.subTest(rows=len(bad)), self.assertRaises(ValueError):
                checker = LedgerVerifier(io.StringIO(''.join(bad)))
                compare_cycles(REG['contract'], ONE, stream=checker)
                checker.finish()
