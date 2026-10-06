"""Readback regressions using saved native evidence; launches no simulation."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np

from wafer_sim.analysis.goal_completion import audit
from wafer_sim.io import read_json, write_json


class FullReadbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="wafer-readback-")
        self.root = Path(self.temporary.name)
        self.graph = self.root / "graph"
        self.graph.mkdir()
        saved = Path(os.environ["WAFER_NATIVE_REGRESSION_INPUT"])
        workload = read_json(saved / "cpu_and_nic/workload.json")
        self.report = read_json(saved / "cpu_and_nic/trace_report.json")
        nodes = workload["nodes"]
        ops = np.array([(0 if n["kind"] == "compute" else 1,
                         n["duration_cycles"] if n["kind"] == "compute" else n["bytes"],
                         n["rank"], n["cpu_resource"]) for n in nodes],
                       dtype=[("kind", "u1"), ("amount", "u8"), ("rank", "i4"), ("cpu", "i4")])
        np.save(self.graph / "operations.npy", ops)
        np.save(self.graph / "dependencies.npy", np.empty((0, 2), dtype="i4"))
        np.save(self.graph / "message_pairs.npy", np.empty((0, 2), dtype="i4"))
        write_json(self.root / "contract.json", dict(work=dict(instructions=3, messages=1, flits=32,
                                                              cpu_stride=1, flit_bytes=2000)))

    def tearDown(self):
        self.temporary.cleanup()

    def run_reader(self, report):
        report = copy.deepcopy(report)
        report["events_file"] = str(self.root / "events.jsonl")
        with Path(report["events_file"]).open("w") as stream:
            for event in report.pop("events"):
                stream.write(json.dumps(event)+"\n")
        write_json(self.root / "trace_report.json", report)
        return audit(self.graph, self.root)

    def test_resource_critical_chain_closes(self):
        result = self.run_reader(self.report)
        self.assertEqual(result["critical_local_work_cycles"], 100)
        self.assertEqual(result["total_local_work_cycles"], 120)
        self.assertEqual(result["critical_message_cycles"], self.report["application_cycles"]-100)

    def test_changed_local_work_rejected(self):
        damaged = copy.deepcopy(self.report)
        damaged["events"][2]["finish_cycle"] -= 1
        with self.assertRaisesRegex(ValueError, "duration"):
            self.run_reader(damaged)

    def test_unexplained_cpu_wait_rejected(self):
        damaged = copy.deepcopy(self.report)
        damaged["events"][1]["cpu_predecessor"] = -1
        with self.assertRaisesRegex(ValueError, "CPU wait"):
            self.run_reader(damaged)
