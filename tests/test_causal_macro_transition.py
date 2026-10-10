"""R3 exact-core migration, boundary sequence and guarded-jump negative tests."""
from copy import deepcopy
from pathlib import Path
import json
from unittest.mock import patch
import unittest
from wafer_sim.io import read_json
from wafer_sim.execution.causal import initialize, step_one_cycle, result, completion_summary
from wafer_sim.execution.causal.macro import run, SingleFlowPeriod2Rule, RecentEvents
from wafer_sim.execution.causal.source import SourceRange, LazyPackets
from wafer_sim.analysis.causal_evidence import expand_record
from wafer_sim.analysis.causal_macro_transition import reference_snapshots, check_accuracy
from wafer_sim.adapters.causal_merge import simulate

REG = read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')


def demand(n, ready=0):
    return [dict(source=0, destination=3, flits=n, ready=ready)]


class MacroTransitionTests(unittest.TestCase):
    def recognized(self):
        state = initialize(REG['contract'], demand(1024), evidence='counters')
        state.sources[0].issuing = SourceRange(); state.work = LazyPackets(); state.observer = RecentEvents()
        rule = SingleFlowPeriod2Rule()
        for _ in range(400):
            proposal = rule.recognize(state)
            if proposal is not None:
                return state, rule, proposal
            step_one_cycle(state)
        self.fail('No recognized period-two transition')

    def test_no_ast_prototype_is_used_by_the_new_runner(self):
        with patch('wafer_sim.adapters.causal_macro.derived_source', side_effect=AssertionError('AST')):
            self.assertEqual(expand_record(run(REG['contract'], demand(128)).record()),
                             simulate(REG['contract'], demand(128)))

    def test_macro_on_off_and_all_evidence_modes_match_original_events(self):
        for n, ready in ((1, 0), (64, 0), (127, 0), (128, 0), (1025, 37)):
            expected = simulate(REG['contract'], demand(n, ready))
            for enabled in (False, True):
                with self.subTest(flits=n, enabled=enabled):
                    full = run(REG['contract'], demand(n, ready), compress=enabled, evidence='full')
                    compact = run(REG['contract'], demand(n, ready), compress=enabled)
                    counters = run(REG['contract'], demand(n, ready), compress=enabled, evidence='counters')
                    self.assertEqual(result(full.state), expected)
                    self.assertEqual(expand_record(compact.record()), expected)
                    self.assertEqual(full.compact(), counters.compact())
                    self.assertEqual(full.state.snapshot(), counters.state.snapshot())
                    self.assertEqual(full.state.progress_snapshot(), counters.state.progress_snapshot())

    def test_exact_normal_step_is_reused_and_only_counts_actual_updates(self):
        from wafer_sim.execution.causal.transition import step_one_cycle as exact
        with patch('wafer_sim.execution.causal.macro.step_one_cycle', wraps=exact) as step:
            candidate = run(REG['contract'], demand(1024), evidence='counters')
        self.assertEqual(step.call_count, candidate.metrics()['physical_cycle_updates'])
        self.assertGreater(candidate.metrics()['skipped_cycles'], 1000)

    def test_macro_checkpoints_match_legacy_sequence_and_all_state(self):
        candidate = run(REG['contract'], demand(1024), checkpoints=True)
        clocks = [r['state']['cycle'] for r in candidate.metrics()['checkpoints']]
        expected, boundaries = reference_snapshots(REG['contract'], demand(1024), 200000, clocks)
        checked = check_accuracy(candidate.record(), candidate.metrics(), expected, boundaries)
        self.assertGreater(checked['checkpoints_checked'], 0)
        metric = deepcopy(candidate.metrics())
        metric['checkpoints'][-1]['state']['next_event_sequence'] += 1
        with self.assertRaises(ValueError):
            check_accuracy(candidate.record(), metric, expected, boundaries)

    def test_saved_json_checkpoint_keys_roundtrip_without_hiding_a_clock_error(self):
        candidate = run(REG['contract'], demand(128), checkpoints=True)
        record = json.loads(json.dumps(candidate.record()))
        metrics = json.loads(json.dumps(candidate.metrics()))
        clocks = [r['state']['cycle'] for r in metrics['checkpoints']]
        expected, boundaries = reference_snapshots(REG['contract'], demand(128), 200000, clocks)
        self.assertTrue(check_accuracy(record, metrics, expected, boundaries)['passed'])
        metrics['checkpoints'][-1]['progress']['messages'][0]['last_inject'] += 1
        with self.assertRaises(ValueError):
            check_accuracy(record, metrics, expected, boundaries)

    def test_full_macro_metrics_acknowledge_online_evidence_expansion(self):
        full = run(REG['contract'], demand(128), evidence='full')
        self.assertTrue(full.metrics()['expanded_during_execution'])
        self.assertFalse(run(REG['contract'], demand(128)).metrics()['expanded_during_execution'])

    def test_unmodeled_live_metadata_disables_the_rule(self):
        state, rule, proposal = self.recognized()
        state.work.data[min(state.work.data)]['unknown'] = 1
        self.assertFalse(rule.guard(state))
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            rule.apply(state, proposal, 1)

    def test_stale_authorization_rejects_owner_credit_work_event_and_sequence_changes(self):
        changes = [lambda s: setattr(s.routers[0], 'owner', 2),
                   lambda s: setattr(s.routers[0], 'credit', 31),
                   lambda s: setattr(s.progress[0], 'received', s.progress[0].received-1),
                   lambda s: setattr(s.events, 'next_sequence', s.events.next_sequence+1),
                   lambda s: s.events.pending[min(s.events.pending)].reverse(),
                   lambda s: setattr(s.routers[0], 'sw_ready', 9999)]
        for change in changes:
            state, rule, proposal = self.recognized()
            before = state.snapshot()
            change(state)
            if state.snapshot() == before:
                state.events.pending[max(state.events.pending)][0].payload['kind'] = 'unknown'
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                rule.apply(state, proposal, 1)

    def test_forged_or_changed_template_cannot_authorize_a_jump(self):
        state, rule, proposal = self.recognized()
        proposal['service'][0]['cycle'] += 1
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            rule.apply(state, proposal, 1)
        state, _, proposal = self.recognized()
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            SingleFlowPeriod2Rule().apply(state, proposal, 1)

    def test_remaining_tail_deadline_and_final_credit_drain_are_not_skipped(self):
        candidate = run(REG['contract'], demand(2049), evidence='counters')
        metric = candidate.metrics(); tail = metric['batches'][-1]
        self.assertEqual(tail['source_remaining_after'], 1)
        self.assertLess(tail['end'], candidate.compact()['messages'][0]['finish'])
        self.assertGreater(candidate.final_cycle, candidate.compact()['messages'][0]['finish'])
        for enabled in (False, True):
            with self.assertRaises(TimeoutError):
                run(REG['contract'], demand(2049), candidate.final_cycle-1, compress=enabled)
            self.assertEqual(run(REG['contract'], demand(2049), candidate.final_cycle,
                                 compress=enabled).final_cycle, candidate.final_cycle)

    def test_counters_have_no_reconstructable_record_and_live_storage_is_bounded(self):
        candidate = run(REG['contract'], demand(8192), evidence='counters')
        self.assertEqual(candidate.state.work.data, {})
        self.assertEqual(vars(candidate.state.evidence), {})
        with self.assertRaises(ValueError):
            candidate.record()
        self.assertLess(candidate.metrics()['physical_cycle_updates'], 400)

    def test_source_and_snapshot_storage_change_preserves_every_ordinary_boundary(self):
        eager = initialize(REG['contract'], demand(128))
        lazy = initialize(REG['contract'], demand(128))
        lazy.sources[0].issuing = SourceRange(); lazy.work = LazyPackets()
        while not eager.complete:
            self.assertEqual(eager.snapshot(), lazy.snapshot())
            step_one_cycle(eager); step_one_cycle(lazy)
        self.assertEqual(eager.snapshot(), lazy.snapshot())
        self.assertEqual(result(eager), result(lazy))

    def test_other_sources_merges_credit_contracts_and_invalid_options_are_rejected(self):
        for contract, messages in [(REG['contract'], demand(8)+demand(8)),
                (REG['contract'], [dict(demand(8)[0], source=1)]),
                (dict(REG['contract'], capacity_flits=2), demand(8))]:
            with self.assertRaises(ValueError):
                run(contract, messages)
        with self.assertRaises(ValueError):
            run(REG['contract'], demand(8), compress=1)
