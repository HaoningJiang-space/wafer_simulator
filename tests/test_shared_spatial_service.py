"""Shared resource identity, fair fluid progress and complete-DAG regressions."""
import copy
from fractions import Fraction
from pathlib import Path
import unittest
from unittest.mock import patch

from test_wafer_machine import one_read
from wafer_sim.adapters.shared_spatial_service import SharedSpatialNetwork, contract, max_min_rates
from wafer_sim.analysis.shared_spatial_service import audit, audit_network
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.plan import Transfer
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json


def fixture():
    c,b,_=one_read()
    reg=read_json(Path(__file__).resolve().parents[1]/'configs/shared_spatial_service.json')
    spec=contract(c,reg)
    return c,b,spec,SharedSpatialNetwork(b,c.timing,spec)


def transfer(c,source,destination,size=64):
    return Transfer('fixture',source,destination,c.endpoints[source],c.endpoints[destination],size)


def drain(n):
    while n.pending:n.advance(10000)
    return n.close()


class SharedSpatialServiceTests(unittest.TestCase):
    def test_progressive_filling_redistributes_spare_capacity(self):
        rates=max_min_rates({0:['a','b'],1:['a'],2:['b']},{'a':Fraction(1,2),'b':Fraction(1)})
        self.assertEqual(rates,{0:Fraction(1,4),1:Fraction(1,4),2:Fraction(3,4)})

    def test_short_payload_rounding_and_long_unloaded_rule(self):
        for size,expected in ((16,13),(64,13),(65,15),(16384,523),(65536,2059)):
            c,b,spec,n=fixture();n.submit('a',transfer(c,'dram-0-0','sram-0',size),0)
            record=drain(n);self.assertEqual(record['messages'][0]['finish'],expected)
            self.assertTrue(audit_network(b.network,dict(network_messages=record['messages'],**n.evidence()))['passed'])

    def test_dram_c2c_and_io_share_one_output_without_native_process(self):
        c,b,spec,n=fixture()
        with patch('subprocess.Popen',side_effect=AssertionError('D1 must not spawn native simulation')):
            for token,source in (('dram','dram-0-0'),('c2c','sram-0'),('io','host-memory')):
                n.submit(token,transfer(c,source,'sram-2'),0)
            record=drain(n)
        self.assertEqual({m['service_finish'] for m in record['messages']},{6})
        common=set.intersection(*(set(m['resources']) for m in record['messages']))
        self.assertTrue(any(r.startswith('output/') and '/router/' in r for r in common))
        self.assertTrue(audit_network(b.network,dict(network_messages=record['messages'],**n.evidence()))['passed'])

    def test_disjoint_paths_and_reverse_direction_do_not_share_outputs(self):
        c,b,spec,n=fixture()
        n.submit('a',transfer(c,'sram-0','sram-1',256),0)
        n.submit('b',transfer(c,'sram-2','sram-3',256),0)
        record=drain(n);self.assertEqual({m['service_finish'] for m in record['messages']},{8})
        c,b,spec,n=fixture()
        n.submit('a',transfer(c,'sram-0','sram-1',256),0)
        n.submit('b',transfer(c,'sram-1','sram-0',256),0)
        record=drain(n);self.assertEqual({m['service_finish'] for m in record['messages']},{8})

    def test_staggered_flow_progress_resumes_after_peer_releases(self):
        c,b,spec,n=fixture()
        n.submit('a',transfer(c,'dram-0-0','sram-0',256),0)
        self.assertEqual(n.advance(3),[])
        n.submit('b',transfer(c,'dram-0-0','sram-0',64),3)
        record=drain(n);by_token={m['token']:m for m in record['messages']}
        self.assertEqual(by_token['a']['service_finish'],10)
        self.assertEqual(by_token['b']['service_finish'],7)
        self.assertTrue(audit_network(b.network,dict(network_messages=record['messages'],**n.evidence()))['passed'])

    def test_idle_ready_translation_and_external_boundaries_do_not_change_progress(self):
        endings=[]
        for ready in (0,509):
            c,b,spec,n=fixture();n.advance(ready)
            n.submit('a',transfer(c,'dram-0-0','sram-0',256),ready)
            for t in range(ready+1,ready+8):n.advance(t)
            record=drain(n);endings.append(record['messages'][0]['finish']-ready)
            self.assertEqual(len(n.epochs),1)
        self.assertEqual(endings,[19,19])

    def test_full_execution_audit_and_critical_chain(self):
        c,b,spec,n=fixture();result=execute(b,c.timing,network=n,cycle_limit=10000)
        self.assertTrue(audit(c,b,b,c.timing,spec,result)['passed'])
        chain=critical_chain(b,result)
        self.assertEqual(sum(chain['cycles'].values()),result['application_cycles'])
        self.assertEqual(chain['cycles']['network'],26)
        self.assertEqual(result['flow_counters']['flit_events'],0)

    def test_capacities_fairness_paths_and_missing_work_rejected(self):
        c,b,spec,n=fixture()
        n.submit('a',transfer(c,'dram-0-0','sram-0',64),0)
        n.submit('b',transfer(c,'dram-0-0','sram-0',64),0)
        record=drain(n);result=dict(network_messages=record['messages'],**n.evidence())
        for kind in ('capacity','fairness','path','missing','finish'):
            bad=copy.deepcopy(result)
            if kind=='capacity':bad['flow_epochs'][0]['rates']['0']=[1,1]
            if kind=='fairness':bad['flow_epochs'][0]['rates']={'0':[1,8],'1':[1,8]}
            if kind=='path':bad['network_messages'][0]['path']=[999]
            if kind=='missing':bad['flow_epochs']=[];bad['flow_counters']['epochs']=0
            if kind=='finish':bad['network_messages'][0]['service_finish']+=1
            with self.subTest(kind=kind),self.assertRaises(ValueError):audit_network(b.network,bad)

    def test_duplicate_clock_close_and_deadline_checks(self):
        c,b,spec,n=fixture();t=transfer(c,'dram-0-0','sram-0')
        n.submit('a',t,0)
        with self.assertRaises(ValueError):n.submit('a',t,0)
        with self.assertRaises(ValueError):n.submit('b',t,1)
        with self.assertRaises(ValueError):n.close()
        n.advance(1)
        with self.assertRaises(ValueError):n.advance(0)
        c,b,spec,n=fixture();end=execute(b,c.timing,network=n,cycle_limit=10000)['application_cycles']
        c,b,spec,n=fixture()
        with self.assertRaises(TimeoutError):execute(b,c.timing,network=n,cycle_limit=end-1)
        c,b,spec,n=fixture();self.assertTrue(execute(b,c.timing,network=n,cycle_limit=end)['complete'])
