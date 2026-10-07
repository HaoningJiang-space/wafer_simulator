"""Collective -> immutable value -> finite target lifetime regressions."""
from dataclasses import replace
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from test_collectives import report, machine, POLICY, EVIDENCE
from wafer_sim.workloads.chakra_collectives import match_collectives
from wafer_sim.workloads.collective_values import bind_values
from wafer_sim.workloads.tensor_effect_binding import AccessBinding
from wafer_sim.workloads.tensor_versions import ByteVersions
from wafer_sim.adapters.collectives import bind_collective
from wafer_sim.execution.collectives import CollectiveState, input_consumer, output_hold
from wafer_sim.execution.reservations import ReservationPool
from wafer_sim.execution.values import ValueLifetime
from wafer_sim.analysis.collective_ports import check_call, join_ports


def source_fixture(*, inplace=False):
    reports = [report(3, 0), report(7, 1)]
    state, accesses = ByteVersions(), {}
    for r in reports:
        c = r["calls"][0]
        slot = c["intent"]["slots"][0]
        if inplace:
            slot["source"]["storage_id"] = slot["destination"]["storage_id"]
        storages = {}
        for role in ("destination", "source"):
            ref = slot[role]
            sid = ref["storage_id"]
            if sid not in storages:
                storages[sid] = state.allocate(r["rank"], ref["source_device"], sid, 32,
                                               initial="explicit input" if role == "source" or inplace else None)
            accesses[(r["rank"],c["node_id"],ref["path"])] = AccessBinding(storages[sid], ((0,ref["num_elements"]*4),))
    calls = {(r["rank"],c["node_id"]):c for r in reports for c in r["calls"]}
    match = match_collectives(reports)["collectives"][0]
    return state, match, calls, accesses


def value_fixture(*, inplace=False, capacity=512, extra_reader=False):
    state, match, calls, accesses = source_fixture(inplace=inplace)
    values = bind_values(state,match,calls,accesses,provenance=EVIDENCE)
    b = bind_collective(values.collective,machine(capacity),{3:"compute-3",7:"compute-7"},policy=POLICY,values=values)
    life = ValueLifetime(ReservationPool(b.memory))
    for (rank,slot),a in b.inputs.items():
        readers = [input_consumer(b,rank)] + (["other-reader"] if extra_reader else [])
        life.declare(a,values.inputs[(rank,slot)].producers,readers)
        assert life.pool.reserve((a,))
        life.publish(a.key,values.inputs[(rank,slot)].producers)
    for key,a in b.outputs.items():
        life.declare(a,values.outputs[key].producers,[output_hold(b),"next-compute"])
    return b,life


