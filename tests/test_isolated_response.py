"""Mechanism metrics distinguish first access, sustained supply and sharing."""
import copy
import unittest

from wafer_sim.analysis.isolated_response import progress, shared_windows


class IsolatedResponseTests(unittest.TestCase):
    def message(self):
        return dict(bytes=256,flit_bytes=64,expected_flits=4,ready=0,
            first_eject=4,last_eject=8,finish=9,
            flits=[dict(id=i,injected=t,router_path=[1,0,2]) for i,t in enumerate((0,1,3,5))])

    def test_progress_does_not_confuse_zero_first_wait_with_uninterrupted_supply(self):
        p=progress(self.message())
        self.assertEqual(p['first_inject_wait'],0)
        self.assertEqual(p['injection_span'],5)
        self.assertEqual(p['unused_injection_slots'],2)
        self.assertEqual(p['first_receive_boundary'],5)
        self.assertEqual(p['last_receive_boundary'],9)
        self.assertEqual(p['middle_half_injection_bytes_per_cycle'],32)
        self.assertEqual(p['injection_gap_histogram'],{1:1,2:2})

    def test_truncated_and_reordered_flits_rejected(self):
        m=self.message();m['flits'].pop()
        with self.assertRaises(ValueError):progress(m)
        m=self.message();m['flits'][2]['injected']=1
        with self.assertRaises(ValueError):progress(m)

    def test_shared_path_without_temporal_overlap_is_not_competition_evidence(self):
        def message(token,cycles):
            return dict(token=token,flits=[dict(link_arrivals=[dict(source=0,destination=1,cycle=t)]) for t in cycles])
        own=message('a',[2,6]);peer=message('b',[3,4,8]);late=message('c',[9,10])
        row=shared_windows(own,[own,peer,late])[0]
        self.assertEqual(row['own_flits'],2)
        self.assertEqual(row['peer_messages'],{'b':2})
        self.assertEqual(row['window_flits_per_cycle'],.8)
        extra=copy.deepcopy(peer);extra['flits']*=3
        with self.assertRaises(ValueError):shared_windows(own,[own,extra])
