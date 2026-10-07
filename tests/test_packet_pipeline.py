"""Hand-derived pipeline times and adversarial independent readback."""
import copy
import unittest
from test_spatial import op,data
from test_wow_target import exported
from wafer_sim.adapters.packet_pipeline import contract
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.analysis.packet_pipeline import audit_pipeline
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.plan import Placement,Transfer
from wafer_sim.execution.packet_pipeline import PacketPipeline
from wafer_sim.execution.timing import execute
from wafer_sim.workloads.spatial import Workload


def fixture():
    export=exported()
    export['inputs']['booksim_config']=dict(mode='trace',num_vcs=1,packet_size=1,wait_for_tail_credit=0,
        hold_switch_for_packet=0,alloc_iters=1,priority='none',vc_allocator='separable_input_first',
        sw_allocator='separable_input_first')
    hardware,rates,_=build_wow_target(export,dict(scope='test',region_capacity_bytes=65536,
        compute_rates={'mac':4},memory_bytes_per_cycle=8),2000)
    workload=Workload((data('x',2001,'a'),data('y',8,'b',True)),
        (op('a',outputs=('x',)),op('b',inputs=('x',),outputs=('y',))))
    binding=bind(workload,hardware,Placement({'a':'compute-0','b':'compute-1'},{'x':'0','y':'1'}))
    return binding,rates,contract(export,2000),export


class PacketPipelineTests(unittest.TestCase):
    def run_messages(self,requests):
        binding,rates,model,_=fixture();network=PacketPipeline(TimedTarget(binding,rates),model)
        for i,(cycle,src,dst,size) in enumerate(requests):
            while network.now<cycle: network.advance(cycle)
            network.submit(str(i),Transfer(str(i),str(src),str(dst),src,dst,size),cycle)
        while network.pending: network.advance(10000)
        record=network.close()
        self.assertTrue(audit_pipeline(binding,rates,record['messages'],record['packet_services'],model)['passed'])
        return binding,rates,record

    def test_padding_head_latency_and_two_cycle_tail_spacing(self):
        for size,count in ((1,1),(2000,1),(2001,2),(6000,3)):
            _,_,r=self.run_messages([(0,0,1,size)])
            m=r['messages'][0]
            # Injection 7, link+router 7, destination+publication 11. Later packets every 2.
            self.assertEqual(m['expected_flits'],count)
            self.assertEqual(m['finish'],25+2*(count-1))
            self.assertEqual(m['last_inject']-m['first_inject'],count-1)

    def test_shared_output_contention_and_independent_directions(self):
        _,_,r=self.run_messages([(0,0,1,6000),(0,0,1,6000)])
        self.assertEqual([m['finish'] for m in r['messages']],[29,35])
        _,_,r=self.run_messages([(0,0,1,6000),(0,1,0,6000)])
        self.assertEqual([m['finish'] for m in r['messages']],[29,29])

    def test_idle_gap_and_partial_advance_do_not_complete_early(self):
        b,t,m,_=fixture();n=PacketPipeline(TimedTarget(b,t),m)
        n.submit('a',Transfer('x','0','1',0,1,2001),0)
        self.assertEqual(n.advance(26),[])
        with self.assertRaisesRegex(ValueError,'unfinished'): n.close()
        self.assertEqual(n.advance(27),['a'])
        n.advance(100)
        n.submit('b',Transfer('y','1','0',1,0,1),100)
        self.assertEqual(n.advance(1000),['b']);self.assertEqual(n.now,125)
        n.close()
        with self.assertRaises(ValueError): n.advance(1001)

    def test_pipeline_completion_controls_storage_and_critical_chain(self):
        b,t,m,_=fixture();n=PacketPipeline(TimedTarget(b,t),m)
        result=execute(b,t,network=n);n.close()
        self.assertTrue(audit(b,t,result)['passed'])
        self.assertEqual(result['network_backend'],'packet_pipeline')
        self.assertGreater(result['output_ready']['y'],result['network_messages'][0]['finish'])
        self.assertEqual(sum(critical_chain(b,result)['cycles'].values()),result['application_cycles'])

    def test_audit_rejects_false_service_completion_and_missing_packet(self):
        b,t,r=self.run_messages([(0,0,1,2001)])
        for field in ('finish','resource_released','start','ready'):
            changed=copy.deepcopy(r);changed['packet_services'][0][field]+=1
            with self.assertRaises(ValueError):
                audit_pipeline(b,t,changed['messages'],changed['packet_services'],changed['packet_contract'])
        changed=copy.deepcopy(r);changed['messages'][0]['flits'].pop()
        with self.assertRaises(ValueError): audit_pipeline(b,t,changed['messages'],changed['packet_services'],changed['packet_contract'])

    def test_unsupported_native_modes_are_not_silently_approximated(self):
        _,_,_,e=fixture()
        for key,value in (('mode','traffic'),('num_vcs',2),('packet_size',2),('wait_for_tail_credit',1),('speculative',1)):
            changed=copy.deepcopy(e);changed['inputs']['booksim_config'][key]=value
            with self.assertRaises(ValueError): contract(changed,2000)
