"""Hand-calculated target timing and independent full-event checks."""
import copy
from dataclasses import replace
from pathlib import Path
import unittest

from test_spatial import data,op,target
from wafer_sim.architecture.timing import Service, Link, Endpoint, Timing
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.timing import Step,TimedTarget
from wafer_sim.execution.plan import Placement, Phase, Transfer
from wafer_sim.execution.timing import ResourceCalendar,execute
from wafer_sim.analysis.timing import audit
from wafer_sim.experiments.timed_example import run_case
from wafer_sim.io import read_json
from wafer_sim.workloads.spatial import Workload


def timing():
    return Timing((Service("compute-A","mac",3),Service("compute-B","mac",3),
        Service("A-port","bytes",4),Service("B-read","bytes",4),Service("B-write","bytes",4)),
        (Link(10,11,Service("10->11","bytes",4,latency_cycles=3)),
         Link(11,10,Service("11->10","bytes",4,latency_cycles=3))),
        (Endpoint(0,Service("inject-0","bytes",8),Service("eject-0","bytes",8)),
         Endpoint(1,Service("inject-1","bytes",8),Service("eject-1","bytes",8))),
        "Analytical service rates, not calibrated hardware")


def local_binding():
    w = Workload((data("x",8),data("y",4,"f",True)),(op("f",("x",),("y",)),))
    return bind(w,target(),Placement({"f":"compute-A"},{"x":"A","y":"A"}))


class CalendarTests(unittest.TestCase):
    def test_memory_bursts_rejoin_fcfs_without_reserving_future_bandwidth(self):
        clock=ResourceCalendar({('port','bytes'):Service('port','bytes',2)},memory_quantum_bytes=4)
        done={}
        for name,amount in (('a',10),('b',4)):
            clock.submit(name,(Step('port','bytes',amount,'memory'),),
                         lambda name=name:done.update({name:clock.now}))
        while clock.events:clock.advance()
        self.assertEqual(done,{'b':4,'a':7})
        self.assertEqual([(r['token'],r['amount'],r['start'],r['finish']) for r in clock.records],
                         [('a',4,0,2),('b',4,2,4),('a',4,4,6),('a',2,6,7)])
        self.assertEqual(clock.resource_summary()['port']['busy_cycles'],7)

    def test_burst_tail_latency_and_other_service_categories(self):
        services={('p','bytes'):Service('p','bytes',2,latency_cycles=2),
                  ('n','bytes'):Service('n','bytes',2),('c','mac'):Service('c','mac',2)}
        clock=ResourceCalendar(services,memory_quantum_bytes=3);done={}
        for name,step in (('m',Step('p','bytes',8,'memory')),
                          ('n',Step('n','bytes',8,'network')),('c',Step('c','mac',8,'compute'))):
            clock.submit(name,(step,),lambda name=name:done.update({name:clock.now}))
        while clock.events:clock.advance()
        self.assertEqual(done,{'n':4,'c':4,'m':11})
        self.assertEqual([r['amount'] for r in clock.records if r['token']=='m'],[3,3,2])
        self.assertEqual(len([r for r in clock.records if r['token']=='n']),1)
        self.assertEqual(len([r for r in clock.records if r['token']=='c']),1)

    def test_invalid_memory_quantum_rejected(self):
        for quantum in (0,-1,True,1.5):
            with self.assertRaises(ValueError):ResourceCalendar({},memory_quantum_bytes=quantum)

    def test_shared_port_never_supplies_full_rate_to_two_clients(self):
        clock = ResourceCalendar({("port","bytes"):Service("port","bytes",4)})
        finish = {}
        for name in ("a","b"):
            clock.submit(name,(Step("port","bytes",16,"memory"),),lambda name=name:finish.update({name:clock.now}))
        while clock.events: clock.advance()
        self.assertEqual(finish,{"a":4,"b":8})
        self.assertEqual(clock.records[1]["start"],4)
        self.assertEqual(clock.records[1]["resource_predecessor"],0)

    def test_propagation_does_not_hold_link_bandwidth(self):
        clock = ResourceCalendar({("link","bytes"):Service("link","bytes",4,latency_cycles=10)})
        finish = []
        for name in ("a","b"):
            clock.submit(name,(Step("link","bytes",4,"network"),),lambda:finish.append(clock.now))
        while clock.events: clock.advance()
        self.assertEqual(finish,[11,12])
        self.assertEqual(clock.resource_summary()["link"]["busy_cycles"],2)

    def test_rational_rates_round_up_without_floating_point_drift(self):
        clock = ResourceCalendar({("compute","mac"):Service("compute","mac",3,2)})
        clock.submit("x",(Step("compute","mac",5,"compute"),),lambda:None)
        clock.advance()
        self.assertEqual(clock.now,4)

    def test_two_flows_contend_on_shared_directed_link(self):
        b = local_binding(); t = TimedTarget(b,timing())
        phase = Phase("transfer",transfer=Transfer("x","A","B",0,1,16))
        clock = ResourceCalendar(t.services)
        finish = {}
        for name in ("a","b"):
            clock.submit(name,t.steps(phase),lambda name=name:finish.update({name:clock.now}))
        while clock.events: clock.advance()
        self.assertEqual(finish,{"a":11,"b":15})
        self.assertEqual(clock.resource_summary()["10->11"]["queue_wait_cycles"],2)

    def test_independent_directions_overlap(self):
        b=local_binding(); t=TimedTarget(b,timing()); clock=ResourceCalendar(t.services)
        for src,dst in ((0,1),(1,0)):
            phase=Phase("transfer",transfer=Transfer("x","A","B",src,dst,16))
            clock.submit(str(src),t.steps(phase),lambda:None)
        while clock.events: clock.advance()
        self.assertEqual(clock.now,11)

    def test_incomplete_timing_fails_before_execution(self):
        b=local_binding(); t=timing()
        for bad in (replace(t,links=()),replace(t,endpoints=()),replace(t,services=t.services[1:])):
            with self.assertRaises(ValueError): execute(b,bad)
        with self.assertRaises(ValueError):
            execute(b,replace(t,services=(Service("compute-A","mac",0),*t.services[1:])))


