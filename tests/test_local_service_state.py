"""Causal local boundaries and blocking, with explicitly external credit input."""
import unittest
from wafer_sim.analysis.local_service_state import reconstruct_state


def contract(capacity=32):
    return dict(input_count=3, downstream_capacity=capacity, routing_delay=0, vc_alloc_delay=1,
                sw_alloc_delay=1, crossbar_delay=2, channel_latency=17,
                vc_busy_when_full=False, output_buffer_limit=-1)


class LocalStateTests(unittest.TestCase):
    def test_vc_and_switch_are_different_service_boundaries(self):
        result = reconstruct_state([dict(flit=i, input=i+1, cycle=0) for i in (0, 1)],
                                   [dict(cycle=40, amount=2)], contract())
        a, b = result['boundaries']
        self.assertEqual([a['vc_commit'], a['sw_commit'], a['output_send'], a['output_sink_arrival']], [0, 1, 3, 21])
        self.assertEqual([b['vc_commit'], b['sw_commit'], b['output_send'], b['output_sink_arrival']], [2, 3, 5, 23])

    def test_busy_vc_filters_other_input_before_switch_contention(self):
        result = reconstruct_state([dict(flit=i, input=i+1, cycle=0) for i in (0, 1)],
                                   [dict(cycle=40, amount=2)], contract())
        second_cycle = next(r for r in result['intervals'] if r['cycle'] == 1)
        self.assertEqual((second_cycle['vc_requests'], second_cycle['sw_requests']), ([], [1]))

    def test_credit_blocks_owner_and_release_does_not_require_destination_finish(self):
        result = reconstruct_state([dict(flit=i, input=i+1, cycle=0) for i in (0, 1)],
                                   [dict(cycle=40, amount=1), dict(cycle=80, amount=1)], contract(1))
        a, b = result['boundaries']
        self.assertEqual((a['output_sink_arrival'], b['vc_commit'], b['sw_commit']), (21, 2, 40))
        self.assertGreater(result['skipped_empty_or_blocked_cycles'], 0)

    def test_fifo_at_one_input_preserves_arrival_order(self):
        result = reconstruct_state([dict(flit=8, input=1, cycle=0), dict(flit=2, input=1, cycle=1)],
                                   [dict(cycle=40, amount=2)], contract())
        finish = {r['flit']: r['sw_commit'] for r in result['boundaries']}
        self.assertEqual(finish, {8: 1, 2: 3})

    def test_missing_credit_is_not_complete(self):
        with self.assertRaisesRegex(ValueError, 'credit drainage'):
            reconstruct_state([dict(flit=0, input=1, cycle=0)], [], contract())

    def test_overreturn_of_credit_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'occupancy'):
            reconstruct_state([dict(flit=0, input=1, cycle=1)], [dict(cycle=0, amount=1)], contract())
