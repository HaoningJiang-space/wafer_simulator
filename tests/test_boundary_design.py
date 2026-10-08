"""Decision errors, feasibility and close-design handling are separate claims."""
import unittest
from wafer_sim.analysis.boundary_design import public_status, decision_table, design_choice


class BoundaryDesignTests(unittest.TestCase):
    def row(self,mode='pipeline',capacity=False):
        return dict(mode=mode,capacity_feasible=capacity,application_target_met=True,message_target_met=False)

    def test_audit_success_and_exact_makespan_do_not_certify_capacity(self):
        result=public_status(self.row())
        self.assertTrue(result['semantic_audit_passed'])
        self.assertEqual(result['capacity_status'],'violated')
        self.assertEqual(result['reference_agreement'],'outside_registered_targets')

    def test_unmodeled_capacity_and_reference_are_not_hardware_truth(self):
        self.assertEqual(public_status(self.row('serial',None))['capacity_status'],'unmodeled')
        row=public_status(self.row('bounded',True))
        self.assertEqual(row['reference_agreement'],'reference')
        self.assertEqual(row['hardware_calibration_status'],'uncalibrated_local_resources')

    def matrix(self):
        reg=dict(cases=['s'],contracts=['q'],placements=['baseline','ours_rotated'],
                 modes=['serial','pipeline','bounded'],gap_tolerance_cycles=100,design_indifference_cycles=100)
        rows=[]
        for p,t in [('baseline',1000),('ours_rotated',990)]:
            for m in reg['modes']:
                error=-200 if m=='serial' else (20 if m=='pipeline' and p=='ours_rotated' else 0)
                rows.append(dict(self.row(m,None if m=='serial' else m=='bounded'),shape='s',contract='q',
                                 placement=p,application_cycles=t+error,error_cycles=error))
        return rows,reg

    def test_common_bias_cancels_but_opposite_errors_can_reverse_raw_sign(self):
        rows,reg=self.matrix();row=decision_table(rows,reg)[0]
        self.assertEqual(row['serial_gap_error_cycles'],0)
        self.assertEqual(row['pipeline_gap_error_cycles'],-20)
        self.assertFalse(row['pipeline_raw_order_agrees'])
        self.assertEqual(row['pipeline_choice'],'approximately_equal')
        self.assertEqual(row['pipeline_rotated_capacity'],'violated')

    def test_missing_duplicate_or_inconsistent_pair_is_rejected(self):
        rows,reg=self.matrix()
        for invalid in (rows[:-1],rows+[rows[0]], [dict(rows[0],error_cycles=1)]+rows[1:]):
            with self.assertRaises(ValueError):decision_table(invalid,reg)

    def test_indifference_is_explicit_absolute_band(self):
        self.assertEqual(design_choice(0,100),'approximately_equal')
        self.assertEqual(design_choice(-100,100),'approximately_equal')
        self.assertEqual(design_choice(101,100),'ours_rotated')
        self.assertEqual(design_choice(-101,100),'baseline')
