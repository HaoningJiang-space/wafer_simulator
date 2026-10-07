"""Native interface regressions; all compilation/execution belongs on eex005."""
import copy
from dataclasses import replace
import os
from pathlib import Path
import unittest

from test_semantics import tiny_inputs
from test_spatial import data,op,target
from test_timed_execution import timing
from test_collective_timing import case as collective_case
from wafer_sim.adapters import wow
from wafer_sim.adapters.online_booksim import OnlineBookSim,prepare_online_config
from wafer_sim.adapters.spatial import bind
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.timing import audit
from wafer_sim.architecture.spatial import Network
from wafer_sim.architecture.timing import Link
from wafer_sim.execution.plan import Placement,Transfer
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.network_reference import compare_reference
from wafer_sim.workloads.spatial import Workload
from wafer_sim.io import write_json


class OnlineBookSimTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=Path(os.environ.get("WAFER_REMOTE_ROOT","/home/wangziheng/wafer_simulator"))
        cls.output=Path(os.environ["WAFER_ONLINE_TEST_OUTPUT"])
        cls.output.mkdir(exist_ok=False)
        cls.binary=cls.root/"build/booksim-online/online_booksim"
        cls.reference=cls.root/"build/booksim/rapidchiplet/booksim2/src/booksim"
        if not cls.binary.exists() or not cls.reference.exists():
            raise RuntimeError("Build the live adapter and accepted native reference first")
        wow.load_upstream(cls.root/"upstream/nw-design-for-wsi")

    def prepare(self, suffix, nodes=3):
        directory=self.output/suffix
        directory.mkdir()
        tree=directory/"rapidchiplet/booksim2/src"
        for part in ("rc_configs","rc_topologies","rc_stats","rc_xy_info"):
            (tree/part).mkdir(parents=True)
        rows=[]
        for i in range(nodes):
            row=f"router {i} node {i} 1"
            if i: row+=f" router {i-1} 3"
            if i+1<nodes: row+=f" router {i+1} 3"
            rows.append(row)
        (tree/"rc_topologies/network.anynet").write_text("\n".join(rows)+"\n")
        inputs=tiny_inputs()
        inputs["placement"]["chiplets"]=[{"name":"c"} for _ in range(nodes)]
        inputs["booksim_config"]["vc_buf_size"]=2
        config=prepare_online_config(inputs,directory)
        return directory,inputs,config

    def flows(self,suffix,requests):
        directory,inputs,config=self.prepare(suffix)
        client=OnlineBookSim(self.binary,config,directory,flit_bytes=4)
        try:
            for identity,(cycle,source,destination,size) in enumerate(requests):
                while client.now < cycle: client.advance(cycle)
                transfer=Transfer(str(identity),str(source),str(destination),source,destination,size)
                client.submit(str(identity),transfer,cycle)
            while client.pending: client.advance(10000)
            record=client.close()
        finally:
            client.abort()
        network=Network(((0,0),(1,1),(2,2)),((0,1),(1,2)),"declared line")
        checked=audit_messages(network,record["messages"])
        write_json(directory/"audit.json",checked)
        reference=compare_reference(inputs,directory,directory/"reference",self.reference,record["messages"],1)
        self.assertTrue(reference["passed"])
        return record,network

    def test_single_flow_padding_and_native_reference(self):
        record,_=self.flows("single",[(7,0,2,65)])
        m=record["messages"][0]
        self.assertEqual(m["expected_flits"],17)
        self.assertEqual(m["ready"],7)
        self.assertEqual(m["finish"],max(f["ejected"] for f in m["flits"])+1)
        self.assertEqual(m["flits"][0]["router_path"],[0,1,2])

    def test_concurrent_flows_share_link_with_credit_backpressure(self):
        isolated,_=self.flows("isolated",[(0,0,2,128)])
        combined,_=self.flows("shared",[(0,0,2,128),(0,1,2,128)])
        self.assertGreater(combined["messages"][0]["finish"],isolated["messages"][0]["finish"])
        self.assertGreater(combined["messages"][0]["last_inject"]-
                           combined["messages"][0]["first_inject"],31)

    def test_idle_gap_preserves_native_clock_and_credits(self):
        record,_=self.flows("gap",[(0,0,2,32),(1000,2,0,32)])
        self.assertEqual(record["messages"][1]["ready"],1000)
        self.assertGreater(record["final"]["idle_skipped_cycles"],0)
        self.assertTrue(record["final"]["drained"])

    def test_incomplete_transfer_cannot_close(self):
        directory,_,config=self.prepare("incomplete")
        client=OnlineBookSim(self.binary,config,directory,flit_bytes=4)
        try:
            client.submit("x",Transfer("x","0","2",0,2,128),0)
            with self.assertRaisesRegex(ValueError,"incomplete"): client.close()
        finally: client.abort()

    def test_collective_actions_share_live_network_and_wait_for_all_writes(self):
        directory,inputs,config=self.prepare("collective",nodes=4)
        binding,rates=collective_case(4)
        client=OnlineBookSim(self.binary,config,directory,flit_bytes=4)
        try:
            result=execute(binding,rates,network=client)
            record=client.close()
        finally:client.abort()
        self.assertTrue(audit(binding,rates,result)["passed"])
        gathers=[m for m in record["messages"] if m["destination"]==0]
        self.assertEqual(len(gathers),3)
        self.assertEqual({m["ready"] for m in gathers},{2})
        self.assertLess(max(m["first_inject"] for m in gathers),min(m["finish"] for m in gathers))
        self.assertEqual(result["storage"]["available_data"],["y0","y1","y2","y3"])
        self.assertGreater(result["application_cycles"],max(m["finish"] for m in record["messages"]))
        compare_reference(inputs,directory,directory/"reference",self.reference,record["messages"],1)

    def test_timing_memory_write_and_lifetime_follow_native_arrival(self):
        directory,inputs,config=self.prepare("lifetime",nodes=2)
        network=Network(((0,0),(1,1)),((0,1),),"declared two endpoints")
        hardware=replace(target(),network=network)
        w=Workload((data("x",8,"a"),data("y",4,"b",True)),
            (op("a",outputs=("x",)),op("b",inputs=("x",),outputs=("y",))))
        binding=bind(w,hardware,Placement({"a":"compute-A","b":"compute-B"},{"x":"A","y":"B"}))
        rates=replace(timing(),links=tuple(Link(a,b,link.service)
            for (a,b),link in zip(((0,1),(1,0)),timing().links)))
        client=OnlineBookSim(self.binary,config,directory,flit_bytes=4)
        try:
            result=execute(binding,rates,network=client)
            record=client.close()
        finally: client.abort()
        write_json(directory/"execution.json",result)
        self.assertTrue(audit(binding,rates,result)["passed"])
        message=record["messages"][0]
        self.assertEqual(message["ready"],8)  # 4 compute + 2 write + 2 source read
        self.assertEqual(result["application_cycles"],message["finish"]+9)
        self.assertEqual(result["storage"]["available_data"],["y"])
        compare_reference(inputs,directory,directory/"reference",self.reference,record["messages"],1)
        broken=copy.deepcopy(result)
        broken["network_messages"][0]["flits"].pop()
        with self.assertRaisesRegex(ValueError,"payload"): audit(binding,rates,broken)
        broken=copy.deepcopy(result)
        broken["network_messages"][0]["finish"]-=1
        with self.assertRaisesRegex(ValueError,"final flit"): audit(binding,rates,broken)
