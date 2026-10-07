"""Independent service accounting rejects incomplete and route-mixed evidence."""
from dataclasses import replace
import unittest
from test_timed_execution import local_binding, timing
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.architecture.timing import Link, Service
from wafer_sim.analysis.transfer_granularity import isolated_comparison, summarize_isolated


class GranularityTests(unittest.TestCase):
    def message(self, **fields):
        return dict(dict(source=0,destination=1,bytes=17,flit_bytes=8,expected_flits=3,
            flits=[dict(router_path=[10,11]) for _ in range(3)],ready=0,finish=12,
            first_inject=0,last_inject=2,first_eject=9,last_eject=11),**fields)

    def test_partial_last_flit_and_each_service_rounding(self):
        row=isolated_comparison(TimedTarget(local_binding(),timing()),self.message())
        # Independent ceil(17/8) + ceil(17/4) + ceil(17/8) plus propagation 3.
        self.assertEqual(row['serialization_cycles'],11)
        self.assertEqual(row['latency_cycles'],3)
        self.assertEqual(row['coarse_cycles'],14)
        self.assertEqual(row['error_cycles'],2)
        self.assertTrue(row['matched_path'])
        self.assertFalse(summarize_isolated([row],5)['meets_service_target'])

    def test_observed_alternate_path_is_diagnostic_not_same_path_evidence(self):
        b=local_binding()
        edges=((10,20),(20,11),(10,21),(21,11))
        b=replace(b,network=replace(b.network,router_links=edges))
        t=replace(timing(),links=tuple(Link(a,z,Service(f'{a}->{z}','bytes',4))
                     for x,y in edges for a,z in ((x,y),(y,x))))
        row=isolated_comparison(TimedTarget(b,t),self.message(
            flits=[dict(router_path=[10,21,11]) for _ in range(3)]))
        self.assertFalse(row['matched_path'])
        self.assertEqual(row['coarse_path'],(10,20,11))
        summary=summarize_isolated([row],100)
        self.assertEqual(summary['route_mismatches'],1)
        self.assertIsNone(summary['meets_service_target'])

    def test_no_missing_flits_or_zero_duration_can_pass(self):
        target=TimedTarget(local_binding(),timing())
        for change in (dict(flits=[]),dict(expected_flits=4),dict(bytes=25),dict(finish=0)):
            with self.assertRaises(ValueError): isolated_comparison(target,self.message(**change))
        self.assertIsNone(summarize_isolated([],5)['meets_service_target'])
