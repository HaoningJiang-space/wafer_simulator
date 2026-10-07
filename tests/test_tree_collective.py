"""Independent SUM evaluation, fixed logical edges, work and lifetime checks."""
from dataclasses import replace
import copy
import unittest
import numpy as np

from test_collective_timing import case
from wafer_sim.adapters.collectives import bind_collective
from wafer_sim.architecture.spatial import Target, ComputeResource
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.storage import StorageState
from wafer_sim.execution.timing import execute


class TreeTests(unittest.TestCase):
    def test_work_conservation_non_power_of_two_and_fixed_edges(self):
        for n in (2,3,5,8):
            tree,timing=case(n,capacity=512,algorithm="binary_tree_sum")
            direct,_=case(n,capacity=512)
            plan=tree.plans["sum"]
            edges={(p.transfer.source_endpoint,p.transfer.destination_endpoint) for p in plan.phases if p.transfer}
            expected={(r,(r-1)//2) for r in range(1,n)}
            self.assertEqual(edges,expected|{(b,a) for a,b in expected})
            for b in (tree,direct):
                self.assertEqual(sum(p.transfer.size_bytes for p in b.plans["sum"].phases if p.transfer),2*(n-1)*8)
                self.assertEqual(sum(d.amount for p in b.plans["sum"].phases if p.kind=="compute" for d in p.demands),2*(n-1))
            result=execute(tree,timing)
            self.assertTrue(audit(tree,timing,result)["passed"])
            self.assertEqual(sum(critical_chain(tree,result)["cycles"].values()),result["application_cycles"])
            self.assertEqual(result["storage"]["used_bytes"],{str(r):8 for r in range(n)})
        # Heap position 7 is below 3, not 6.
        self.assertIn((7,3),edges);self.assertNotIn((7,6),edges)

    def test_numerical_sum_follows_actual_action_dependencies(self):
        for n in (2,3,5,8):
            binding,_=case(n,capacity=512,algorithm="binary_tree_sum")
            plan=binding.plans["sum"]
            for inputs in (np.arange(n*2).reshape(n,2), np.random.default_rng(37).normal(size=(n,2))):
                values={}
                for i,p in enumerate(plan.phases):
                    deps=plan.predecessors(i)
                    if not deps:
                        self.assertTrue(plan.action_ids[i].startswith("0/local-read/"))
                        rank=int(plan.action_ids[i].rsplit("/",1)[1]);values[i]=inputs[rank].copy()
                    elif p.kind=="compute":
                        self.assertEqual(p.demands[0].amount,2*(len(deps)-1))
                        values[i]=sum((values[d] for d in deps))
                    else:
                        self.assertEqual(len(deps),1)
                        values[i]=values[deps[0]].copy()
                for _,requirements in plan.output_requirements:
                    self.assertEqual(len(requirements),1)
                    np.testing.assert_allclose(values[requirements[0]],inputs.sum(axis=0),rtol=1e-12,atol=1e-12)

    def test_tree_uses_communicator_positions_not_physical_ids(self):
        binding,_=case(5,capacity=512,algorithm="binary_tree_sum")
        members=(11,3,27,4,9)
        collective=replace(binding.graph.operations["sum"].collective,members=members)
        machine=Target(tuple(binding.memory.values()),tuple(ComputeResource(f"compute-{i}",str(i),("scalar_add",),"fixture") for i in range(5)),binding.network)
        for assignment in ((0,1,2,3,4),(4,2,0,3,1)):
            placed=dict(zip(members,(f"compute-{i}" for i in assignment)))
            actions=bind_collective(collective,machine,placed,policy="binary_tree_sum").actions
            inverse=dict(zip(assignment,members))
            edges={(inverse[a.phase.transfer.source_endpoint],inverse[a.phase.transfer.destination_endpoint])
                   for a in actions.values() if a.phase.transfer}
            reduce={(members[i],members[(i-1)//2]) for i in range(1,5)}
            self.assertEqual(edges,reduce|{(b,a) for a,b in reduce})

    def test_partial_is_not_final_and_staging_survives_root_publication(self):
        binding,_=case(8,capacity=512,algorithm="binary_tree_sum")
        state=StorageState(binding);state.try_begin("sum")
        plan=binding.plans["sum"]
        while "y0" not in state.available:
            for i in state.ready_phases("sum"):
                state.begin_phase("sum",i);state.complete_phase("sum",i)
        self.assertEqual(state.available & {f"y{r}" for r in range(8)},{"y0"})
        self.assertNotIn("sum",state.completed)
        self.assertEqual(sum(k[0]=="collective_partial" for k in state.allocations),3)
        self.assertEqual(sum(k[0]=="collective_stage" for k in state.allocations),7)
        while "sum" not in state.completed:
            for i in state.ready_phases("sum"):
                state.begin_phase("sum",i);state.complete_phase("sum",i)
        self.assertTrue(all(k[0]=="object" for k in state.allocations))

    def test_explicit_extra_partial_memory_work_and_capacity(self):
        tree,timing=case(8,capacity=512,algorithm="binary_tree_sum");direct,_=case(8,capacity=512)
        memory=lambda b:sum(d.amount for p in b.plans["sum"].phases if p.kind.startswith("memory") for d in p.demands)
        self.assertEqual(memory(tree)-memory(direct),3*2*8)
        small,timing=case(8,capacity=32,algorithm="binary_tree_sum")
        result=execute(small,timing)
        self.assertFalse(result["complete"]);self.assertIsNone(result["application_cycles"])

    def test_independent_readback_rejects_incomplete_partial_and_early_output(self):
        binding,timing=case(4,algorithm="binary_tree_sum");result=execute(binding,timing)
        broken=copy.deepcopy(result)
        phase=next(p for p in broken["phases"] if p["action"]=="0/partial/1/read")
        phase["ready"]-=1
        with self.assertRaises(ValueError):audit(binding,timing,broken)
        broken=copy.deepcopy(result);broken["output_ready"]["y1"]-=1
        with self.assertRaisesRegex(ValueError,"Output published"):audit(binding,timing,broken)
