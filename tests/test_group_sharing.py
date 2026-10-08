"""Composition preserves each complete group's semantics and fixed positions."""
from collections import Counter
from dataclasses import asdict
import unittest

from wafer_sim.workloads.transformer import build_block
from wafer_sim.workloads.spatial import validate
from wafer_sim.workloads.groups import namespace, independent_groups
from wafer_sim.adapters.transformer_groups import place_groups
from wafer_sim.adapters.transformer import place_block
from wafer_sim.experiments.group_sharing import strip_namespace
from wafer_sim.analysis.group_sharing import group_times, shared_paths, progress_changes


class GroupSharingTests(unittest.TestCase):
    def setUp(self):
        self.block=build_block(batch=1,sequence=64,hidden=64,heads=8,ffn_hidden=128,shards=8)

    def test_namespace_is_exactly_reversible_including_collective_and_dependencies(self):
        copied=namespace(self.block.workload,'A')
        self.assertEqual(strip_namespace(asdict(copied)),asdict(self.block.workload))
        validate(copied)

    def test_disjoint_graphs_and_work_conservation(self):
        work=independent_groups(self.block.workload,['A','B']); graph=validate(work)
        self.assertEqual(len(work.operations),2*len(self.block.workload.operations))
        for op in work.operations:
            group=op.id.split('/')[0]
            self.assertTrue(all(x.startswith(group+'/') for x in op.inputs+op.outputs+op.control_deps))
            self.assertTrue(all(x.startswith(group+'/') for x in graph.predecessors[op.id]))
            if op.collective:
                self.assertEqual(op.collective.id,op.id)
                self.assertEqual(op.collective.members,tuple(range(8)))
        def totals(w):
            c=Counter()
            for op in w.operations:
                for k,n in op.work:c[k]+=n
            return c
        self.assertEqual(totals(work),totals(self.block.workload)+totals(self.block.workload))

    def test_solo_is_exact_joint_projection_at_same_physical_resources(self):
        endpoints={'A':list(range(8)),'B':list(range(8,16))}
        both,bp=place_groups(self.block,endpoints)
        for g,ns in endpoints.items():
            single,sp=place_groups(self.block,{g:ns})
            self.assertEqual(single.operations,tuple(o for o in both.operations if o.id.startswith(g+'/')))
            self.assertEqual(single.data,tuple(d for d in both.data if d.id.startswith(g+'/')))
            self.assertEqual(dict(sp.compute),{k:v for k,v in bp.compute.items() if k.startswith(g+'/')})
            self.assertEqual(dict(sp.data),{k:v for k,v in bp.data.items() if k.startswith(g+'/')})
            self.assertEqual(strip_namespace(asdict(sp),g),asdict(place_block(self.block,ns)))

    def test_reject_aliasing_groups_and_local_resources(self):
        for names in ([],['A','A'],['A/invalid'],['']):
            with self.assertRaises(ValueError):independent_groups(self.block.workload,names)
        with self.assertRaises(ValueError):place_groups(self.block,{'A':list(range(8)),'B':list(range(8))})

    def test_group_completion_separates_outputs_from_retirement(self):
        result=dict(output_ready={**{f'A/r{i}/output:out':10+i for i in range(8)},'A/internal:out':100,
                                  **{f'B/r{i}/output:out':999 for i in range(8)}},
                    operations={'A/reduce':dict(retired=20),'B/reduce':dict(retired=999)})
        self.assertEqual(group_times(result,'A'),dict(output_ready=17,retired=20))
        del result['output_ready']['A/r0/output:out']
        with self.assertRaises(ValueError):group_times(result,'A')

    def test_shared_link_is_directional_and_time_envelope_is_separate(self):
        def message(g,a,b,t):
            return dict(token=g+'/send/phase/1',flits=[dict(router_path=[a,b],
                link_arrivals=[dict(source=a,destination=b,cycle=t)])])
        self.assertEqual(shared_paths([message('A',1,2,10),message('B',2,1,10)])['shared_directed_links'],0)
        r=shared_paths([message('A',1,2,10),message('B',1,2,100)])
        self.assertEqual(r['shared_directed_links'],1)
        self.assertEqual(r['shared_links_with_overlapping_arrival_envelopes'],0)

    def test_progress_reports_local_changes_even_when_collective_end_is_equal(self):
        solo=dict(operations={'A/attention_sum':dict(retired=10),'A/ffn_sum':dict(retired=20),
                              'A/r4/output':dict(retired=25)})
        joint=dict(operations={**solo['operations'],'A/r4/output':dict(retired=26),'B/other':dict(retired=99)})
        row=progress_changes(solo,joint,'A')
        self.assertEqual(row['changed_operation_count'],1)
        self.assertEqual(row['collective_progress']['ffn_sum']['solo'],row['collective_progress']['ffn_sum']['joint'])
