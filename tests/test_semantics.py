"""Independent semantic tests; execute only on eex005."""
import copy
import os
from pathlib import Path
import unittest

from wafer_sim.adapters import booksim, wow
from wafer_sim.analysis.audit import audit
from wafer_sim.io import read_json, write_json
from wafer_sim.workloads.dag import lower_to_booksim, summary, validate
from wafer_sim.workloads.training import make_training


def node(i, kind="compute", duration=0, deps=(), rank=0, dst=-1, size=0, release=0):
    return dict(id=i, kind=kind, duration_cycles=duration, deps=list(deps), rank=rank,
                dst=dst, bytes=size, release_cycle=release, label=f"node{i}")


def work(nodes):
    return dict(ranks=2, nodes=nodes)


def tiny_inputs():
    return dict(chiplets={"c": dict(router_latency=4, unit_count=1)},
                placement={"chiplets": [{"name": "c"}, {"name": "c"}]},
                routing_table={"type": "default"},
                booksim_config=dict(mode="trace", trace_file="none", ignore_cycles=0, repetitions=3,
                    sim_count=1, trace_time_out=30, time_limit=30, precision=0.001,
                    saturation_factor=2, traffic="uniform", packet_size=1,
                    num_vcs=1, vc_buf_size=32, modular_routing_function="simple_cycle_breaking_set",
                    modular_selection_function="adaptive", sample_period=100000,
                    warmup_periods=0, wait_for_tail_credit=0,
                    injection_rate_uses_flits=1, deadlock_warn_timeout=200000))


class WorkloadTests(unittest.TestCase):
    def test_ring_payload_and_work_counts(self):
        workload = make_training(ranks=4, iterations=2, compute_cycles=100,
                                 chunk_bytes=2000, optimizer_cycles=10)
        counts = summary(workload)
        self.assertEqual(counts["messages"], 2*2*4*3)
        self.assertEqual(counts["payload_bytes"], 48*2000)
        self.assertEqual(counts["compute_cycles"], 2*4*110)

    def test_cycle_rejected(self):
        with self.assertRaisesRegex(ValueError, "Cyclic"):
            validate(work([node(0, deps=[1]), node(1, deps=[0])]))

    def test_bad_work_rejected(self):
        for nodes in ([node(0, duration=-1)], [node(0, duration=float("nan"))],
                      [node(0, deps=[9])], [node(0, deps=[1, 1]), node(1)]):
            with self.subTest(nodes=nodes), self.assertRaises(ValueError):
                validate(work(nodes))

    def test_rank_mapping_injective(self):
        with self.assertRaises(ValueError):
            lower_to_booksim(work([node(0)]), [0, 0])


class NativeCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ.get("WAFER_REMOTE_ROOT", "/home/wangziheng/wafer_simulator"))
        cls.binary = Path(os.environ.get("WAFER_TEST_BINARY", str(cls.root / "build/booksim/rapidchiplet/booksim2/src/booksim")))
        cls.original = cls.root / "build/booksim-reference/rapidchiplet/booksim2/src/booksim"
        # Do not silently skip native coverage on an incorrectly prepared host.
        if not cls.binary.exists() or not cls.original.exists():
            raise RuntimeError("Both original and patched BookSim binaries are required")
        cls.output = Path(os.environ["WAFER_TEST_OUTPUT"])
        cls.output.mkdir(parents=True, exist_ok=False)
        wow.load_upstream(cls.root / "upstream/nw-design-for-wsi")

    def execute(self, workload, suffix, original=False, skip=True, max_cycles=None, trace_transform=None):
        directory = self.output / suffix
        directory.mkdir()
        tree = directory / "rapidchiplet/booksim2/src"
        for part in ("rc_configs", "rc_topologies", "rc_stats", "rc_xy_info"):
            (tree / part).mkdir(parents=True)
        (tree / "rc_topologies/network.anynet").write_text(
            "router 0 node 0 1 router 1 3\nrouter 1 node 1 1 router 0 3\n")
        write_json(directory / "workload.json", workload)
        trace = lower_to_booksim(workload, [0, 1])
        if trace_transform is not None:
            trace_transform(trace)
        write_json(directory / "trace.json", trace)
        inputs = tiny_inputs()
        if os.environ.get("WAFER_TEST_DEPENDENCY_PROFILE") == "1" and not original:
            inputs["booksim_config"]["trace_dependency_profile"] = str(directory / "dependency_profile.json")
        config = booksim.prepare_config(inputs, directory, directory / "trace.json", 1, 30, skip)
        if original:
            config.write_text("\n".join(line for line in config.read_text().splitlines()
                                       if not line.startswith(("trace_report", "trace_skip_idle")))+"\n")
        if max_cycles is not None:
            config.write_text(config.read_text().replace("sample_period = 1000000000;", "sample_period = 0;"))
        execution = booksim.run(self.original if original else self.binary, config, directory, 30,
                                require_report=not original)
        if original:
            return execution
        report = read_json(directory / "trace_report.json")
        checked = audit(workload, report)
        write_json(directory / "audit.json", checked)
        return report, checked

    def test_terminal_compute_and_upstream_regression(self):
        workload = work([node(0, duration=37)])
        report, _ = self.execute(workload, "terminal_compute_fixed")
        self.assertEqual(report["application_cycles"], 37)
        original = self.execute(workload, "terminal_compute_original", original=True)
        self.assertNotEqual(original["network_metrics"]["Total cycles until trace completion"], 37)

    def test_terminal_message_and_upstream_regression(self):
        workload = work([node(0, "message", dst=1, size=64000)])
        report, _ = self.execute(workload, "terminal_message_fixed")
        self.assertEqual(report["messages_completed"], 1)
        self.assertEqual(report["flits_ejected"], 32)
        self.assertGreater(report["application_cycles"], 31)
        original = self.execute(workload, "terminal_message_original", original=True)
        self.assertEqual(original["network_metrics"]["Total number of trace messages simulated"], 0)

    def test_tail_compute_and_all_payloads(self):
        workload = work([node(0, duration=100),
                         node(1, "message", deps=[0], dst=1, size=128000),
                         node(2, "message", deps=[0], rank=1, dst=0, size=2001),
                         node(3, duration=51, deps=[1, 2])])
        report, _ = self.execute(workload, "tail_compute")
        self.assertEqual(report["flits_ejected"], 66)
        events = {e["id"]: e for e in report["events"]}
        self.assertEqual(report["application_cycles"], max(events[1]["finish_cycle"], events[2]["finish_cycle"])+51)

    def test_idle_skip_matches_cycle_stepping(self):
        workload = work([node(0, duration=1000),
                         node(1, "message", deps=[0], dst=1, size=64000),
                         node(2, "join", deps=[1]),
                         node(3, duration=3000, deps=[2]),
                         node(4, "message", deps=[3], rank=1, dst=0, size=80000),
                         node(5, duration=900, deps=[4])])
        fast, _ = self.execute(workload, "skip_idle", skip=True)
        slow, _ = self.execute(workload, "no_skip_idle", skip=False)
        self.assertEqual(fast["events"], slow["events"])
        self.assertEqual(fast["application_cycles"], slow["application_cycles"])

    def test_parallel_and_release_times(self):
        workload = work([node(0, duration=30), node(1, duration=20, rank=1, release=100),
                         node(2, duration=7, deps=[0, 1])])
        report, _ = self.execute(workload, "parallel_release")
        self.assertEqual(report["application_cycles"], 127)

    def test_cpu_lanes_serialize_without_serializing_other_lanes(self):
        workload = work([node(0, duration=30), node(1, duration=20),
                         node(2, duration=40, rank=1)])
        for op, lane in zip(workload["nodes"], [0, 0, 1]):
            op["cpu_resource"] = lane
        report, _ = self.execute(workload, "cpu_lanes")
        self.assertEqual(report["application_cycles"], 50)
        events = {e["id"]: e for e in report["events"]}
        self.assertEqual(events[1]["start_cycle"], 30)
        self.assertEqual(events[1]["cpu_predecessor"], 0)
        self.assertEqual(events[2]["start_cycle"], 0)

    def test_cpu_wait_delays_issue_and_message_does_not_occupy_cpu(self):
        workload = work([node(0, duration=100), node(1, "message", dst=1, size=64000),
                         node(2, duration=20)])
        for op in workload["nodes"]:
            op["cpu_resource"] = 0
        report, _ = self.execute(workload, "cpu_and_nic")
        events = {e["id"]: e for e in report["events"]}
        self.assertEqual(events[1]["start_cycle"], 100)
        self.assertEqual(events[2]["finish_cycle"], 120)
        self.assertGreater(events[1]["finish_cycle"], 120)

    def test_incomplete_run_rejected(self):
        workload = work([node(0, duration=37)])
        with self.assertRaisesRegex(RuntimeError, "did not complete"):
            self.execute(workload, "incomplete", max_cycles=0)
        report = read_json(self.output / "incomplete/trace_report.json")
        self.assertFalse(report["complete"])
        with self.assertRaises(ValueError):
            audit(workload, report)

    def test_unordered_dense_ids_preserve_cpu_callback_order(self):
        # Initial readiness follows file order, not ID order. Dependency-ready
        # callbacks follow reverse-edge order. Both are observable on one CPU.
        initial = work([node(2, duration=20), node(0, duration=30), node(1, duration=40)])
        dependent = work([node(0, duration=5), node(2, duration=20, deps=[0]),
                          node(1, duration=30, deps=[0])])
        for workload, suffix, starts in (
                (initial, "unordered_initial", {2: 0, 0: 20, 1: 50}),
                (dependent, "unordered_successors", {0: 0, 2: 5, 1: 25})):
            for op in workload["nodes"]:
                op["cpu_resource"] = 0
            report, _ = self.execute(workload, suffix)
            self.assertEqual([e["id"] for e in report["events"]], [0, 1, 2])
            self.assertEqual({e["id"]: e["start_cycle"] for e in report["events"]}, starts)

    def test_native_invalid_indices_rejected(self):
        # Exercise the native parser directly, bypassing Python's input gate.
        cases = {
            "negative_id": lambda trace: trace[0].update(id=-1),
            "duplicate_id": lambda trace: trace[1].update(id=0),
            "missing_successor": lambda trace: trace[0].update(rev_deps=[9]),
            "negative_successor": lambda trace: trace[0].update(rev_deps=[-1]),
        }
        for suffix, transform in cases.items():
            with self.subTest(case=suffix), self.assertRaisesRegex(RuntimeError, "did not complete"):
                self.execute(work([node(0), node(1)]), suffix, trace_transform=transform)
            self.assertFalse((self.output / suffix / "trace_report.json").exists())
            # A parser error is required; a crash is not an acceptable rejection.
            self.assertIn("complete-trace", (self.output / suffix / "stdout.log").read_text().lower())

    def test_zero_duration_join_keeps_completion_heap_order(self):
        # Completing 0 inserts join 1 ahead of already-due 4. Taking all due
        # events as an unordered frontier would reserve CPU 0 in the wrong order.
        workload = work([node(0, duration=5), node(4, duration=5, rank=1),
                         node(1, "join", deps=[0]), node(2, duration=20, deps=[1]),
                         node(3, duration=30, deps=[4])])
        for op in workload["nodes"]:
            if op["id"] in (2, 3):
                op["cpu_resource"] = 0
        report, _ = self.execute(workload, "zero_join_heap_order")
        events = {e["id"]: e for e in report["events"]}
        self.assertEqual(events[2]["start_cycle"], 5)
        self.assertEqual(events[3]["start_cycle"], 25)
        self.assertEqual(report["application_cycles"], 55)

    def test_shared_successor_and_frontier_submission_order(self):
        workload = work([node(0, duration=10), node(1, duration=10, rank=1),
                         node(2, duration=15, deps=[0, 1]), node(3, duration=10, deps=[0]),
                         node(4, duration=25, deps=[1])])
        for op in workload["nodes"]:
            if op["id"] >= 2:
                op["cpu_resource"] = 0
        report, _ = self.execute(workload, "shared_successor_order")
        events = {e["id"]: e for e in report["events"]}
        self.assertEqual([events[i]["start_cycle"] for i in (3, 2, 4)], [10, 20, 35])
        self.assertEqual(report["application_cycles"], 60)

    def test_native_malformed_dependency_rows_rejected(self):
        cases = {
            "duplicate_edge": lambda trace: trace[0].update(rev_deps=[1, 1]),
            "self_edge": lambda trace: trace[0].update(rev_deps=[0]),
            "indegree_mismatch": lambda trace: trace[1].update(num_deps=2),
        }
        for suffix, transform in cases.items():
            with self.subTest(case=suffix), self.assertRaisesRegex(RuntimeError, "did not complete"):
                self.execute(work([node(0), node(1, deps=[0])]), suffix, trace_transform=transform)
            self.assertFalse((self.output / suffix / "trace_report.json").exists())
            self.assertIn("dependency", (self.output / suffix / "stdout.log").read_text().lower())

    def test_audit_detects_corrupted_completion(self):
        workload = work([node(0, duration=37)])
        report, _ = self.execute(workload, "corruption_check")
        damaged = copy.deepcopy(report)
        damaged["events"][0]["finish_cycle"] = 36
        with self.assertRaisesRegex(ValueError, "duration"):
            audit(workload, damaged)


if __name__ == "__main__":
    unittest.main()
