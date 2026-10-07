"""Explicit unit conversion, resource binding and paired-study controls."""
import copy
from pathlib import Path
import unittest

from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.adapters.spatial import bind
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.analysis.timing import audit
from wafer_sim.execution.plan import Placement
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json
from test_spatial import data,op
from wafer_sim.workloads.spatial import Workload


def exported():
    return dict(resources=dict(link_bits_per_cycle=16000,router_latency_cycles=4,network_frequency_hz=1000000000),
        endpoints=[dict(node=0,router=0),dict(node=1,router=1)],
        inputs=dict(links=[dict(src=0,dst=1,bidirectional=True,bandwidth=16000,latency=3)],
            chiplets={"c":dict(router_latency=4,unit_to_router_latency=6)},
            placement=dict(chiplets=[dict(name="c"),dict(name="c")])) )


class WoWTargetTests(unittest.TestCase):
    def parameters(self):
        return dict(scope="analytical local resources",region_capacity_bytes=128,
                    compute_rates={"mac":4},memory_bytes_per_cycle=8)

    def test_bits_bytes_router_and_endpoint_latency_are_explicit(self):
        hardware,timing,contract=build_wow_target(exported(),self.parameters(),2000)
        self.assertEqual(len(hardware.memory),2)
        self.assertEqual(timing.links[0].service.rate_numerator,16000)
        self.assertEqual(timing.links[0].service.rate_denominator,8)
        self.assertEqual(timing.links[0].service.latency_cycles,7)
        self.assertEqual(timing.endpoints[0].injection.latency_cycles,6)
        self.assertEqual(timing.endpoints[0].ejection.latency_cycles,10)
        self.assertFalse(contract["compute_memory_calibrated"])

    def test_heterogeneous_or_incompatible_native_width_rejected(self):
        for width in (1999,4000):
            with self.assertRaisesRegex(ValueError,"bandwidth"):
                build_wow_target(exported(),self.parameters(),width)
        bad=copy.deepcopy(exported()); bad["inputs"]["links"][0]["bandwidth"]=8000
        with self.assertRaisesRegex(ValueError,"bandwidth"):
            build_wow_target(bad,self.parameters(),2000)

    def test_observed_critical_chain_counts_resource_wait_once(self):
        hardware,timing,_=build_wow_target(exported(),self.parameters(),2000)
        w=Workload((data("x",8,"a"),data("y",8,"b",True)),
                   (op("a",outputs=("x",)),op("b",inputs=("x",),outputs=("y",))))
        binding=bind(w,hardware,Placement({"a":"compute-0","b":"compute-1"},{"x":"0","y":"1"}))
        result=execute(binding,timing)
        self.assertTrue(audit(binding,timing,result)["passed"])
        chain=critical_chain(binding,result)
        self.assertEqual(sum(chain["cycles"].values()),result["application_cycles"])
        self.assertGreater(chain["cycles"]["network"],0)

    def test_registration_uses_accepted_complete_block_and_one_mapping(self):
        repo=Path(__file__).resolve().parents[1]
        config=read_json(repo/"configs/transformer_wow_pair.json")
        block=read_json(repo/config["workload_config"])
        self.assertEqual(block["block"],dict(batch=1,sequence=16,hidden=64,heads=4,ffn_hidden=128,shards=2))
        self.assertEqual(config["placements"],["baseline","ours_rotated"])
        self.assertEqual(config["mapping"],"row_major")
