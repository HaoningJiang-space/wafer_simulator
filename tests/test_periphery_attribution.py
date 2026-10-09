"""Observation scope, integer boundaries and conserved critical accounting."""
import unittest

from wafer_sim.analysis.periphery_attribution import (
    interval_profile, weighted_profile, union, overlap, network_slices,
    order_inversions, chain_accounting, compare_packet_facts)


class PeripheryAttributionTests(unittest.TestCase):
    def test_transaction_windows_do_not_impose_a_controller_window(self):
        rows = [dict(id=f'{tx}/{i}', start=0, finish=10, bytes=4096)
                for tx in ('a', 'b') for i in range(4)]
        self.assertEqual(interval_profile(rows)['peak_count'], 8)
        self.assertEqual(interval_profile(rows)['peak_useful_bytes'], 32768)
        for tx in ('a', 'b'):
            self.assertEqual(interval_profile([r for r in rows if r['id'].startswith(tx)])['peak_count'], 4)

    def test_same_boundary_release_precedes_window_reuse(self):
        rows = [dict(id='old', start=0, finish=10, bytes=4096),
                dict(id='new', start=10, finish=20, bytes=4096)]
        p = interval_profile(rows)
        self.assertEqual((p['peak_count'], p['peak_useful_bytes'], p['position_cycle_integral']), (1, 4096, 20))

    def test_invalid_lifetimes_are_rejected(self):
        with self.assertRaises(ValueError): interval_profile([dict(id='x', start=10, finish=10, bytes=1)])
        with self.assertRaises(ValueError): interval_profile([dict(id='x', start=0, finish=10, bytes=1)]*2)
        with self.assertRaises(ValueError): weighted_profile([(1, -1), (2, 1)])
        with self.assertRaises(ValueError): weighted_profile([(1, 1)])

    def test_overlap_excludes_bank_trailing_latency_and_deduplicates_intervals(self):
        bank_serializers = [(0, 128), (128, 256)]
        # First fragment's bank latency ends at 158; its channel can overlap
        # the second fragment's serializer. It does not add bank occupation.
        self.assertEqual(union(bank_serializers), [(0, 256)])
        self.assertEqual(overlap(bank_serializers, [(158, 222)]), 64)
        self.assertEqual(overlap([(0, 128)], [(128, 158)]), 0)

    def test_partial_useful_receive_bytes_exclude_padding(self):
        # Two 64-byte flits carry only 65 useful bytes; atomic commit at 20.
        p = weighted_profile([(6, 64), (11, 1), (20, -65)])
        self.assertEqual(p['peak_useful_bytes'], 65)
        self.assertEqual(p['useful_byte_cycle_integral'], 64*5+65*9)

    def test_injection_order_can_change_without_any_route_change(self):
        a, b, c = ('t', 'dram_response', 0), ('u', 'dram_response', 0), ('t', 'dram_response', 1)
        old = {key: dict(source='nic', injected=i, generated=0, ejected=i+10, route=(0, 1))
               for i, key in enumerate((a, b, c))}
        new = {key: dict(old[key], injected=i) for i, key in enumerate((b, a, c))}
        compare = compare_packet_facts(old, new, {'nic': [a, b, c]}, {'nic': [b, a, c]})
        self.assertEqual(compare['by_role']['dram_response']['route_changed_packets'], 0)
        self.assertEqual(compare['reversed_pairs'], 1)
        self.assertEqual(order_inversions([a, b, c], [c, b, a])['reversed_pairs'], 3)
        with self.assertRaises(ValueError): order_inversions([a, b], [a, c])

    def test_critical_accounting_and_network_slices_close_without_double_counting(self):
        token = 'f/phase/1'
        message = dict(token=token, bytes=64, ready=40, generated=45, first_inject=47, last_inject=87, finish=100)
        result = dict(application_cycles=100, network_messages=[message],
                      services=[dict(resource='dram-0-0/port')], operations={'f': dict(finish=100)})
        common = dict(category='memory', operation='f', token='f/phase/0')
        chain = dict(segments=[dict(common, point='service:0:release', start=0, finish=10, duration=10),
            dict(common, point='service:0:finish', start=10, finish=40, duration=30),
            dict(point='network:'+token, category='network', operation='f', token=token, start=40, finish=100, duration=60)])
        tags = {token: dict(transaction='t', role='dram_response', offset=0, ordinal=0)}
        checked = chain_accounting(result, chain, tags, {token: 't', 'f/phase/0': 't'})
        self.assertEqual(checked['totals'], {'dram_bank_serialize': 10, 'dram_bank_latency': 30, 'network/dram_response': 60})
        self.assertEqual(checked['network_slices'], dict(source_generation_wait=5, first_injection_wait=2, injection_span=40, completion_tail=13))
        with self.assertRaises(ValueError): network_slices(dict(message, generated=48))
        chain['segments'][1]['start'] = 9
        with self.assertRaises(ValueError): chain_accounting(result, chain, tags, {token: 't'})