class CollectiveValueTests(unittest.TestCase):
    def test_inplace_reads_snapshot_before_output_versions(self):
        state,match,calls,accesses=source_fixture(inplace=True)
        before = state.read(accesses[(3,1,"i:1.0")].storage,((0,16),))
        values=bind_values(state,match,calls,accesses,provenance=EVIDENCE)
        self.assertEqual(values.inputs[(3,0)].slices,before)
        self.assertNotEqual(values.inputs[(3,0)].key,values.outputs[(3,0)].key)
        self.assertEqual(values.outputs[(3,0)].producers,frozenset({"pg:pg/seq:10/output/3/0"}))
        self.assertNotEqual(values.inputs[(3,0)].key,values.inputs[(7,0)].key)

    def test_invalid_later_rank_does_not_mutate_earlier_output(self):
        state,match,calls,accesses=source_fixture()
        a=accesses[(7,1,"i:1.0")]
        accesses[(7,1,"i:1.0")]=replace(a,spans=((0,8),))
        with self.assertRaisesRegex(ValueError,"footprint"):
            bind_values(state,match,calls,accesses,provenance=EVIDENCE)
        out=accesses[(3,1,"i:0.0")]
        with self.assertRaisesRegex(ValueError,"uninitialized"):
            state.read(out.storage,out.spans)

    def test_stale_generation_and_wrong_source_identity_rejected(self):
        state,match,calls,accesses=source_fixture()
        state.allocate(3,"cuda:0",102,32)
        with self.assertRaisesRegex(ValueError,"stale"):
            bind_values(state,match,calls,accesses,provenance=EVIDENCE)
        state,match,calls,accesses=source_fixture()
        calls[(7,1)]["identity"]["sequence"]=11
        with self.assertRaisesRegex(ValueError,"identity"):
            bind_values(state,match,calls,accesses,provenance=EVIDENCE)

    def test_partial_prior_writes_preserve_both_producer_dependencies(self):
        state,match,calls,accesses=source_fixture()
        a=accesses[(3,1,"i:1.0")]
        state.write(a.storage,((0,8),),"compute-A",EVIDENCE)
        state.write(a.storage,((8,16),),"compute-B",EVIDENCE)
        v=bind_values(state,match,calls,accesses,provenance=EVIDENCE)
        self.assertEqual(v.inputs[(3,0)].producers,frozenset({"compute-A","compute-B"}))

    def test_unmatched_collective_cannot_generate_target_versions(self):
        state,match,calls,accesses=source_fixture()
        match["participant_and_volume_match"]=False
        with self.assertRaises(ValueError):
            bind_values(state,match,calls,accesses,provenance=EVIDENCE)

    def test_overlapping_outputs_rejected_before_any_write(self):
        state,match,calls,accesses=source_fixture()
        for c in calls.values(): c["intent"]["slots"].append(copy.deepcopy(c["intent"]["slots"][0]))
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            bind_values(state,match,calls,accesses,provenance=EVIDENCE)
        a=accesses[(3,1,"i:0.0")]
        with self.assertRaisesRegex(ValueError,"uninitialized"): state.read(a.storage,a.spans)

    def test_broadcast_nonroot_overwrite_does_not_read_old_value(self):
        state,match,calls,accesses=source_fixture()
        match["kind"]="broadcast"
        for (rank,node),c in calls.items():
            c["intent"].update(kind="broadcast",root_local_rank=0)
            slot=c["intent"]["slots"][0]
            slot.update(source=slot["destination"],input_elements=8,input_bytes=32)
            del accesses[(rank,node,"i:1.0")]
        a=accesses[(3,1,"i:0.0")]
        state.write(a.storage,a.spans,"root-compute",EVIDENCE)
        values=bind_values(state,match,calls,accesses,provenance=EVIDENCE)
        self.assertEqual(set(values.inputs),{(3,0)})
        b=bind_collective(values.collective,machine(),{3:"compute-3",7:"compute-7"},policy=POLICY,values=values)
        self.assertEqual(set(b.inputs),{(3,0)})


