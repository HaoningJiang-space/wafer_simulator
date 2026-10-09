"""Discriminating component-only source gate; no fitted native inputs."""
import unittest
from wafer_sim.analysis.source_order import ordered_probe,source_queue_rows


def job(i,source,ready=0,work=1024,propagation=32):
    return dict(id=i,token=str(i),source=source,destination=10+i,ready=ready,bytes=64*work,
        work_packets=work,propagation_cycles=propagation,resources=['output'],path=[source,10+i])


class SourceOrderTests(unittest.TestCase):
    def test_same_source_serial_head_releases_before_destination(self):
        a=ordered_probe([job(0,0,propagation=100),job(1,0,propagation=53)],{'output':[1,2]})
        self.assertEqual([m['source_service_begin'] for m in a],[0,2048])
        self.assertEqual([m['finish'] for m in a],[2148,4149])

    def test_unique_sources_preserve_equal_flow_sharing(self):
        a=ordered_probe([job(i,i,propagation=74) for i in range(3)],{'output':[1,2]})
        self.assertEqual([m['finish'] for m in a],[6218]*3)

    def test_future_eligibility_does_not_compete_early(self):
        a=ordered_probe([job(0,0,work=10,propagation=0),job(1,0,ready=50,work=10,propagation=0)],{'output':[1,2]})
        self.assertEqual([m['finish'] for m in a],[20,70])

    def test_native_gate_is_injection_drain_not_receive(self):
        rows=source_queue_rows([dict(id=0,source=0,token='a',ready=0,generated=0,first_inject=0,last_inject=1987,finish=2080),
            dict(id=1,source=0,token='b',ready=0,generated=1988,first_inject=1989,last_inject=4035,finish=4149)])
        self.assertTrue(all(r['selection_boundary_matches'] for r in rows))
        self.assertEqual(rows[1]['expected_generated'],1988)

