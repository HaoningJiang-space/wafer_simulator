"""R2.1 semantic progress regressions; history stubs are test-only probes."""
from copy import deepcopy
from pathlib import Path
import unittest
from wafer_sim.io import read_json
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.execution.causal import initialize, step_one_cycle, result, MessageProgress
from wafer_sim.analysis.causal_transition import compare_cycles, StateDivergence, LedgerVerifier

REG = read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')
ONE = [dict(source=0, destination=3, flits=1, ready=0)]


class WriteOnlyList:
    def __init__(self, callback=None):
        self.callback = callback

    def append(self, value):
        if self.callback:
            self.callback(value)

    def __len__(self):
        raise AssertionError('Simulation read evidence length')

    def __iter__(self):
        raise AssertionError('Simulation iterated evidence')

    def __getitem__(self, key):
        raise AssertionError('Simulation read evidence item')


class WriteOnlyMap:
    def __init__(self, callback=None):
        self.rows = {}
        self.callback = callback

    def __getitem__(self, key):
        if key not in self.rows:
            self.rows[key] = WriteOnlyList(
                (lambda value: self.callback(key, value)) if self.callback else None)
        return self.rows[key]

    def get(self, *args):
        raise AssertionError('Simulation read evidence mapping')


class CausalProgressTests(unittest.TestCase):
    def finish(self, state):
        while not state.complete:
            step_one_cycle(state)
        return state

    def test_zero_clocks_and_unstarted_progress_remain_distinct(self):
        state = initialize(REG['contract'], ONE)
        self.assertEqual(state.progress[0], MessageProgress())
        self.assertEqual(state.generated, {})
        step_one_cycle(state)
        progress = state.progress[0]
        self.assertEqual((progress.generated_at, progress.injected, progress.first_inject,
                          progress.last_inject), (0, 1, 0, 0))
        self.assertEqual((progress.received, progress.first_eject, progress.last_eject), (0, None, None))

    def test_semantic_update_precedes_timestamp_append(self):
        state = initialize(REG['contract'], ONE)
        observed = []
        def injection(mid, clock):
            p = state.progress[mid]
            self.assertEqual((p.injected, p.first_inject, p.last_inject), (1, clock, clock))
            observed.append('inject')
        def ejection(mid, clock):
            p = state.progress[mid]
            self.assertEqual((p.received, p.first_eject, p.last_eject), (1, clock, clock))
            observed.append('receive')
        state.evidence.injections = WriteOnlyMap(injection)
        state.evidence.ejections = WriteOnlyMap(ejection)
        self.finish(state)
        self.assertEqual(observed, ['inject', 'receive'])
        self.assertEqual(result(state), simulate(REG['contract'], ONE))

    def test_no_evidence_length_iteration_or_timestamp_read_for_execution(self):
        messages = [dict(ONE[0], flits=8), dict(ONE[0], flits=3),
                    dict(ONE[0], source=2, flits=8, ready=2)]
        contract = dict(REG['contract'], capacity_flits=2)
        plain = self.finish(initialize(contract, messages))
        state = initialize(contract, messages)
        state.evidence.injections = WriteOnlyMap()
        state.evidence.ejections = WriteOnlyMap()
        for name in ('service', 'inputs', 'credits', 'credit_sends', 'allocations'):
            setattr(state.evidence, name, WriteOnlyList())
        self.finish(state)
        self.assertEqual(state.now, plain.now)
        self.assertEqual(state.progress_snapshot(), plain.progress_snapshot())
        self.assertEqual(state.sources, plain.sources)
        self.assertEqual(state.routers, plain.routers)
        self.assertEqual(state.events.snapshot(), plain.events.snapshot())
        self.assertEqual(state.events.next_sequence, plain.events.next_sequence)

    def test_erased_timestamp_histories_do_not_change_any_default_boundary(self):
        messages = [dict(ONE[0], flits=16)]
        plain = initialize(REG['contract'], messages)
        changed = initialize(REG['contract'], messages)
        while not plain.complete:
            changed.evidence.injections.clear()
            changed.evidence.ejections.clear()
            step_one_cycle(plain)
            step_one_cycle(changed)
            self.assertEqual(changed.snapshot(), plain.snapshot())
            self.assertEqual(changed.progress_snapshot(), plain.progress_snapshot())
        self.assertTrue(changed.complete)
        self.assertEqual(result(changed), result(plain))

    def test_wrong_timestamp_list_contents_do_not_replace_semantic_summary(self):
        state = self.finish(initialize(REG['contract'], ONE))
        state.evidence.injections[0][:] = [-999, 9999]
        state.evidence.ejections[0][:] = [-999, 9999]
        self.assertEqual(state.snapshot().to_record()['remaining'], [[0, 0]])
        self.assertEqual(result(state), simulate(REG['contract'], ONE))

    def test_false_received_progress_is_rejected_with_intact_history(self):
        def change(state):
            if state.now == 50:
                state.progress[0].received -= 1
        with self.assertRaises(StateDivergence) as raised:
            compare_cycles(REG['contract'], ONE, perturb=change)
        self.assertEqual(raised.exception.record['cycle'], 50)
        self.assertIn('remaining', raised.exception.record['field'])

    def test_wrong_semantic_timestamps_fail_at_first_boundary(self):
        for field, cycle in [('generated_at', 1), ('first_inject', 1), ('last_inject', 1),
                             ('first_eject', 50), ('last_eject', 50)]:
            def change(state):
                if state.now == cycle:
                    setattr(state.progress[0], field, 999)
            with self.subTest(field=field), self.assertRaises(StateDivergence) as raised:
                compare_cycles(REG['contract'], ONE, perturb=change)
            self.assertEqual(raised.exception.record['cycle'], cycle)
            self.assertIn(field if field != 'generated_at' else 'generated', raised.exception.record['field'])

    def test_progress_snapshot_and_generation_view_are_detached(self):
        state = initialize(REG['contract'], ONE)
        step_one_cycle(state)
        view = state.generated
        view[0] = 99
        snap = state.progress_snapshot()
        record = snap.to_record()
        record['messages'][0]['injected'] = 100
        self.finish(state)
        self.assertEqual(snap.to_record()['messages'][0]['received'], 0)
        self.assertEqual(state.progress[0].generated_at, 0)
        self.assertEqual(state.progress[0].injected, 1)

    def test_progress_ledger_requires_all_boundaries_and_original_values(self):
        import io
        stream = io.StringIO()
        compare_cycles(REG['contract'], ONE, progress_stream=stream)
        rows = stream.getvalue().splitlines(keepends=True)
        self.assertEqual(len(rows), 65)
        for bad in (rows[:-1], [rows[0]]+rows,
                    [rows[0].replace('false', 'true')]+rows[1:]):
            with self.subTest(rows=len(bad)), self.assertRaises(ValueError):
                ledger = LedgerVerifier(io.StringIO(''.join(bad)))
                compare_cycles(REG['contract'], ONE, progress_stream=ledger)
                ledger.finish()
