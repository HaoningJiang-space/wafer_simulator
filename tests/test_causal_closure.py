"""Portable semantic checks for bounded G1; formal execution belongs on hn072."""
from copy import deepcopy
from pathlib import Path
import unittest
import tempfile
import json
from wafer_sim.analysis.causal_closure import read_observation
from wafer_sim.io import read_json
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.architecture.causal_merge import validate, topology

REG = read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')


class CausalClosureTests(unittest.TestCase):
    def run_case(self, name):
        case = next(c for c in REG['cases'] if c['name']==name)
        contract = dict(REG['contract'], capacity_flits=case.get('capacity_flits',32))
        return simulate(contract,case['messages'],REG['cycle_limit'])

    def test_one_flit_keeps_service_and_propagation_boundaries(self):
        r=self.run_case('single-one'); f=r['messages'][0]['flits'][0]
        self.assertEqual((f['injected'],f['injection_router_arrival'],f['ejected']), (0,2,49))
        self.assertEqual(f['router_path'],[0,2,3])
        self.assertEqual(r['messages'][0]['finish'],50)
        self.assertEqual([e['cycle'] for e in r['service'] if e['kind']=='vc_commit'],[2,23,44])
        self.assertEqual([e['cycle'] for e in r['service'] if e['kind']=='sw_commit'],[3,24,45])

    def test_drains_every_credit_including_receiver_return(self):
        r=self.run_case('single-one')
        self.assertEqual(r['final_cycle'],52)
        self.assertEqual(len(r['credit_sends']),3)
        self.assertEqual(len(r['credit_returns']),4)
        self.assertTrue(r['drained'])

    def test_source_switches_after_injection_not_destination(self):
        r=self.run_case('queued-source'); a,b=r['messages'][:2]
        self.assertEqual(b['generated'],a['last_inject']+1)
        self.assertLess(b['generated'],a['finish'])
        self.assertGreaterEqual(b['first_inject'],b['generated'])

    def test_credit_feedback_actually_blocks_service(self):
        r=self.run_case('tight-credit')
        self.assertGreater(sum(r['router_credit_stall_cycles']),0)
        self.assertGreater(sum(r['source_stall_cycles']),0)
        self.assertTrue(all(max(q)<=2 for q in r['queue_peaks']))

    def test_no_service_before_own_arrival(self):
        r=self.run_case('merge-0')
        arrivals={(e['router'],e['flit']):e['cycle'] for e in r['input_arrivals']}
        commits={(e['router'],e['flit']):e['cycle'] for e in r['service'] if e['kind']=='vc_commit'}
        for key,t in commits.items(): self.assertGreaterEqual(t,arrivals[key])
        self.assertEqual(len(commits),9216)

    def test_vc_ownership_excludes_other_requests_until_send(self):
        r=self.run_case('merge-0')
        for point in r['allocations']:
            if point['owner'] is not None: self.assertFalse(point['vc_requests'])
            self.assertLessEqual(len(point['sw_requests']),1)

    def test_late_release_not_shifted_to_zero(self):
        r=self.run_case('merge-3000')
        self.assertEqual([m['generated'] for m in r['messages']],[0,3000,6000])
        self.assertGreater(r['messages'][2]['finish'],6000)

    def test_demand_is_immutable_and_native_fields_rejected(self):
        c=deepcopy(REG['contract']); demand=deepcopy(REG['cases'][0]['messages'])
        simulate(c,demand); self.assertEqual(c,REG['contract']); self.assertEqual(demand,REG['cases'][0]['messages'])
        with self.assertRaises(ValueError): simulate(c,[dict(demand[0],arrivals=[2])])

    def test_unsupported_state_is_not_silently_approximated(self):
        for field,value in [('num_vcs',2),('speculative',1),('capacity_flits',0),('router_link_latency',0)]:
            with self.subTest(field=field), self.assertRaises(ValueError): validate(dict(REG['contract'],**{field:value}))
        with self.assertRaises(ValueError): simulate(REG['contract'],[dict(source=3,destination=0,flits=1,ready=0)])

    def test_timeout_is_incomplete(self):
        with self.assertRaises(TimeoutError): simulate(REG['contract'],REG['cases'][0]['messages'],49)

    def test_topology_keeps_reverse_credit_latency_and_two_endpoints(self):
        s=topology(REG['contract'])
        self.assertIn('router 0 node 0 1 node 1 1 router 2 17',s)
        self.assertIn('router 2 router 0 17 router 1 17 router 3 17',s)

    def test_partial_observation_cannot_be_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'observation.jsonl'
            rows=[dict(kind='begin',schema=3),dict(kind='contract')]
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError): read_observation(path)
            rows.append(dict(kind='end',complete=True,rows_before_end=17))
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            with self.assertRaises(ValueError): read_observation(path)

    def test_no_future_source_can_create_early_data(self):
        r=simulate(REG['contract'],[dict(source=0,destination=3,flits=1,ready=100)])
        self.assertEqual(r['messages'][0]['generated'],100)
        self.assertEqual(r['messages'][0]['first_inject'],100)
        self.assertTrue(all(e['cycle']>=102 for e in r['input_arrivals']))
