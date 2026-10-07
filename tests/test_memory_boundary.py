"""Remote native boundary regressions; complete mechanism units, not applications."""
import copy
from dataclasses import replace
import os
from pathlib import Path
import unittest

import test_online_booksim
from test_collective_timing import case
from wafer_sim.adapters import wow
from wafer_sim.adapters.boundary_booksim import BoundaryBookSim
from wafer_sim.adapters.memory_boundary import reserve_endpoint_storage,fuse_movements
from wafer_sim.execution.memory_boundary import MemoryBoundary
from wafer_sim.execution.plan import Transfer
from wafer_sim.execution.timing import execute
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.memory_boundary import audit_occupancy
from wafer_sim.experiments.network_reference import compare_reference


class MemoryBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path('/home/wangziheng/wafer_simulator')
        cls.output=Path(os.environ['WAFER_ONLINE_TEST_OUTPUT']+'-boundary');cls.output.mkdir(exist_ok=False)
        cls.binary=cls.root/'build/booksim-boundary/endpoint_booksim'
        cls.reference=cls.root/'build/booksim/rapidchiplet/booksim2/src/booksim'
        wow.load_upstream(cls.root/'upstream/nw-design-for-wsi')
    prepare=test_online_booksim.OnlineBookSimTests.prepare

    def test_transparent_hooks_restore_original_native_timestamps(self):
        directory,inputs,config=self.prepare('transparent')
        client=BoundaryBookSim(self.binary,config,directory,flit_bytes=4)
        try:
            client.configure(rx_slots=2,bounded=False,streaming=False)
            client.submit('x',Transfer('x','0','2',0,2,65),0)
            while client.pending:client.advance(10000)
            record=client.close()
        finally:client.abort()
        self.assertTrue(compare_reference(inputs,directory,directory/'reference',self.reference,record['messages'],1)['passed'])

    def test_unsupplied_data_and_withheld_credits_block_native_progress(self):
        directory,_,config=self.prepare('credits')
        client=BoundaryBookSim(self.binary,config,directory,flit_bytes=4)
        received=[]
        try:
            client.configure(rx_slots=2,bounded=True)
            client.submit('x',Transfer('x','0','2',0,2,32),0)
            client.advance(20)
            self.assertFalse(client.progress)
            for _ in range(8):client.supply(0)
            while client.now<300:
                client.advance(300)
                received.extend(e for e in client.progress if e['event']=='receive')
            self.assertEqual(len(received),2)
            client.commit(received[0]['flit'])
            before=len(received)
            while len(received)==before and client.now<600:
                client.advance(600)
                received.extend(e for e in client.progress if e['event']=='receive')
            self.assertEqual(len(received),3)
            client.commit(received[1]['flit']);client.commit(received[2]['flit'])
            while client.pending:
                client.advance(10000)
                for e in client.progress:
                    if e['event']=='receive':client.commit(e['flit'])
            client.close()
        finally:client.abort()

    def run_collective(self, name, mode, limit=100000, delayed=False):
        directory,_,config=self.prepare(name,nodes=4)
        binding,rates=case(4)
        if delayed:
            from wafer_sim.workloads.spatial import Workload,Operation,validate
            from wafer_sim.execution.plan import OperationPlan,Phase,Demand
            precursor=Operation('prepare',(),(),(('scalar_add',10),),0,(),'fixture')
            graph=validate(Workload(tuple(binding.graph.data.values()),
                (precursor,replace(binding.graph.operations['sum'],control_deps=('prepare',)))))
            plans={'prepare':OperationPlan((),(Phase('compute',(Demand('compute-0','scalar_add',10),)),)),**binding.plans}
            binding=replace(binding,graph=graph,plans=plans)
        binding=reserve_endpoint_storage(binding,4,2,2)
        client=BoundaryBookSim(self.binary,config,directory,flit_bytes=4)
        controller=client
        if mode=='serial':client.configure(rx_slots=2,bounded=False,streaming=False)
        else:
            binding,_=fuse_movements(binding)
            controller=MemoryBoundary(client,tx_slots=2,rx_slots=2,bounded=mode=='bounded')
        try:
            result=execute(binding,rates,network=controller,cycle_limit=limit)
            controller.close()
        finally:controller.abort()
        self.assertTrue(audit(binding,rates,result)['passed'])
        from wafer_sim.analysis.timed_attribution import critical_chain
        critical_chain(binding,result)
        return binding,rates,result

    def test_complete_collective_conserves_memory_network_and_lifetimes(self):
        serial=self.run_collective('serial','serial')[2]
        for mode in ('pipeline','bounded'):
            binding,rates,result=self.run_collective(mode,mode)
            self.assertEqual(len(result['network_messages']),6)
            self.assertEqual(sum(m['bytes'] for m in result['network_messages']),48)
            self.assertEqual(sum(s['amount'] for s in result['services'] if s['category']=='memory'),
                             sum(s['amount'] for s in serial['services'] if s['category']=='memory'))
            self.assertTrue(audit_occupancy(result['boundary'])['passed'])
            broken=copy.deepcopy(result);broken['boundary']['moves'][0]['packets'][0]['supplied']=0
            with self.assertRaises(ValueError):audit(binding,rates,broken)
            broken=copy.deepcopy(result);broken['boundary']['events'][0]['tx_slots']+=1
            with self.assertRaises(ValueError):audit(binding,rates,broken)

    def test_native_and_boundary_accept_exact_deadline(self):
        for mode in ('serial','bounded'):
            limit=self.run_collective(mode+'-measure',mode)[2]['application_cycles']
            self.run_collective(mode+'-equal',mode,limit)
            with self.assertRaises(TimeoutError):self.run_collective(mode+'-short',mode,limit-1)

    def test_local_work_before_first_network_movement(self):
        _,_,result=self.run_collective('delayed','bounded',delayed=True)
        self.assertEqual(result['operations']['prepare']['finish'],5)
        self.assertEqual(result['operations']['sum']['admitted'],5)

    def test_buffer_storage_is_charged_and_ambiguous_fusion_rejected(self):
        binding,_=case(4)
        carved=reserve_endpoint_storage(binding,4,2,2)
        for key in binding.memory:
            self.assertEqual(carved.memory[key].capacity_bytes,binding.memory[key].capacity_bytes-16)
        with self.assertRaises(ValueError):reserve_endpoint_storage(binding,100000,2,2)
        op=next(iter(binding.plans));plan=binding.plans[op]
        i=next(i for i,p in enumerate(plan.phases) if p.transfer)
        deps=list(plan.dependencies);deps[i]=()
        bad=replace(binding,plans={op:replace(plan,dependencies=tuple(deps))})
        with self.assertRaises(ValueError):fuse_movements(bad)
