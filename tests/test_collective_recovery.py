"""Source-backed recovery and zero-copy lifetime semantics; no workload runs."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from test_collectives import report, machine, EVIDENCE, POLICY
from wafer_sim.analysis.collective_recovery import join_recovery
from wafer_sim.workloads.chakra_collectives import match_collectives, GPU_TYPES
from wafer_sim.workloads.collective_recovery import recover
from wafer_sim.workloads.collective_values import bind_values, forwards_input
from wafer_sim.workloads.collectives import from_match
from wafer_sim.workloads.tensor_effect_binding import AccessBinding
from wafer_sim.workloads.tensor_versions import ByteVersions
from wafer_sim.adapters.collectives import bind_collective
from wafer_sim.execution.collectives import CollectiveState, input_consumer, output_hold
from wafer_sim.execution.reservations import ReservationPool
from wafer_sim.execution.values import ValueLifetime


def singleton(kind="broadcast", reduction=None):
    source = report(3, 0)
    call = source["calls"][0]
    call["identity"].update(members=[3], group_size=1)
    source["parameters"][0].update(members=[3], group_size=1)
    intent = call["intent"]
    intent.update(kind=kind, reduction=reduction, root_local_rank=0 if kind == "broadcast" else None)
    slot = intent["slots"][0]
    slot["source"] = dict(slot["destination"])
    slot.update(input_elements=8, output_elements=8, input_bytes=32, output_bytes=32)
    return source


def barrier_reports():
    reports = [report(3, 0), report(7, 1)]
    for source in reports:
        source["calls"][0]["intent"].update(kind="barrier", slots=[], root_local_rank=None, reduction=None)
    return reports


class RecoveryTests(unittest.TestCase):
    def test_barrier_binds_all_participants_without_tensor_layout(self):
        plans, barriers, _ = recover(barrier_reports())
        self.assertEqual(len(barriers), 1)
        self.assertEqual(barriers[0]["collective"]["members"], (3, 7))
        for plan in plans.values():
            self.assertEqual(plan["required_binding_evidence"], [])
            self.assertTrue(plan["value_versions_bound"])
            self.assertFalse(plan["target_execution_complete"])

    def test_incomplete_barrier_cannot_become_ready(self):
        plans, barriers, _ = recover(barrier_reports()[:1])
        self.assertFalse(barriers)
        self.assertIn("incomplete_or_duplicate_participants", plans[3, 1]["required_binding_evidence"])
        self.assertNotIn("exact_byte_footprint", plans[3, 1]["required_binding_evidence"])

    def test_forward_recipe_still_requires_upstream_input_version(self):
        for kind, reduction in (("broadcast", None), ("allreduce", "sum")):
            plans, _, _ = recover([singleton(kind, reduction)])
            plan = plans[3, 1]
            self.assertEqual(plan["recipe"], "forward_input")
            self.assertEqual(plan["required_binding_evidence"], ["input_value_binding"])
            self.assertFalse(plan["value_versions_bound"])

    def test_opaque_singleton_reduction_is_not_assumed_identity(self):
        for reduction in (None, "premul_sum"):
            source = singleton("allreduce", reduction)
            plans, _, matches = recover([source])
            self.assertEqual(plans[3, 1]["recipe"], "unresolved_collective")
            self.assertIn("reduction_operator_unresolved", plans[3, 1]["collective_issues"])
            with self.assertRaises(ValueError):
                from_match(matches["collectives"][0], {(3, 1): source["calls"][0]})

    def test_same_storage_is_not_same_tensor_argument(self):
        source = singleton()
        source["calls"][0]["intent"]["slots"][0]["source"]["tensor_id"] += 1
        plans, _, _ = recover([source])
        self.assertEqual(plans[3, 1]["recipe"], "payload_binding")
        self.assertIn("exact_byte_footprint", plans[3, 1]["required_binding_evidence"])

    def test_missing_identity_is_not_inferred_from_shape_or_call_order(self):
        source = singleton()
        source["calls"][0]["identity"] = None
        plans, _, _ = recover([source])
        self.assertEqual(plans[3, 1]["recipe"], "unresolved_collective")
        self.assertIn("communicator_and_sequence", plans[3, 1]["required_binding_evidence"])

    def test_duplicate_ranks_or_calls_rejected(self):
        source = singleton()
        with self.assertRaises(ValueError): recover([source, source])
        source["calls"].append(copy.deepcopy(source["calls"][0]))
        with self.assertRaises(ValueError): recover([source])

    def test_recovery_join_keeps_entire_original_and_checks_coverage(self):
        plans, _, _ = recover([singleton()])
        row = dict(rank=3, call=dict(node_id=1), source_data_deps=[7, 9],
                   gpu_ports=[dict(node_id=21)], wait_ports=[dict(node_id=22)])
        with tempfile.TemporaryDirectory() as temp:
            src, dst = Path(temp)/"src.gz", Path(temp)/"dst.gz"
            with gzip.open(src, "wt") as stream: stream.write(json.dumps(row)+"\n")
            counts = join_recovery(src, dst, 3, plans)
            self.assertEqual(counts["calls"], 1)
            with gzip.open(dst, "rt") as stream: saved = json.loads(next(stream))
            self.assertEqual(saved["source_ports"], row)
            with gzip.open(src, "wt") as stream: stream.write("")
            with self.assertRaisesRegex(ValueError, "Missing"): join_recovery(src, dst, 3, plans)

    def test_gpu_broadcast_enum_matches_pinned_author_schema(self):
        schema = Path(__file__).resolve().parents[1]/"third_party/chakra/schema/protobuf/et_def.proto"
        self.assertIn("BROADCAST = 5;", schema.read_text())
        self.assertEqual(GPU_TYPES["broadcast"], 5)


class ForwardLifetimeTests(unittest.TestCase):
    def bound(self, *, initialized=True, kind="broadcast", reduction=None):
        source = singleton(kind, reduction)
        call = source["calls"][0]
        match = match_collectives([source])["collectives"][0]
        ref = call["intent"]["slots"][0]["source"]
        versions = ByteVersions()
        key = versions.allocate(3, ref["source_device"], ref["storage_id"], 32,
                                initial=EVIDENCE if initialized else None)
        access = {(3, 1, ref["path"]): AccessBinding(key, ((0, 32),))}
        values = bind_values(versions, match, {(3, 1):call}, access, provenance=EVIDENCE)
        binding = bind_collective(values.collective, machine(32), {3:"compute-3"}, policy=POLICY, values=values)
        return versions, values, binding

    def test_identity_does_not_create_write_or_duplicate_storage(self):
        for kind, reduction in (("broadcast", None), ("allreduce", "sum")):
            versions, values, binding = self.bound(kind=kind, reduction=reduction)
            value = values.inputs[3, 0]
            self.assertEqual(value, values.outputs[3, 0])
            self.assertEqual(versions.read(value.storage, ((0, 32),)), value.slices)
            self.assertEqual(binding.inputs, binding.outputs)
            self.assertEqual(binding.reservations[3], ())
            self.assertFalse(binding.actions)

    def test_forwarding_wait_and_future_consumer_lifetime(self):
        _, values, binding = self.bound()
        allocation = binding.inputs[3, 0]
        life = ValueLifetime(ReservationPool(binding.memory))
        life.declare(allocation, values.inputs[3, 0].producers,
                     [input_consumer(binding, 3), output_hold(binding), "next-compute"])
        state = CollectiveState(binding, lifetime=life)
        self.assertFalse(state.enter(3))
        self.assertFalse(state.wait_satisfied(3))
        self.assertTrue(life.pool.reserve((allocation,)))
        life.publish(allocation.key, set())
        # Data readiness alone is not operation/dependency completion.
        self.assertFalse(state.wait_satisfied(3))
        self.assertTrue(state.enter(3))
        self.assertTrue(state.all_complete())
        self.assertTrue(state.wait_satisfied(3))
        self.assertEqual(life.pool.used["3"], 32)
        self.assertEqual(life.values[allocation.key].remaining, {"next-compute"})
        life.acquire(allocation.key, "next-compute")
        life.finish(allocation.key, "next-compute")
        self.assertEqual(life.pool.used["3"], 0)

    def test_forwarding_does_not_invent_initial_data(self):
        with self.assertRaisesRegex(ValueError, "uninitialized"):
            self.bound(initialized=False)

    def test_bound_barrier_keeps_rendezvous_completion(self):
        reports = barrier_reports()
        calls = {(r["rank"], 1):r["calls"][0] for r in reports}
        match = match_collectives(reports)["collectives"][0]
        values = bind_values(ByteVersions(), match, calls, {}, provenance=EVIDENCE)
        binding = bind_collective(values.collective, machine(), {3:"compute-3",7:"compute-7"},
                                  policy=POLICY, values=values)
        life = ValueLifetime(ReservationPool(binding.memory))
        state = CollectiveState(binding, lifetime=life)
        self.assertTrue(state.enter(3))
        self.assertFalse(state.wait_satisfied(3))
        self.assertTrue(state.enter(7))
        self.assertTrue(state.wait_satisfied(3))
        self.assertEqual(sum(life.pool.used.values()), 0)
