"""Portable semantic checks for bounded G1; formal execution belongs on hn072."""
from copy import deepcopy
from pathlib import Path
import unittest
import tempfile
import json
from wafer_sim.analysis.causal_closure import (read_observation, validate_observation,
    prediction_indexes, compare, verify_sources)
from wafer_sim.io import read_json
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.architecture.causal_merge import validate, topology

REG = read_json(Path(__file__).resolve().parents[1]/'configs/causal_closure.json')
REPO = Path(__file__).resolve().parents[1]


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
        # Receiver consumption returns its own credit early; the final reverse
        # inter-router credit arrives at 45 + 17 + 1 = 63, then drains at 64.
        self.assertEqual(r['final_cycle'],64)
        self.assertEqual(max(e['cycle'] for e in r['credit_returns']),63)
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


class CausalClosureAuditTests(unittest.TestCase):
    def observation(self):
        # Schema-3 snapshot of router 0's first allocation: two endpoint inputs
        # and the reverse router port. This is format evidence, not an oracle
        # for the predictor's transitions.
        inputs = []
        for number, router, endpoint in [(0,-1,0),(1,-1,1),(2,2,-1)]:
            present = number == 0
            inputs.append(dict(input=number,upstream_router=router,upstream_endpoint=endpoint,
                occupancy=1 if present else 0,state='vc_alloc' if present else 'idle',
                head_flit=0 if present else -1,head_message=0 if present else -1,
                target_in_route=present,vc_evaluate_pending=present,sw_evaluate_pending=False,
                requested=present,other_output_requests=[]))
        rows = [dict(kind='begin',schema=3,scope='four-router causal closure observation'),
            dict(kind='contract',router=0,output=2,input_count=3,crossbar_delay=2,
                channel_latency=17,downstream_capacity=32,vc_busy_when_full=False,
                output_buffer_limit=-1,routing_delay=0,vc_alloc_delay=1,sw_alloc_delay=1),
            dict(kind='allocate_pre',stage='vc',cycle=2,router=0,output=2,destination=2,
                input_count=3,grant_pointer=0,grant_input=-1,vc_available=True,vc_owner=-1,
                vc_busy_when_full=False,credit_available=True,credit_slots=32,
                downstream_occupancy=0,output_buffer_occupancy=0,output_buffer_limit=-1,inputs=inputs)]
        return self.close(rows)

    def close(self, rows):
        return rows+[dict(kind='end',complete=True,rows_before_end=len(rows))]

    def prediction(self):
        return simulate(REG['contract'], REG['cases'][0]['messages'])

    def test_schema_three_snapshot_round_trips(self):
        rows=self.observation()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'observation.jsonl'
            path.write_text(''.join(json.dumps(r)+'\n' for r in rows))
            self.assertEqual(read_observation(path),rows)

    def test_unknown_event_with_consistent_footer_is_rejected_by_comparator(self):
        rows=self.close(self.observation()[:-1]+[dict(kind='unrecognized',cycle=2)])
        with self.assertRaisesRegex(ValueError,'Unknown causal observation event'):
            compare(REG['contract'],self.prediction(),{},rows)

    def test_repeated_begin_or_end_is_rejected_with_consistent_count(self):
        for marker in (self.observation()[0],self.observation()[-1]):
            rows=self.close(self.observation()[:-1]+[marker])
            with self.subTest(marker=marker['kind']), self.assertRaisesRegex(ValueError,'Repeated observation'):
                validate_observation(rows)

    def test_missing_and_extra_fields_are_not_ignored(self):
        for extra in (False,True):
            rows=self.observation()
            if extra: rows[2]['ignored']=0
            else: del rows[2]['credit_slots']
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError,'fields'):
                validate_observation(rows)

    def test_invalid_types_and_allocation_stage_are_rejected(self):
        for field,value in [('cycle',True),('credit_available',1),('stage','other'),('kind',[])]:
            rows=self.observation();rows[2][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_observation(rows)

    def test_input_identity_and_attachment_cannot_be_forged(self):
        for field,value in [('input',0),('upstream_endpoint',3),('state','invented')]:
            rows=self.observation();rows[2]['inputs'][1][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_observation(rows)

    def test_invalid_credit_amount_and_endpoint_are_rejected(self):
        for field,value in [('amount',0),('amount',-1),('endpoint',4)]:
            credit=dict(kind='endpoint_credit',cycle=5,endpoint=0,amount=1);credit[field]=value
            rows=self.close(self.observation()[:-1]+[credit])
            with self.subTest(field=field), self.assertRaises(ValueError): validate_observation(rows)

    def test_duplicate_json_fields_are_rejected_before_decoding_can_hide_them(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'observation.jsonl'
            text=''.join(json.dumps(r)+'\n' for r in self.observation())
            path.write_text(text.replace('"schema": 3','"schema": 3, "schema": 3'))
            with self.assertRaisesRegex(ValueError,'Repeated observation JSON field'): read_observation(path)

    def test_duplicate_predicted_service_is_rejected_after_real_execution(self):
        p=self.prediction();p['service'].append(deepcopy(p['service'][0]))
        with self.assertRaisesRegex(ValueError,'Repeated predicted service identity'):
            compare(REG['contract'],p,{},self.observation())

    def test_duplicate_predicted_allocation_is_rejected_after_real_execution(self):
        p=self.prediction();p['allocations'].append(deepcopy(p['allocations'][0]))
        with self.assertRaisesRegex(ValueError,'Repeated predicted allocation identity'):
            compare(REG['contract'],p,{},self.observation())

    def test_duplicate_predicted_messages_and_flits_are_rejected(self):
        for kind in ('message','flit'):
            p=self.prediction()
            rows=p['messages'] if kind=='message' else p['messages'][0]['flits']
            rows.append(deepcopy(rows[0]))
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError,'Repeated predicted '+kind):
                prediction_indexes(p)

    def test_unknown_predicted_service_is_rejected(self):
        p=self.prediction();p['service'][0]['kind']='invented'
        with self.assertRaisesRegex(ValueError,'Unknown predicted service'): prediction_indexes(p)

    def test_old_auditor_requires_explicit_revision_flag(self):
        start=read_json(REPO/'docs/results/causal-closure-001/STARTED.json')
        with self.assertRaisesRegex(ValueError,'Changed predictor/observer/comparator source'):
            verify_sources(REPO,start)

    def test_explicit_revision_retains_pinned_old_and_current_auditor_identities(self):
        start=read_json(REPO/'docs/results/causal-closure-001/STARTED.json')
        revisions=verify_sources(REPO,start,True)
        self.assertEqual(len(revisions),1)
        self.assertEqual(revisions[0]['archived_commit'],start['source_commit'])
        self.assertEqual(revisions[0]['archived_sha256'],start['source_hashes'][revisions[0]['path']])
        self.assertNotEqual(revisions[0]['current_sha256'],revisions[0]['archived_sha256'])

    def test_revision_flag_does_not_accept_other_sources_or_an_unknown_auditor(self):
        for path in ('src/wafer_sim/adapters/causal_merge.py','src/wafer_sim/analysis/causal_closure.py'):
            start=read_json(REPO/'docs/results/causal-closure-001/STARTED.json')
            start['source_hashes'][path]='0'*64
            with self.subTest(path=path), self.assertRaisesRegex(ValueError,'Changed predictor/observer/comparator source'):
                verify_sources(REPO,start,True)
