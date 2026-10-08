"""Physical legality and independent transaction/lifetime checks; remote only."""
from dataclasses import replace
import copy
from pathlib import Path
import unittest

from wafer_sim.io import read_json
from wafer_sim.architecture.wafer_machine import from_config,validate
from wafer_sim.adapters.wafer_machine import compile_machine,bind_machine,CONTROL_BYTES
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.analysis.timing import audit
from wafer_sim.execution.timing import execute
from wafer_sim.execution.plan import Placement
from wafer_sim.workloads.memory_machine import build,place_data
from wafer_sim.workloads.spatial import Workload,DataObject,Operation


def machine():
    cfg=read_json(Path(__file__).resolve().parents[1]/'configs/wafer_machine.json')
    cfg['array']=[2,2]
    return from_config(cfg)


def one_read(home='dram-0-0'):
    w=Workload((DataObject('x',64,None,False,'test'),DataObject('y',64,'f',True,'test')),
        (Operation('f',('x',),('y',),(('mac',256),),0,(),'test'),))
    p=Placement({'f':'c0'},{'x':home,'y':'sram-0'})
    c=compile_machine(machine());b,tx=bind_machine(w,c,p)
    return c,b,tx


class WaferMachineTests(unittest.TestCase):
    def test_unstitched_machine_cannot_keep_direct_lateral_links(self):
        with self.assertRaisesRegex(ValueError,'stitching'):
            validate(replace(machine(),technology='unstitched_compute_hb_memory'))

    def test_memory_wafer_does_not_inherit_interconnect_transit(self):
        m=machine();link=replace(m.connections[0],id='illegal',source='m0',destination='m1')
        with self.assertRaisesRegex(ValueError,'compute wafer'):
            validate(replace(m,connections=m.connections+(link,)))

    def test_hb_alignment_budget_and_router_radix_rejected(self):
        m=machine()
        for bad in (replace(m.tiles[1],x_um=m.tiles[1].x_um+1),
                    replace(m.tiles[1],hb_signal_budget=10),replace(m.tiles[1],max_ports=1)):
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                validate(replace(m,tiles=(m.tiles[0],bad,*m.tiles[2:])))

    def test_wire_latency_and_wafer_extent_checked(self):
        m=machine()
        with self.assertRaisesRegex(ValueError,'pipeline'):
            validate(replace(m,connections=(replace(m.connections[0],latency_cycles=1),*m.connections[1:])))
        with self.assertRaisesRegex(ValueError,'outside wafer'):
            validate(replace(m,wafer_diameter_um=10000))

    def test_distinct_banks_share_explicit_controller_channel(self):
        c=compile_machine(machine())
        s={x.id:x for x in c.physical.stores}
        self.assertEqual(s['dram-0-0'].controller,s['dram-0-1'].controller)
        self.assertNotEqual(s['dram-0-0'].id,s['dram-0-1'].id)
        self.assertEqual(sum(x.resource=='controller-0/channel' for x in c.timing.services),1)

    def test_read_request_precedes_bank_and_response(self):
        c,b,tx=one_read();ph=b.plans['f'].phases
        self.assertEqual((ph[0].transfer.source_memory,ph[0].transfer.destination_memory),('sram-0','dram-0-0'))
        self.assertEqual(ph[0].transfer.size_bytes,CONTROL_BYTES)
        self.assertEqual(ph[2].demands[0].resource,'dram-0-0/port')
        self.assertEqual(ph[4].transfer.size_bytes,64)
        r=execute(b,c.timing);self.assertTrue(audit(b,c.timing,r)['passed'])
        # Independent serial calculation: request 2+6+6=14; command4;
        # bank2+30; channel1; response14; staging write1; local read1;
        # compute1; final write1 = 69 cycles.
        self.assertEqual(r['application_cycles'],69)

    def test_remote_read_uses_horizontal_and_vertical_links(self):
        c,b,_=one_read('dram-3-0');t=TimedTarget(b,c.timing)
        response=b.plans['f'].phases[4].transfer
        path=t.route(response.source_endpoint,response.destination_endpoint)
        self.assertEqual(len(path)-1,3)
        self.assertEqual(path[0],c.router_ids['m3'])
        self.assertEqual(path[-1],c.router_ids['c0'])

    def test_write_waits_for_bank_commit_and_ack(self):
        c,_,_=one_read()
        w=Workload((DataObject('x',64,None,False,'t'),DataObject('y',64,'f',True,'t')),
            (Operation('f',('x',),('y',),(('mac',256),),0,(),'t'),))
        b,_=bind_machine(w,c,Placement({'f':'c0'},{'x':'sram-0','y':'dram-1-0'}))
        self.assertEqual(b.plans['f'].phases[-1].transfer.source_memory,'dram-1-0')
        r=execute(b,c.timing);self.assertTrue(audit(b,c.timing,r)['passed'])
        self.assertEqual(r['output_ready']['y'],r['application_cycles'])
        self.assertGreater(r['application_cycles'],r['phases'][-2]['finish'])

    def test_capacity_and_controller_staging_not_free(self):
        c,b,_=one_read()
        m=machine();m=replace(m,controllers=tuple(replace(x,buffer_bytes=32) for x in m.controllers))
        c=compile_machine(m)
        w=Workload((DataObject('x',64,None,False,'t'),DataObject('y',64,'f',True,'t')),
            (Operation('f',('x',),('y',),(('mac',1),),0,(),'t'),))
        b,_=bind_machine(w,c,Placement({'f':'c0'},{'x':'dram-0-0','y':'sram-0'}))
        r=execute(b,c.timing)
        self.assertFalse(r['complete'])
        self.assertEqual(r['blocked']['f']['shortage_bytes']['controller-0/buffer'],32)

    def test_data_placement_keeps_logical_work_and_compute_unchanged(self):
        w,p,meta=build(4,8,16)
        self.assertEqual(meta['macs'],2*4*8*16*16)
        c=compile_machine(machine())
        for mode in ('near','opposite','single_controller'):
            pp=place_data(p,4,mode);self.assertEqual(pp.compute,p.compute)
            b,tx=bind_machine(w,c,pp);r=execute(b,c.timing)
            self.assertTrue(audit(b,c.timing,r)['passed'])
            self.assertEqual(sum(t['kind']=='c2c' for t in tx),4)
            self.assertEqual(sum(t['kind']=='read' for t in tx),9)
            self.assertEqual(sum(t['kind']=='write' for t in tx),4)

    def test_lost_ack_and_early_publication_fail_independent_audit(self):
        w,p,_=build(4,8,16);c=compile_machine(machine());b,_=bind_machine(w,c,p)
        result=execute(b,c.timing);bad=copy.deepcopy(result)
        bad['output_ready']['y0']-=1
        with self.assertRaises(ValueError):audit(b,c.timing,bad)

    def test_same_bank_and_controller_are_shared_not_replicated(self):
        w,p,_=build(4,8,16);p=place_data(p,4,'single_controller')
        c=compile_machine(machine());b,_=bind_machine(w,c,p);r=execute(b,c.timing)
        self.assertTrue(audit(b,c.timing,r)['passed'])
        self.assertGreater(r['resources']['controller-0/channel']['queue_wait_cycles'],0)
        self.assertEqual(r['resources']['controller-0/command']['work']['bytes'],(8+4)*16)
