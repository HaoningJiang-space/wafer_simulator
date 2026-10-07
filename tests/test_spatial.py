"""Analytic semantic regressions only, never a performance workload."""
import unittest
from dataclasses import replace

from wafer_sim.workloads.spatial import DataObject, Operation, Workload, validate
from wafer_sim.architecture.spatial import MemoryRegion, ComputeResource, Network, Target
from wafer_sim.adapters.spatial import bind, network_from_wow
from wafer_sim.execution.plan import Placement
from wafer_sim.execution.storage import StorageState


EVIDENCE = "analytic semantic fixture; not a captured AI workload"


def data(name, size, producer=None, retain=False):
    return DataObject(name, size, producer, retain, EVIDENCE)


def op(name, inputs=(), outputs=(), deps=(), scratch=0):
    return Operation(name, inputs, outputs, (("mac", 12),), scratch, deps, EVIDENCE)


def target(a=64, b=64):
    return Target((MemoryRegion("A", 0, a, "A-port", "A-port", EVIDENCE),
                   MemoryRegion("B", 1, b, "B-read", "B-write", EVIDENCE)),
                  (ComputeResource("compute-A", "A", ("mac",), EVIDENCE),
                   ComputeResource("compute-B", "B", ("mac",), EVIDENCE)),
                  Network(((0, 10), (1, 11)), ((10, 11),), EVIDENCE))


def finish(state, name):
    while name in state.active:
        state.complete_phase(name, state.active[name])