class TimedExecutionTests(unittest.TestCase):
    def test_independent_burst_readback_and_policy_tampering(self):
        b=local_binding();t=timing()
        result=execute(b,t,memory_quantum_bytes=3)
        self.assertEqual(result['application_cycles'],9)
        self.assertTrue(audit(b,t,result)['passed'])
        self.assertEqual([e['amount'] for e in result['services'] if e['category']=='memory'],[3,3,2,3,1])
        broken=copy.deepcopy(result);broken['policy'].pop('memory_quantum_bytes')
        with self.assertRaisesRegex(ValueError,'conservation'):audit(b,t,broken)
        broken=copy.deepcopy(result);broken['policy']['memory_quantum_bytes']=True
        with self.assertRaisesRegex(ValueError,'quantum'):audit(b,t,broken)
        with self.assertRaises(TimeoutError):execute(b,t,memory_quantum_bytes=3,cycle_limit=8)
        self.assertTrue(execute(b,t,memory_quantum_bytes=3,cycle_limit=9)['complete'])

    def test_cycle_limit_is_inclusive_for_local_and_external_network(self):
        class IdleNetwork:
            now = 0
            messages = []
            def advance(self, until):
                self.now = until
                return []
        for external in (False, True):
            for limit in (1, 6):
                with self.assertRaises(TimeoutError):
                    execute(local_binding(), timing(), network=IdleNetwork() if external else None,
                            cycle_limit=limit)
            result = execute(local_binding(), timing(), network=IdleNetwork() if external else None,
                             cycle_limit=7)
            self.assertTrue(result['complete'])
            self.assertEqual(result['application_cycles'], 7)
        for bad in (0, -1, True, 1.5):
            with self.assertRaises(ValueError): execute(local_binding(), timing(), cycle_limit=bad)

    def test_compute_tasks_share_or_overlap_by_physical_resource(self):
        w=Workload((),(op("a"),op("b")))
        for second,expected in (("compute-A",8),("compute-B",4)):
            b=bind(w,target(),Placement({"a":"compute-A","b":second},{}))
            result=execute(b,timing())
            self.assertEqual(result["application_cycles"],expected)
            self.assertTrue(audit(b,timing(),result)["passed"])

    def test_read_compute_write_time_is_computed_by_target(self):
        b=local_binding(); result=execute(b,timing())
        # 8 B / 4 + 12 MAC / 3 + 4 B / 4 = 7 cycles.
        self.assertEqual(result["application_cycles"],7)
        self.assertEqual([p["finish"] for p in result["phases"]],[2,6,7])
        self.assertTrue(audit(b,timing(),result)["passed"])
        faster=replace(timing(),services=(Service("compute-A","mac",6),*timing().services[1:]))
        self.assertEqual(execute(b,faster)["application_cycles"],5)

    def test_consumer_waits_for_remote_write_and_producer_completion(self):
        w=Workload((data("x",8,"a"),),(op("a",outputs=("x",)),op("b",inputs=("x",))))
        b=bind(w,target(),Placement({"a":"compute-A","b":"compute-B"},{"x":"B"}))
        result=execute(b,timing())
        self.assertEqual(result["operations"]["b"]["admitted"],result["operations"]["a"]["finish"])
        rows=[p for p in result["phases"] if p["operation"]=="a"]
        self.assertEqual(rows[-1]["kind"],"memory_write")
        self.assertGreater(rows[-1]["finish"],rows[-2]["finish"])
        self.assertTrue(audit(b,timing(),result)["passed"])

    def test_capacity_waits_then_recovers_when_last_consumer_finishes(self):
        w=Workload((data("hold",16),data("out",16,"produce",True)),
                   (op("release",("hold",)),op("produce",outputs=("out",))))
        b=bind(w,target(32,16),Placement({"release":"compute-A","produce":"compute-A"},
                                        {"hold":"B","out":"B"}))
        result=execute(b,timing())
        self.assertTrue(result["complete"])
        self.assertEqual(result["operations"]["produce"]["admitted"],result["operations"]["release"]["finish"])
        self.assertGreater(result["operations"]["produce"]["capacity_wait_cycles"],0)
        self.assertTrue(audit(b,timing(),result)["passed"])

    def test_permanent_shortage_is_incomplete_not_zero_time_success(self):
        w=Workload((data("x",16),data("y",16,"f")),(op("f",("x",),("y",)),))
        b=bind(w,target(16,16),Placement({"f":"compute-A"},{"x":"A","y":"A"}))
        result=execute(b,timing())
        self.assertFalse(result["complete"])
        self.assertIsNone(result["application_cycles"])
        self.assertEqual(result["blocked"]["f"]["shortage_bytes"],(("A",16),))
        with self.assertRaisesRegex(ValueError,"Incomplete"): audit(b,timing(),result)

    def test_independent_reader_rejects_missing_work_and_changed_rate(self):
        b=local_binding(); original=execute(b,timing())
        for field,value in (("amount",4),("finish",99),("resource_released",99)):
            changed=copy.deepcopy(original); changed["services"][0][field]=value
            with self.assertRaises(ValueError): audit(b,timing(),changed)
        changed=copy.deepcopy(original); changed["lifecycle"][0]["used_bytes"]["A"]=999
        with self.assertRaises(ValueError): audit(b,timing(),changed)
        changed=copy.deepcopy(original); changed["services"][0]["category"]="compute"
        with self.assertRaisesRegex(ValueError,"category"): audit(b,timing(),changed)
        changed=copy.deepcopy(original); changed["resources"]["A-port"]["queue_wait_cycles"]=99
        with self.assertRaisesRegex(ValueError,"summary"): audit(b,timing(),changed)

    def test_complete_example_has_hand_derived_113_cycle_schedule(self):
        config=read_json(Path(__file__).resolve().parents[1]/"configs/timed_execution_example.json")
        record=run_case(config,"declared")
        result=record["result"]
        self.assertEqual({name:row["finish"] for name,row in result["operations"].items()},
                         {"A":12,"B0":52,"B1":56,"AllReduce":105,"C0":113,"C1":113})
        self.assertEqual(result["application_cycles"],113)
        self.assertGreater(result["resources"]["memory-0"]["queue_wait_cycles"],0)
        self.assertGreater(result["resources"]["link-10-11"]["queue_wait_cycles"],0)
        self.assertEqual(result["storage"]["used_bytes"],{"0":0,"1":16,"2":16})

    def test_accepted_example_events_are_unchanged(self):
        root=Path(__file__).resolve().parents[1]
        config=read_json(root/"configs/timed_execution_example.json")
        accepted=read_json(root/"docs/results/timed-execution-001/declared.json")
        current=run_case(config,"declared")
        # Project only the newly added readiness/retirement annotations away;
        # every historical service, phase, admission and release stays exact.
        legacy=copy.deepcopy(current["result"])
        legacy.pop("output_ready")
        for row in legacy["operations"].values():
            self.assertEqual(row.pop("retired"),row["finish"])
        legacy["lifecycle"]=[dict(e,event="complete") if e["event"]=="retire" else e
                             for e in legacy["lifecycle"] if e["event"]!="output_ready"]
        self.assertEqual(legacy,accepted["result"])

    def test_audit_checks_terminal_state_and_capacity_wait(self):
        b=local_binding(); original=execute(b,timing())
        changes = [(["operations","f","capacity_wait_cycles"],99),
                   (["storage","available_data"],[]),
                   (["storage","completed"],[]),
                   (["storage","all_operations_completed"],False),
                   (["stopped_cycle"],99)]
        for path,value in changes:
            changed=copy.deepcopy(original); node=changed
            for key in path[:-1]: node=node[key]
            node[path[-1]]=value
            with self.assertRaises(ValueError): audit(b,timing(),changed)

    def test_audit_rejects_non_fcfs_service_order(self):
        # Two independent equal tasks on one server: invert their service order
        # while preserving all durations, dependencies, capacity and non-overlap.
        w=Workload((),(op("a"),op("b")))
        b=bind(w,target(),Placement({"a":"compute-A","b":"compute-A"},{}))
        changed=execute(b,timing())
        a,z=changed["services"]
        for key in ("start","resource_released","finish","resource_predecessor"):
            a[key],z[key]=z[key],a[key]
        a["resource_predecessor"]=1
        with self.assertRaisesRegex(ValueError,"FCFS"): audit(b,timing(),changed)

    def test_audit_rejects_false_predecessor_on_idle_resource(self):
        b=local_binding(); result=execute(b,timing())
        result["services"][0]["resource_predecessor"]=0
        with self.assertRaisesRegex(ValueError,"FCFS"): audit(b,timing(),result)

    def test_audit_rejects_valid_but_wrong_tie_route(self):
        hardware=target()
        edges=((10,20),(20,11),(10,21),(21,11))
        hardware=replace(hardware,network=replace(hardware.network,router_links=edges))
        w=Workload((data("x",8),),(op("f",("x",)),))
        b=bind(w,hardware,Placement({"f":"compute-A"},{"x":"B"}))
        rates=replace(timing(),links=tuple(Link(a,z,Service(f"{a}->{z}","bytes",4))
                    for x,y in edges for a,z in ((x,y),(y,x))))
        result=execute(b,rates)
        self.assertTrue(audit(b,rates,result)["passed"])
        row=next(p for p in result["phases"] if p["kind"]=="transfer")
        self.assertEqual(row["path"],(11,20,10))
        row["path"]=(11,21,10)
        # Keep the alternate physical route internally consistent. The older
        # conservation-only audit accepted this equal-hop, wrong-tie route.
        replacements={"11->20":"11->21", "20->10":"21->10"}
        for event in result["services"]:
            if event["resource"] in replacements:
                event["resource"]=replacements[event["resource"]]
        for old,new in replacements.items():
            result["resources"][new]=result["resources"].pop(old)
        with self.assertRaisesRegex(ValueError,"route policy"): audit(b,rates,result)

    def test_fixed_work_changes_time_only_through_declared_rates(self):
        config=read_json(Path(__file__).resolve().parents[1]/"configs/timed_execution_example.json")
        original=run_case(config,"declared")
        for case,expected in (("double_compute_rate",99),("double_memory_rate",97),("double_network_rate",93)):
            changed=run_case(config,case)
            self.assertEqual(changed["workload"],original["workload"])
            self.assertEqual(changed["placement"],original["placement"])
            self.assertEqual(changed["result"]["application_cycles"],expected)
            self.assertTrue(changed["audit"]["passed"])
