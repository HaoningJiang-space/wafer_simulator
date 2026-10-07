"""Operator semantics, mathematical work, placement and full target execution."""
from collections import Counter
import copy
from math import prod
from pathlib import Path
import unittest

import numpy as np

from transformer_reference import initial_values, evaluate_graph, dense_forward
from wafer_sim.adapters.declared_target import build_target
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.transformer import place_block
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.transformer import run_case
from wafer_sim.io import read_json
from wafer_sim.workloads.transformer import build_block


def config():
    return read_json(Path(__file__).resolve().parents[1]/"configs/transformer_block.json")


class TransformerTests(unittest.TestCase):
    def test_dense_and_partitioned_forward_agree(self):
        # Includes multi-batch and single-token cases; no source capture involved.
        for batch,sequence,shards,heads,ffn in ((1,3,2,4,12),(2,2,4,4,12),(1,1,2,4,12),(1,3,8,8,16)):
            block = build_block(batch=batch,sequence=sequence,hidden=8,heads=heads,ffn_hidden=ffn,shards=shards)
            initial = initial_values(block)
            outputs = evaluate_graph(block,initial)
            reference = dense_forward(block,initial)
            for r in range(shards):
                np.testing.assert_allclose(outputs[f"r{r}/output:out"],reference,rtol=1e-12,atol=1e-12)

    def test_complete_block_work_and_tensor_sizes(self):
        block = build_block(**config()["block"])
        self.assertEqual(len(block.workload.operations),30)
        counts = Counter()
        for op in block.workload.operations:
            counts.update(dict(op.work))
            self.assertNotIn("cycles", dict(op.work))
            shapes=[block.tensors[d]["shape"] for d in op.inputs]
            output=block.tensors[op.outputs[0]]["shape"]
            kind=block.operators[op.id]["kind"]
            if kind == "linear":
                expected_mac=prod(shapes[0][:-1])*prod(shapes[1])
            elif kind == "attention_scores":
                expected_mac=prod(output)*(shapes[0][-1]//output[1])
            elif kind == "attention_values":
                expected_mac=prod(output)*shapes[0][-1]
            else:
                continue
            self.assertEqual(dict(op.work)["mac"],expected_mac,op.id)
        # Independent dense formula: four HxH and two HxF projections,
        # plus QK^T and attention-V; parallelization conserves MACs.
        b,s,h,f,p,heads = 1,16,64,128,2,4
        self.assertEqual(counts["mac"],4*b*s*h*h+2*b*s*s*h+2*b*s*h*f)
        self.assertEqual(counts["mac"],557056)
        n,rows = b*s*h,b*s
        self.assertEqual(counts["scalar_add"],2*p*(4*n-rows)+2*p*n+2*(p-1)*n+b*s*f+b*heads*s*(2*s-1))
        self.assertEqual(counts["scalar_mul"],2*p*(3*n+2*rows)+3*b*s*f+b*heads*s*s)
        self.assertEqual(counts["scalar_rsqrt"],2*p*rows)
        self.assertEqual(counts["scalar_max"],b*heads*s*(s-1))
        self.assertEqual(counts["scalar_exp"],b*heads*s*s)
        self.assertEqual(counts["scalar_div"],b*heads*s*s)
        self.assertEqual(counts["scalar_erf"],b*s*f)
        for d in block.workload.data:
            self.assertEqual(d.size_bytes,4*prod(block.tensors[d.id]["shape"]))

    def test_invalid_partition_is_rejected(self):
        for key,value in (("shards",1),("heads",3),("ffn_hidden",127),("sequence",0),("batch",True)):
            dims=dict(config()["block"]); dims[key]=value
            with self.assertRaises(ValueError): build_block(**dims)

    def test_mapping_changes_traffic_without_changing_work(self):
        c=config(); block=build_block(**c["block"])
        target,timing=build_target(c)
        remote=bind(block.workload,target,place_block(block,[0,1]))
        colocated=bind(block.workload,target,place_block(block,[0,0]))
        volume=lambda binding: sum(phase.transfer.size_bytes for plan in binding.plans.values()
                                  for phase in plan.phases if phase.transfer)
        self.assertEqual(volume(remote),16384)
        self.assertEqual(volume(colocated),0)
        # Co-location is only a resource-binding unit check, not a mapping study.
        self.assertTrue(execute(colocated,timing)["complete"])
        with self.assertRaises(ValueError): place_block(block,[0])

    def test_full_execution_collective_completion_and_lifetimes(self):
        record=run_case(config(),"declared")
        result=record["result"]
        self.assertTrue(record["audit"]["passed"])
        for collective,next_stage in (("attention_sum","attention_residual"),("ffn_sum","output")):
            op=next(o for o in record["workload"]["operations"] if o["id"]==collective)
            for r in range(2):
                self.assertEqual(result["operations"][f"r{r}/{next_stage}"]["ready"],
                                 result["output_ready"][op["outputs"][r]])
        # Only persistent parameters and the two final outputs remain live.
        self.assertEqual(sum(result["storage"]["used_bytes"].values()),
                         record["logical_summary"]["parameter_bytes"]+8192)
        retained={d["id"] for d in record["workload"]["data"] if d["retain"]}
        self.assertEqual(set(result["storage"]["available_data"]),retained)

    def test_service_rate_controls_keep_work_mapping_and_collectives_fixed(self):
        c=config(); baseline=run_case(c,"declared")
        for case in c["controlled_cases"][1:]:
            changed=run_case(c,case)
            for field in ("workload","placement","collective","logical_summary"):
                self.assertEqual(changed[field],baseline[field])
            self.assertTrue(changed["audit"]["passed"])
            self.assertLess(changed["result"]["application_cycles"],baseline["result"]["application_cycles"])

    def test_capacity_shortage_does_not_become_complete(self):
        c=config(); c["region_capacity_bytes"]=70000
        block=build_block(**c["block"]); target,timing=build_target(c)
        binding=bind(block.workload,target,place_block(block,c["worker_endpoints"]))
        # Persistent parameters + replicated input already exceed this budget.
        with self.assertRaisesRegex(ValueError,"Initial live data"):
            execute(binding,timing)

    def test_missing_special_function_rate_is_not_free_work(self):
        c=copy.deepcopy(config()); del c["compute_rates"]["scalar_erf"]
        with self.assertRaisesRegex(ValueError,"work unit"): run_case(c,"declared")
