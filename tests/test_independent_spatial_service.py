"""D0 independence, coverage, completion, clock and evidence regressions."""
import copy
import unittest
from unittest.mock import patch

import networkx as nx

from test_wafer_machine import one_read
from test_memory_abstraction import ClockNetwork
from wafer_sim.adapters.independent_spatial_service import IndependentSpatialNetwork, contract, key, machine_identity
from wafer_sim.analysis.independent_spatial_service import audit
from wafer_sim.execution.timing import execute
from wafer_sim.execution.plan import Transfer
from wafer_sim.experiments.independent_spatial_service import component_cases
from wafer_sim.io import read_json


def fixture():
    c,b,_=one_read(); graph=nx.Graph(c.target.network.router_links)
    attachments=dict(c.target.network.endpoint_routers);entries={}
    for phase in b.plans['f'].phases:
        t=phase.transfer
        if t is None: continue
        k=key(t.source_endpoint,t.destination_endpoint,t.size_bytes)
        entries[k]=dict(duration_cycles=17 if t.size_bytes==16 else 71,
            routes=[dict(routers=nx.shortest_path(graph,attachments[t.source_endpoint],attachments[t.destination_endpoint]),flits=1)],samples=[])
    table=dict(schema='isolated-spatial-service-v1',validated=True,binary_sha256='fixture',
        semantic_network_config={},scope='semantic fixture, not calibrated timing',
        machines={machine_identity(c):dict(topology_sha256='fixture',entries=entries)})
    return c,b,table


def client(c,table):
    native=ClockNetwork();native.identity=dict(binary_sha256='fixture')
    return IndependentSpatialNetwork(native,contract(c,table))


class IndependentSpatialServiceTests(unittest.TestCase):
    def test_singleton_service_and_path_are_payload_specific(self):
        c,b,table=fixture();n=client(c,table)
        request=b.plans['f'].phases[0].transfer
        n.submit('request',request,0)
        self.assertEqual(n.advance(100),['request']);self.assertEqual(n.now,17)
        self.assertEqual(n.messages[0]['finish']-n.messages[0]['ready'],17)

    def test_overlapping_dram_messages_do_not_compete(self):
        c,b,table=fixture();n=client(c,table)
        t=next(p.transfer for p in b.plans['f'].phases if p.transfer and p.transfer.size_bytes==64)
        n.submit('a',t,0);n.submit('b',t,0)
        self.assertEqual(n.advance(100),['a','b']);self.assertEqual(n.now,71)
        self.assertFalse(n.native.pending)

    def test_uncalibrated_size_machine_and_binary_fail_closed(self):
        c,b,table=fixture();n=client(c,table)
        t=next(p.transfer for p in b.plans['f'].phases if p.transfer)
        with self.assertRaisesRegex(ValueError,'Uncalibrated endpoint/payload'):
            n.submit('bad',Transfer(t.data,t.source_memory,t.destination_memory,t.source_endpoint,t.destination_endpoint,65),0)
        self.assertFalse(n.pending)
        bad=copy.deepcopy(table);bad['machines']={}
        with self.assertRaisesRegex(ValueError,'Uncalibrated physical machine'):contract(c,bad)
        native=ClockNetwork();native.identity=dict(binary_sha256='wrong')
        with self.assertRaises(ValueError):IndependentSpatialNetwork(native,contract(c,table))

    def test_own_clock_and_duplicate_tokens_are_checked(self):
        c,b,table=fixture();n=client(c,table);t=b.plans['f'].phases[0].transfer
        n.submit('a',t,0)
        with self.assertRaises(ValueError):n.submit('a',t,0)
        with self.assertRaises(ValueError):n.submit('b',t,1)
        n.advance(10)
        with self.assertRaises(ValueError):n.advance(9)
        with self.assertRaises(ValueError):n.close()

    def test_complete_dag_services_and_lifetime_audit(self):
        c,b,table=fixture();spec=contract(c,table)
        result=execute(b,c.timing,network=client(c,table),cycle_limit=10000)
        checked=audit(c,b,b,c.timing,spec,result)
        self.assertTrue(checked['passed'])
        self.assertEqual(checked['execution']['operations'],1)
        self.assertEqual(result['independent_spatial_contract']['resource_contract']['model'],'U1')
        self.assertEqual(len(result['network_messages']),2)
        self.assertFalse(result['native_network_messages'])

    def test_incomplete_wrong_cost_missing_message_and_route_rejected(self):
        c,b,table=fixture();spec=contract(c,table)
        result=execute(b,c.timing,network=client(c,table),cycle_limit=10000)
        for damage in ('complete','cost','missing','path'):
            bad=copy.deepcopy(result)
            if damage=='complete':bad['complete']=False
            if damage=='cost':bad['network_messages'][0]['finish']+=1
            if damage=='missing':bad['network_messages'].pop()
            if damage=='path':
                k=bad['network_messages'][0]['component_key']
                bad['independent_spatial_contract']['entries'][k]['routes'][0]['routers']=[999]
            with self.subTest(damage=damage),self.assertRaises((ValueError,KeyError)):
                audit(c,b,b,c.timing,spec,bad)

    def test_deadline_includes_final_completion_without_truncation(self):
        c,b,table=fixture()
        result=execute(b,c.timing,network=client(c,table),cycle_limit=10000);end=result['application_cycles']
        with self.assertRaises(TimeoutError):execute(b,c.timing,network=client(c,table),cycle_limit=end-1)
        self.assertTrue(execute(b,c.timing,network=client(c,table),cycle_limit=end)['complete'])

    def test_component_design_never_reads_application_evidence(self):
        reads=[]
        def checked_read(path):
            reads.append(str(path))
            self.assertNotIn('/results/',str(path));self.assertNotIn('/runs/',str(path))
            return read_json(path)
        with patch('wafer_sim.experiments.spatial_scaling.read_json',side_effect=checked_read):
            machines,cases=component_cases()
        self.assertEqual(len(machines),3)
        self.assertEqual({c['side'] for c in cases},{4,6,7})
        self.assertTrue({16,16384,65536} <= {c['bytes'] for c in cases})
        self.assertEqual(len(cases),len({(c['machine_sha256'],c['key']) for c in cases}))
        self.assertTrue(reads)

    def test_native_completion_keeps_conservative_d0_boundary(self):
        c,b,table=fixture();n=client(c,table)
        n.submit('dram',b.plans['f'].phases[0].transfer,0)
        n.submit('c2c',Transfer('z','sram-1','sram-0',2,0,64),0)
        self.assertEqual(n.advance(100),['c2c']);self.assertEqual(n.now,7)
        self.assertEqual(n.advance(100),['dram']);self.assertEqual(n.now,17)