class CollectiveLifetimeTests(unittest.TestCase):
    def drain(self,state):
        while not state.all_complete():
            ready=state.ready_actions(); self.assertTrue(ready)
            for action in ready:
                state.begin(action); state.complete(action)

    def test_collective_output_becomes_next_compute_input_then_frees(self):
        b,life=value_fixture(inplace=True)
        state=CollectiveState(b,lifetime=life)
        out=b.outputs[(3,0)].key
        self.assertFalse(life.can_acquire(out,"next-compute"))
        for rank in b.collective.members: self.assertTrue(state.enter(rank))
        with self.assertRaisesRegex(ValueError,"active"):
            life.pool.release(b.inputs[(3,0)].key)
        self.drain(state)
        self.assertTrue(life.can_acquire(out,"next-compute"))
        self.assertTrue(all(a.key not in life.pool.allocations for a in b.inputs.values()))
        for a in b.outputs.values():
            life.acquire(a.key,"next-compute")
            life.finish(a.key,"next-compute")
        self.assertEqual(sum(life.pool.used.values()),0)

    def test_another_consumer_keeps_old_input_version_resident(self):
        b,life=value_fixture(extra_reader=True)
        state=CollectiveState(b,lifetime=life)
        for rank in b.collective.members: state.enter(rank)
        self.drain(state)
        key=b.inputs[(3,0)].key
        self.assertIn(key,life.pool.allocations)
        life.acquire(key,"other-reader"); life.finish(key,"other-reader")
        self.assertNotIn(key,life.pool.allocations)

    def test_capacity_failure_does_not_pin_or_consume_input(self):
        b,life=value_fixture(capacity=32)
        state=CollectiveState(b,lifetime=life)
        before=life.pool.used.copy()
        self.assertFalse(state.enter(3))
        self.assertEqual(life.pool.used,before)
        self.assertFalse(life.values[b.inputs[(3,0)].key].active)

    def test_output_ready_does_not_imply_global_completion(self):
        b,life=value_fixture()
        state=CollectiveState(b,lifetime=life)
        for rank in b.collective.members: state.enter(rank)
        delayed="0/3->7/write"
        while True:
            ready=[a for a in state.ready_actions() if a != delayed]
            if not ready: break
            for a in ready: state.begin(a); state.complete(a)
        self.assertTrue(life.can_acquire(b.outputs[(3,0)].key,"next-compute"))
        self.assertFalse(life.can_acquire(b.outputs[(7,0)].key,"next-compute"))
        self.assertFalse(state.all_complete())
        self.assertNotIn(b.inputs[(3,0)].key,life.pool.allocations)

    def test_unproduced_version_cannot_enter_or_publish(self):
        b,life=value_fixture()
        a=b.inputs[(3,0)]; value=life.values[a.key]
        value.ready=False; value.published=False; value.producers=frozenset({"not-finished"})
        with self.assertRaisesRegex(ValueError,"completed producers"):
            life.publish(a.key,set())
        # A separate catalogue with matching producer declarations is needed;
        # the collective itself rejects arbitrary producer identity changes.
        with self.assertRaisesRegex(ValueError,"producers"):
            CollectiveState(b,lifetime=life)

    def test_bound_versions_cannot_bypass_lifetime_catalogue(self):
        b,_=value_fixture()
        with self.assertRaisesRegex(ValueError,"together"): CollectiveState(b)

    def test_unavailable_input_blocks_without_partial_reservation(self):
        b,old=value_fixture()
        life=ValueLifetime(ReservationPool(b.memory))
        for v in old.values.values(): life.declare(v.allocation,v.producers,v.remaining)
        state=CollectiveState(b,lifetime=life)
        self.assertFalse(state.enter(3))
        self.assertEqual(sum(life.pool.used.values()),0)
        a=b.inputs[(3,0)]
        life.pool.reserve((a,)); life.publish(a.key,b.values.inputs[(3,0)].producers)
        self.assertTrue(state.enter(3))

    def test_output_retention_and_duplicate_consumer_completion(self):
        b,life=value_fixture()
        life.values[b.outputs[(3,0)].key].retain=True
        state=CollectiveState(b,lifetime=life)
        for rank in b.collective.members: state.enter(rank)
        self.drain(state)
        key=b.outputs[(3,0)].key
        life.acquire(key,"next-compute"); life.finish(key,"next-compute")
        self.assertIn(key,life.pool.allocations)
        with self.assertRaises(ValueError): life.finish(key,"next-compute")


class CollectivePortJoinTests(unittest.TestCase):
    def fixture(self):
        r=report(3,0); c=r["calls"][0]
        c.update(byte_offset=100,source_ctrl_deps=[0],source_data_deps=[],gpu_nodes=[],source_wait_nodes=[])
        slot=c["intent"]["slots"][0]
        row=dict(rank=3,node_id=1,byte_offset=100,name=c["name"],source_ctrl_deps=[0],source_data_deps=[],
                 effects=dict(inputs=[slot["destination"],slot["source"]],outputs=[]))
        return r,row

    def test_join_retains_owner_tensor_ports_and_unknown_bindings(self):
        r,row=self.fixture()
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name,entry in (("effects",row),("owners",dict(rank=3,node_id=1,byte_offset=100,owner=1))):
                with gzip.open(root/name,"wt") as f: f.write(json.dumps(entry)+"\n")
            result=join_ports(r,root/"effects",root/"owners",root/"out")
            self.assertEqual(result["counts"]["collective_calls"],1)
            with gzip.open(root/"out","rt") as f: saved=json.loads(next(f))
            self.assertFalse(saved["value_versions_bound"])
            self.assertIn("allocation_generation",saved["required_binding_evidence"])

    def test_mismatched_tensor_or_dependency_rejected(self):
        r,row=self.fixture()
        changed=copy.deepcopy(row); changed["effects"]["inputs"][0]["tensor_id"]+=1
        with self.assertRaisesRegex(ValueError,"tensor"): check_call(r["calls"][0],changed)
        row["source_data_deps"]=[5]
        with self.assertRaisesRegex(ValueError,"dependency"): check_call(r["calls"][0],row)


if __name__ == "__main__":
    unittest.main()
