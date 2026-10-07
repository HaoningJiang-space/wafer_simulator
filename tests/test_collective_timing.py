"""Hand-derived collective service, concurrent requests and finite lifetimes."""
from dataclasses import replace
from types import MappingProxyType
import copy
import unittest

from wafer_sim.adapters.declared_target import build_target
from wafer_sim.adapters.spatial import bind
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.analysis.collective_contention import summarize
from wafer_sim.execution.plan import Placement
from wafer_sim.execution.storage import StorageState
from wafer_sim.execution.timing import execute
from wafer_sim.workloads.collectives import Collective, Slot
from wafer_sim.workloads.spatial import DataObject, Operation, Workload


def case(n=2, capacity=128):
    members = tuple(range(n))
    inputs = tuple(f"x{r}" for r in members)
    outputs = tuple(f"y{r}" for r in members)
    collective = Collective("sum", "allreduce", members, (Slot(2,2,4,"float32"),), "sum", None, "fixture")
    workload = Workload(tuple(DataObject(d,8,None,False,"fixture") for d in inputs) +
                        tuple(DataObject(d,8,"sum",True,"fixture") for d in outputs),
        (Operation("sum",inputs,outputs,(("scalar_add",2*(n-1)),),0,(),"fixture",collective),))
    config = dict(scope="fixture",region_capacity_bytes=capacity,compute_rates={"scalar_add":2},
        memory_bytes_per_cycle=4,endpoint_routers=tuple((r,r) for r in members),
        router_links=tuple((r,r+1) for r in range(n-1)),link_bytes_per_cycle=4,
        endpoint_bytes_per_cycle=4,link_latency_cycles=0)
    target,timing = build_target(config)
    placement = Placement({"sum":"compute-0"},{d:str(r) for r in members for d in (inputs[r],outputs[r])})
    return bind(workload,target,placement),timing


