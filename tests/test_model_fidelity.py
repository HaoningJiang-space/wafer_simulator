import unittest
from wafer_sim.analysis.model_fidelity import error_summary, placement_pairs


class FidelityTests(unittest.TestCase):
    def row(self, placement, fine, coarse):
        return dict(algorithm='tree', memory_bytes_per_cycle=1024, placement=placement,
                    reference_cycles=fine, coarse_cycles=coarse)

    def test_small_time_error_can_hide_large_gap_error(self):
        rows = [self.row('baseline',4697,4621), self.row('ours_rotated',5005,5169)]
        self.assertLess(error_summary(rows)['maximum_application_ape_percent'], 3.28)
        pair = placement_pairs(rows)[0]
        self.assertEqual((pair['reference_gap_cycles'],pair['coarse_gap_cycles']),(-308,-548))
        self.assertAlmostEqual(pair['gap_absolute_relative_error_percent'], 100*240/308)
        self.assertTrue(pair['ordering_agrees'])

    def test_reference_tie_is_not_rank_agreement_or_relative_error(self):
        pair = placement_pairs([self.row('baseline',100,101),self.row('ours_rotated',100,100)])[0]
        self.assertFalse(pair['ordering_agrees'])
        self.assertIsNone(pair['gap_absolute_relative_error_percent'])

    def test_incomplete_duplicate_or_invalid_evidence_rejected(self):
        row = self.row('baseline',100,100)
        for rows in ([row], [row,row]):
            with self.assertRaises(ValueError): placement_pairs(rows)
        for rows in ([],[self.row('baseline',0,1)]):
            with self.assertRaises(ValueError): error_summary(rows)
