"""Local evidence semantics; run this module on hn072, not a model benchmark."""
import unittest
from wafer_sim.analysis.local_service import output_events, service_windows, conditional_replay


def snapshots(cycle, eligible, pointer, grant, after, count=3, other=None):
    base = dict(stage='vc', cycle=cycle, input_count=count, inputs=[
        dict(input=i, requested=i in eligible, other_output_requests=(other or {}).get(i, []))
        for i in range(count)])
    return [dict(base, kind='allocate_pre', grant_pointer=pointer),
            dict(base, kind='allocate_post', grant_pointer=after, grant_input=grant)]


class LocalServiceTests(unittest.TestCase):
    def test_single_request_advances_pointer_and_empty_request_preserves_it(self):
        rows = snapshots(0, [0], 0, 0, 1) + snapshots(1, [], 1, -1, 1) + snapshots(2, [0, 1], 1, 1, 2)
        result = conditional_replay(rows, 'vc')
        self.assertEqual([r['predicted_grant'] for r in result['rows']], [0, -1, 1])
        self.assertEqual((result['grant_mismatches'], result['pointer_mismatches']), (0, 0))

    def test_wrong_native_grant_is_detected(self):
        result = conditional_replay(snapshots(0, [0, 1], 0, 1, 2), 'vc')
        self.assertEqual((result['grant_mismatches'], result['pointer_mismatches']), (1, 1))

    def test_cross_output_accept_competition_is_not_implicitly_replayed(self):
        with self.assertRaisesRegex(ValueError, 'cross-output'):
            conditional_replay(snapshots(0, [0, 1], 0, 0, 1, other={0: [2]}), 'vc')

    def test_truncated_allocator_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Truncated'):
            conditional_replay(snapshots(0, [0], 0, 0, 1)[:1], 'vc')

    def test_output_arrival_is_distinct_from_local_input_arrival(self):
        message = dict(id=0, source=1, token='a', flits=[dict(id=0,
            injection_router_arrival=0, link_arrivals=[dict(source=12, destination=24, cycle=7),
                                                       dict(source=24, destination=36, cycle=50)])])
        event, = output_events([message], 24, 36)
        self.assertEqual((event['input_identity'], event['local_arrival'], event['cycle']), ('router/12', 7, 50))

    def test_branch_counts_do_not_equal_message_counts(self):
        events = [dict(cycle=i*2, flit=i, input_identity=branch, token=token)
                  for i, (branch, token) in enumerate([('12', 'a'), ('25', 'c'), ('12', 'b'), ('25', 'c')])]
        row, = service_windows(events, 8)
        self.assertEqual(row['input_counts'], {'12': 2, '25': 2})
        self.assertEqual(row['message_counts'], {'a': 1, 'b': 1, 'c': 2})
        self.assertEqual(row['consecutive_same_input'], 0)

    def test_output_capacity_violation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'one flit'):
            service_windows([dict(cycle=2, flit=i, input_identity='12', token=str(i)) for i in (0, 1)])