class CollectiveTimingTests(unittest.TestCase):
    def test_router_residence_uses_actual_path_and_does_not_count_link_latency_as_wait(self):
        export=dict(resources=dict(router_latency_cycles=4),inputs=dict(
            links=[dict(src=0,dst=1,latency=5)],chiplets={"c":dict(unit_to_router_latency=6)},
            placement=dict(chiplets=[dict(name="c"),dict(name="c")])) )
        flit=dict(id=0,injected=0,ejected=26,injection_router_arrival=7,
                  router_path=[0,1],link_arrivals=[dict(source=0,destination=1,cycle=16)])
        message=dict(id=0,token="x",source=0,destination=1,ready=0,finish=27,first_inject=0,flits=[flit])
        self.assertEqual(summarize(export,[message])["first_flit_router_excess_cycles"],0)
        flit["link_arrivals"][0]["cycle"]+=2;flit["ejected"]+=2;message["finish"]+=2
        observed=summarize(export,[message])
        self.assertEqual(observed["first_flit_router_excess_cycles"],2)
        self.assertEqual(observed["messages"][0]["router_residence"],
                         [dict(router=0,excess_cycles=2),dict(router=1,excess_cycles=0)])

    def test_collective_byte_and_reduction_contract_cannot_be_inferred_from_duration(self):
        binding,_=case()
        op=binding.graph.operations["sum"]
        from wafer_sim.workloads.spatial import validate
        bad=replace(op,work=(("scalar_add",1),))
        with self.assertRaisesRegex(ValueError,"mathematical work"):
            validate(Workload(tuple(binding.graph.data.values()),(bad,)))

    def test_root_materializes_one_result_and_retains_original_work(self):
        binding,timing = case()
        plan = binding.plans["sum"]
        result = plan.phases[plan.action_ids.index("0/result/0")]
        self.assertEqual(sum(d.amount for d in result.demands),8)
        self.assertEqual(sum(d.amount for p in plan.phases for d in p.demands if p.kind=="memory_write"),24)
        self.assertEqual(sum(d.amount for p in plan.phases for d in p.demands if p.kind=="compute"),2)
        self.assertEqual(sum(a.size_bytes for a in plan.reservations if a.memory=="0"),16)
        self.assertEqual({p.transfer.data for p in plan.phases if p.transfer},{"x1","y0"})

    def test_two_rank_hand_schedule_and_serial_action_control(self):
        binding,timing = case()
        result=execute(binding,timing)
        self.assertEqual(result["application_cycles"],25)
        self.assertTrue(audit(binding,timing,result)["passed"])
        self.assertEqual(sum(critical_chain(binding,result)["cycles"].values()),25)
        plan=binding.plans["sum"]
        serial=replace(plan,dependencies=tuple((i-1,) if i else () for i in range(len(plan.phases))))
        serial_binding=replace(binding,plans=MappingProxyType({"sum":serial}))
        self.assertEqual(execute(serial_binding,timing)["application_cycles"],27)
        self.assertEqual(result["storage"]["available_data"],["y0","y1"])
        self.assertEqual(result["storage"]["used_bytes"],{"0":8,"1":8})

    def test_three_gathers_enter_before_any_has_finished(self):
        binding,timing=case(4)
        result=execute(binding,timing)
        gathers=[p for p in result["phases"] if p.get("action","").startswith("0/chunk/") and p["kind"]=="transfer"]
        self.assertEqual(len(gathers),3)
        self.assertEqual({p["ready"] for p in gathers},{2})
        self.assertGreater(min(p["finish"] for p in gathers),max(p["ready"] for p in gathers))
        self.assertTrue(audit(binding,timing,result)["passed"])
        self.assertEqual(sum(critical_chain(binding,result)["cycles"].values()),result["application_cycles"])

    def test_action_cannot_complete_before_start_or_publish_before_final_write(self):
        binding,_=case()
        state=StorageState(binding);state.try_begin("sum")
        plan=binding.plans["sum"]
        with self.assertRaises(ValueError):state.complete_phase("sum",0)
        final=plan.action_ids.index("0/broadcast/1/write")
        while True:
            ready=[i for i in state.ready_phases("sum") if i!=final]
            if not ready: break
            for i in ready:state.begin_phase("sum",i);state.complete_phase("sum",i)
        self.assertNotIn("y0",state.available)
        self.assertIn("x1",state.available)
        self.assertTrue(any(k[0]=="collective_stage" for k in state.allocations))
        state.begin_phase("sum",final);state.complete_phase("sum",final)
        self.assertEqual(state.available,{"y0","y1"})
        self.assertFalse(any(k[0]=="collective_stage" for k in state.allocations))

    def test_capacity_shortage_reserves_nothing_and_reports_incomplete(self):
        binding,timing=case(4,24)
        result=execute(binding,timing)
        self.assertFalse(result["complete"])
        self.assertIsNone(result["application_cycles"])
        self.assertEqual(result["storage"]["used_bytes"],{str(r):8 for r in range(4)})

    def test_readback_rejects_missing_dependency_or_early_completion(self):
        binding,timing=case()
        result=execute(binding,timing)
        broken=copy.deepcopy(result)
        phase=next(p for p in broken["phases"] if p["action"]=="0/result/0")
        phase["predecessors"]=()
        with self.assertRaisesRegex(ValueError,"dependencies"):audit(binding,timing,broken)
        broken=copy.deepcopy(result);broken["operations"]["sum"]["finish"]-=1
        with self.assertRaisesRegex(ValueError,"last phase"):audit(binding,timing,broken)

    def test_malformed_action_dag_is_rejected_before_time_advances(self):
        binding,timing=case()
        plan=binding.plans["sum"]
        plan=replace(plan,dependencies=((1,),)+plan.dependencies[1:])
        with self.assertRaisesRegex(ValueError,"Action DAG"):
            execute(replace(binding,plans={"sum":plan}),timing)
