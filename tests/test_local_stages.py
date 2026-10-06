"""Semantic checks for evidence association; these do not run a workload."""
from pathlib import Path
import tempfile
import unittest

import numpy as np

from wafer_sim.adapters.atlahs_observer import DTYPE, write_sites
from wafer_sim.analysis.local_stages import check_correspondence
from wafer_sim.analysis.source_intervals import covered_time
from wafer_sim.io import digest, write_json


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.graph, self.regen = self.root / "graph", self.root / "regen"
        self.graph.mkdir()
        self.regen.mkdir()
        self.original = self.root / "original.goal"
        self.text = "num_ranks 1\nrank 0 {\nl1: calc 10 cpu 1\nl2: calc 6 cpu 2\nl2 requires l1\n}\n"
        self.original.write_text(self.text)
        self.ops = np.array([(0, 1, 0, 10, 1), (0, 2, 0, 6, 2)],
            dtype=[("rank", "i8"), ("label", "i8"), ("kind", "i8"), ("amount", "i8"), ("cpu", "i8")])
        np.save(self.graph / "operations.npy", self.ops)
        write_json(self.graph / "graph_audit.json", dict(source_sha256=digest(self.original), dependency_gate_passed=True))
        self.records = np.zeros(2, dtype=DTYPE)
        self.records["label"] = [1, 2]
        self.records["cpu"] = [1, 2]
        self.records["duration"] = [12, 6]
        self.records["category"] = [2, 5]
        self.records["model_key"] = [0, 1]

    def tearDown(self):
        self.temp.cleanup()

    def run_check(self, candidate=None):
        (self.regen / "candidate.goal").write_text(candidate or self.text.replace("calc 10", "calc 12"))
        self.records.tofile(self.regen / "calc_provenance.bin")
        write_json(self.regen / "CALC_PROVENANCE.json", dict(complete=True,
            binary_sha256=digest(self.regen / "calc_provenance.bin")))
        write_json(self.regen / "REGENERATION.json", dict(upstream_commit="fixture", goal_sha256=dict(
            original=digest(self.original), regenerated=digest(self.regen / "candidate.goal"))))
        return check_correspondence(self.original, self.graph, self.regen, self.root / "result")

    def test_npkit_redraw_can_be_associated_but_original_cost_is_preserved(self):
        result = self.run_check()
        self.assertTrue(result["source_correspondence_passed"])
        self.assertEqual(result["published_npkit_costs_by_observed_key"], {0: 10})
        self.assertEqual(self.original.read_text(), self.text)

    def test_dependency_difference_prevents_source_association(self):
        result = self.run_check(self.text.replace("l2 requires l1", "l1 requires l2"))
        self.assertFalse(result["source_correspondence_passed"])

    def test_changed_transfer_cost_cannot_be_excused_as_npkit_randomness(self):
        self.records["duration"][1] = 7
        self.assertFalse(self.run_check()["source_correspondence_passed"])

    def test_calc_identity_mismatch_prevents_source_association(self):
        self.records["cpu"][1] = 3
        self.assertFalse(self.run_check()["source_correspondence_passed"])

    def test_kernel_union_clips_window_and_does_not_double_count(self):
        self.assertEqual(covered_time([(-1, 3), (2, 7), (9, 12), (3, 4)], 0, 10), 8)

    def test_transfer_peer_comes_from_enclosing_source_branch(self):
        source = '''if goal_rank_peer != goal_rank:
    file.write(f"l{task_counter}: send 1b")
else:
    file.write(f"l{task_counter}: calc {get_intra_node_gpu_transfer_time(1, 'Send')} cpu 1")
'''
        self.assertEqual(write_sites(source)[4]["peer_variable"], "gpuId_peer")