class SpatialContractTests(unittest.TestCase):
    def setUp(self):
        self.work = Workload((data("x", 8), data("y", 4, "f", True)),
                             (op("f", ("x",), ("y",), scratch=2),))
        self.placement = Placement({"f": "compute-A"}, {"x": "A", "y": "A"})

    def test_locality_changes_movements_not_logical_bytes(self):
        local = bind(self.work, target(), self.placement)
        remote = bind(self.work, target(), replace(self.placement, data={"x": "B", "y": "A"}))
        self.assertEqual([p.transfer for p in local.plans["f"].phases if p.transfer], [])
        transfers = [p.transfer for p in remote.plans["f"].phases if p.transfer]
        self.assertEqual([(t.data, t.source_endpoint, t.destination_endpoint, t.size_bytes)
                          for t in transfers], [("x", 1, 0, 8)])
        self.assertEqual(sum(d.size_bytes for d in remote.graph.data.values()), 12)
        self.assertEqual(local.graph.predecessors, remote.graph.predecessors)

    def test_source_read_network_destination_write_are_distinct(self):
        b = bind(self.work, target(), replace(self.placement, data={"x": "B", "y": "A"}))
        phases = b.plans["f"].phases
        self.assertEqual([p.kind for p in phases],
                         ["memory_read", "transfer", "memory_write", "memory_read", "compute", "memory_write"])
        byte_demands = [(d.resource, d.amount) for p in phases for d in p.demands if d.unit == "bytes"]
        self.assertEqual(byte_demands, [("B-read", 8), ("A-port", 8), ("A-port", 8), ("A-port", 4)])

    def test_moving_compute_also_regenerates_transfers(self):
        b = bind(self.work, target(), replace(self.placement, compute={"f": "compute-B"}))
        self.assertEqual([(p.transfer.data, p.transfer.source_endpoint, p.transfer.destination_endpoint)
                          for p in b.plans["f"].phases if p.transfer], [("x", 0, 1), ("y", 1, 0)])

    def test_output_waits_for_network_and_destination_write(self):
        work = Workload((data("x", 8, "produce"),),
                        (op("produce", outputs=("x",)), op("consume", inputs=("x",))))
        b = bind(work, target(), Placement({"produce": "compute-A", "consume": "compute-B"}, {"x": "B"}))
        state = StorageState(b)
        self.assertTrue(state.try_begin("produce").admitted)
        phases = b.plans["produce"].phases
        for index in range(len(phases) - 1):
            state.complete_phase("produce", index)
            self.assertNotIn("x", state.available)
            self.assertFalse(state.admission("consume").admitted)
        self.assertEqual(state.next_phase("produce").kind, "memory_write")
        state.complete_phase("produce", len(phases) - 1)
        self.assertIn("x", state.available)
        self.assertTrue(state.try_begin("consume").admitted)
        finish(state, "consume")
        self.assertEqual(state.used, {"A": 0, "B": 0})

    def test_fanout_releases_after_last_consumer_completion(self):
        work = Workload((data("x", 8),), (op("a", ("x",)), op("b", ("x",))))
        state = StorageState(bind(work, target(), Placement({"a": "compute-A", "b": "compute-A"}, {"x": "A"})))
        state.try_begin("a"); state.try_begin("b")
        finish(state, "a")
        self.assertIn("x", state.available)
        self.assertEqual(state.used["A"], 8)
        finish(state, "b")
        self.assertNotIn("x", state.available)
        self.assertEqual(state.used["A"], 0)

    def test_capacity_admission_is_atomic_and_recovers_after_release(self):
        work = Workload((data("hold", 16), data("out", 16, "produce", True)),
                        (op("release", ("hold",)), op("produce", outputs=("out",))))
        state = StorageState(bind(work, target(16, 16), Placement(
            {"release": "compute-B", "produce": "compute-A"}, {"hold": "B", "out": "B"})))
        before = state.snapshot()
        blocked = state.try_begin("produce")
        self.assertEqual(blocked.shortage_bytes, (("B", 16),))
        self.assertFalse(blocked.admitted)
        self.assertEqual(before, state.snapshot())
        state.try_begin("release"); finish(state, "release")
        self.assertTrue(state.try_begin("produce").admitted)
        self.assertEqual(state.used, {"A": 16, "B": 16})
        finish(state, "produce")
        self.assertEqual(state.used, {"A": 0, "B": 16})
        self.assertTrue(state.snapshot()["all_operations_completed"])
        self.assertFalse(state.snapshot()["timing_evaluated"])

    def test_global_free_space_cannot_cover_local_overflow(self):
        work = Workload((data("x", 6), data("y", 6)), (op("f", ("x", "y")),))
        b = bind(work, target(8, 1024), Placement({"f": "compute-A"}, {"x": "A", "y": "A"}))
        with self.assertRaisesRegex(ValueError, "Initial live data"):
            StorageState(b)

    def test_live_input_output_and_scratch_all_count(self):
        state = StorageState(bind(self.work, target(13, 1024), self.placement))
        self.assertEqual(state.try_begin("f").shortage_bytes, (("A", 1),))
        self.assertFalse(state.snapshot()["all_operations_completed"])
        self.assertEqual(state.used["A"], 8)

    def test_retained_data_and_temporary_storage_accounting(self):
        state = StorageState(bind(self.work, target(), self.placement))
        state.try_begin("f")
        self.assertEqual(state.used["A"], 14)
        finish(state, "f")
        self.assertEqual(state.used["A"], 4)
        self.assertEqual(state.peak["A"], 14)
        self.assertEqual(state.available, {"y"})

    def test_staging_is_per_consumer_not_an_implicit_cache(self):
        work = Workload((data("x", 8),), (op("a", ("x",)), op("b", ("x",))))
        b = bind(work, target(), Placement({"a": "compute-A", "b": "compute-A"}, {"x": "B"}))
        state = StorageState(b)
        state.try_begin("a"); state.try_begin("b")
        self.assertEqual(state.used, {"A": 16, "B": 8})
        self.assertEqual(sum(p.transfer.size_bytes for plan in b.plans.values() for p in plan.phases if p.transfer), 16)

    def test_duplicate_or_early_completion_rejected(self):
        state = StorageState(bind(self.work, target(), self.placement))
        with self.assertRaises(ValueError): state.complete_phase("f", 0)
        state.try_begin("f")
        with self.assertRaises(ValueError): state.try_begin("f")
        with self.assertRaises(ValueError): state.complete_phase("f", 1)
        state.complete_phase("f", 0)
        with self.assertRaises(ValueError): state.complete_phase("f", 0)
        finish(state, "f")
        with self.assertRaises(ValueError): state.complete_phase("f", 0)

    def test_cyclic_data_and_control_dependencies_rejected(self):
        work = Workload((data("x", 4, "a"), data("y", 4, "b")),
                        (op("a", ("y",), ("x",)), op("b", ("x",), ("y",))))
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            validate(work)
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            validate(Workload((), (op("a", deps=("b",)), op("b", deps=("a",)))))

    def test_missing_producer_mismatch_and_duplicate_input_rejected(self):
        for work in (replace(self.work, data=(data("x", 8), data("y", 4, "absent"))),
                     replace(self.work, operations=(op("f", ("x",)),)),
                     replace(self.work, operations=(op("f", ("x", "x"), ("y",)),))):
            with self.assertRaises(ValueError): validate(work)

    def test_duration_cannot_be_substituted_for_compute_work(self):
        for work in ((), (("ms", 556),), (("mac", -1),), (("mac", True),)):
            with self.assertRaises(ValueError):
                validate(replace(self.work, operations=(replace(self.work.operations[0], work=work),)))

    def test_unknown_compute_service_and_incomplete_mapping_rejected(self):
        with self.assertRaises(ValueError):
            bind(self.work, target(), replace(self.placement, data={"x": "A"}))
        with self.assertRaises(ValueError):
            bind(self.work, replace(target(), compute=(ComputeResource("compute-A", "A", ("other",), EVIDENCE),)), self.placement)

    def test_shared_memory_port_and_compute_ids_are_explicit(self):
        b = bind(self.work, target(), self.placement)
        phases = b.plans["f"].phases
        self.assertEqual(phases[0].demands[0].resource, phases[-1].demands[0].resource)
        self.assertEqual(phases[1].demands[0].resource, "compute-A")
        with self.assertRaises(ValueError):
            bind(self.work, replace(target(), compute=(ComputeResource("A-port", "A", ("mac",), EVIDENCE),)), self.placement)

    def test_same_endpoint_memory_domains_require_a_separate_model(self):
        t = target()
        with self.assertRaisesRegex(ValueError, "local DMA"):
            bind(self.work, replace(t, memory=(t.memory[0], replace(t.memory[1], endpoint=0))), self.placement)

    def test_disconnected_physical_network_cannot_move_data(self):
        t = replace(target(), network=Network(((0, 10), (1, 11)), (), EVIDENCE))
        with self.assertRaisesRegex(ValueError, "disconnected"):
            bind(self.work, t, replace(self.placement, data={"x": "B", "y": "A"}))
        # A local use does not acquire imaginary global connectivity.
        self.assertFalse(any(p.transfer for p in bind(self.work, t, self.placement).plans["f"].phases))

    def test_endpoint_and_parallel_link_validation(self):
        for network in (Network(((0, 10),), (), EVIDENCE),
                        Network(((0, 10), (1, 11)), ((10, 11), (11, 10)), EVIDENCE)):
            with self.assertRaises(ValueError):
                bind(self.work, replace(target(), network=network), self.placement)

    def test_author_export_connectivity_is_reused_without_memory_defaults(self):
        export = dict(endpoints=[dict(node=0, router=10), dict(node=1, router=11)],
                      inputs=dict(links=[dict(src=10, dst=11, bidirectional=True, bandwidth=16000, latency=7)]))
        network = network_from_wow(export)
        self.assertEqual(network.endpoint_routers, ((0, 10), (1, 11)))
        self.assertEqual(network.router_links, ((10, 11),))
        changed = dict(endpoints=export["endpoints"], inputs=dict(links=[dict(export["inputs"]["links"][0], latency=8)]))
        self.assertNotEqual(network.provenance, network_from_wow(changed).provenance)


if __name__ == "__main__":
    unittest.main()
