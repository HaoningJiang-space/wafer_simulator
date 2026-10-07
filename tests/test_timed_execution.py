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

    def test_fixed_work_changes_time_only_through_declared_rates(self):
        config=read_json(Path(__file__).resolve().parents[1]/"configs/timed_execution_example.json")
        original=run_case(config,"declared")
        for case,expected in (("double_compute_rate",99),("double_memory_rate",97),("double_network_rate",93)):
            changed=run_case(config,case)
            self.assertEqual(changed["workload"],original["workload"])
            self.assertEqual(changed["placement"],original["placement"])
            self.assertEqual(changed["result"]["application_cycles"],expected)
            self.assertTrue(changed["audit"]["passed"])
