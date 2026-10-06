"""Analytical readback fixtures only: no simulator or performance experiment."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np

from wafer_sim.adapters.goal_booksim import lower
from wafer_sim.analysis.campaign_acceptance import accept
from wafer_sim.analysis.critical_chain import difference, message_timings, parent_graph, recover
from wafer_sim.analysis.goal_completion import audit
from wafer_sim.analysis.placement_attribution import analyze, finalize
from wafer_sim.experiments.next_experiment import register_mapping_check
from wafer_sim.io import digest, read_json, write_json

FIELDS = ("ready_cycle", "start_cycle", "finish_cycle", "cpu_predecessor", "generated_cycle",
          "first_inject_cycle", "last_inject_cycle", "first_eject_cycle")


def event_array(starts, finishes):
    events = np.full(len(starts), -1, dtype=[(f, "i8") for f in FIELDS])
    events["ready_cycle"] = starts
    events["start_cycle"] = starts
    events["finish_cycle"] = finishes
    return events


class ChainTests(unittest.TestCase):
    def test_cpu_wait_is_explained_by_predecessor_not_double_counted(self):
        ops = np.array([(0,), (1,)], dtype=[("kind", "u1")])
        events = event_array([0, 7], [7, 11])
        events["ready_cycle"][1] = 0
        events["cpu_predecessor"][1] = 0
        events["first_inject_cycle"][1] = 8
        chain = recover(ops, events, parent_graph(2, np.empty((0, 2), dtype="i4"), np.empty((0, 2), dtype="i4")), {})
        self.assertEqual(chain["ids"].tolist(), [0, 1])
        self.assertEqual(chain["predecessor_relations"], ["root", "cpu_resource"])
        self.assertEqual((chain["critical_local_work_cycles"], chain["critical_message_cycles"]), (7, 4))
        parts = message_timings(events, np.array([1]))
        self.assertEqual([int(parts[k][0]) for k in ("cpu_wait", "injection_wait", "first_inject_to_complete")], [7, 1, 3])

    def test_terminal_and_predecessor_ties_match_existing_audit(self):
        ops = np.zeros(4, dtype=[("kind", "u1")])
        events = event_array([0, 0, 5, 5], [5, 5, 6, 6])
        parents = parent_graph(4, np.array([(0, 2), (1, 2), (0, 3), (1, 3)]), np.empty((0, 2), dtype="i4"))
        chain = recover(ops, events, parents, {})
        self.assertEqual(chain["ids"].tolist(), [1, 2])
        events["start_cycle"][2] = 4
        with self.assertRaisesRegex(ValueError, "does not close"):
            recover(ops, events, parents, {})

    def test_negative_message_interval_rejected(self):
        events = event_array([2], [5])
        events["first_inject_cycle"] = 6
        with self.assertRaisesRegex(ValueError, "Invalid message interval"):
            message_timings(events, np.array([0]))


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wafer-attribution-unit-")
        self.root = Path(self.temp.name)
        self.graph, self.campaign = self.root / "graph", self.root / "campaign"
        self.graph.mkdir()
        self.campaign.mkdir()
        self.ops = np.array([
            (0, 0, 0, 2, 0, -1, -1, 0, 1), (0, 1, 1, 2000, 0, 0, 1, 10, 2),
            (1, 2, 1, 2000, 0, 0, 0, 20, 3), (1, 3, 2, 2000, 0, 0, 0, 10, 4),
            (0, 4, 2, 2000, 0, 0, 1, 20, 5), (0, 5, 0, 2, 0, -1, -1, 0, 6)],
            dtype=[("rank", "u4"), ("label", "u4"), ("kind", "u1"), ("amount", "u8"),
                   ("cpu", "i4"), ("nic", "i4"), ("peer", "i4"), ("tag", "u8"), ("line", "u4")])
        self.deps = np.array([(0, 1), (0, 2), (3, 5), (4, 5)], dtype="i4")
        self.pairs = np.array([(1, 3), (2, 4)], dtype="i4")
        for file, value in (("operations", self.ops), ("dependencies", self.deps), ("message_pairs", self.pairs)):
            np.save(self.graph / f"{file}.npy", value)
        source_hash = "a" * 64
        write_json(self.graph / "graph_audit.json", dict(dependency_gate_passed=True, truncated=False,
            removed_dependencies=0, source_sha256=source_hash, operations=6, input_dependencies=4, matched_messages=2))
        rows = []
        self.events = {}
        for name, starts, finishes in (("baseline", [0, 2, 2, 12, 5, 12], [2, 12, 5, 12, 5, 14]),
                                       ("ours_rotated", [0, 2, 2, 5, 11, 11], [2, 5, 11, 5, 11, 13])):
            path = self.campaign / name
            path.mkdir()
            contract = lower(self.graph, path / "trace.json", [0, 1])
            events = event_array(starts, finishes)
            for op_id in (1, 2):
                first = starts[op_id] + (2 if (name == "baseline") == (op_id == 1) else 1)
                events["generated_cycle"][op_id] = starts[op_id]
                events["first_inject_cycle"][op_id] = first
                events["last_inject_cycle"][op_id] = first
                events["first_eject_cycle"][op_id] = finishes[op_id]
            self.events[name] = events
            with (path / "events.jsonl").open("w") as stream:
                for i, event in enumerate(events):
                    stream.write(json.dumps(dict(id=i, completed=True, flits_remaining=0,
                        **{f: int(event[f]) for f in FIELDS})) + "\n")
            report = dict(complete=True, application_cycles=finishes[-1], instructions_expected=6,
                instructions_completed=6, messages_completed=2, flits_ejected=2, tagged_last_flit_arrived_early=0,
                events_file=str(path / "events.jsonl"))
            write_json(path / "trace_report.json", report)
            checked = audit(self.graph, path)
            resources = dict(compute_reticles=2, network_frequency_hz=1e9, link_bits_per_cycle=16000,
                buffer_flits_per_vc=32, virtual_channels=1, router_latency_cycles=4, routers=2,
                undirected_links=1, aggregate_directed_link_bits_per_cycle=32000, physical_cost_matched=False)
            endpoints = [dict(node=i, router=i, layer=0, position=dict(x=i, y=0)) for i in range(2)]
            write_json(path / "resources.json", resources)
            write_json(path / "network.json", dict(resources=resources, endpoints=endpoints))
            metrics = {"Packet latency average": 4 if name == "baseline" else 3,
                       "Network latency average": 2, "Hops average": 1}
            write_json(path / "execution.json", dict(complete=True, return_code=0, timed_out=False,
                binary_sha256="b" * 64, network_metrics=metrics, wall_seconds=1))
            rows.append(dict(placement=name, **checked, resources=resources, network_metrics=metrics,
                             wall_seconds=1, report_sha256=digest(path / "trace_report.json")))
        config = dict(placements=["baseline", "ours_rotated"], truncate_input=False, remove_dependencies=False,
            thermal_feedback=False, network_frequency_hz=1e9, flit_bytes=2000,
            source_sha256=source_hash, graph_directory=str(self.graph), dependency_profile=False)
        write_json(self.campaign / "config.json", config)
        write_json(self.campaign / "provenance.json", dict(binary_sha256="b" * 64, source_sha256=source_hash))
        write_json(self.campaign / "registration.json", dict(all_work_matched=True, work=contract["work"]))
        write_json(self.campaign / "results.json", rows)
        write_json(self.campaign / "COMPLETE.json", dict(all_arms_audited=True, comparisons=rows))
        (self.campaign / "summary.csv").write_text("unit fixture\n")
        (self.campaign / "comparison.md").write_text("Analytical unit fixture, no simulation\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_different_critical_messages_and_exact_application_delta(self):
        parents = parent_graph(6, self.deps, self.pairs)
        chains = {n: recover(self.ops, e, parents, {}) for n, e in self.events.items()}
        self.assertEqual(chains["baseline"]["ids"].tolist(), [0, 1, 3, 5])
        self.assertEqual(chains["ours_rotated"]["ids"].tolist(), [0, 2, 4, 5])
        change, _, _ = difference(self.ops, self.events["baseline"], self.events["ours_rotated"],
                                  chains["baseline"], chains["ours_rotated"])
        self.assertEqual(change["application_delta_cycles"], 1)
        self.assertEqual(change["baseline_only_message"], 10)
        self.assertEqual(change["rotated_only_message"], 9)
        self.assertEqual(change["common_local_delta"], 0)

    def test_partial_pair_and_failure_marker_rejected(self):
        (self.campaign / "COMPLETE.json").unlink()
        with self.assertRaises(FileNotFoundError):
            accept(self.campaign)
        write_json(self.campaign / "failures.json", [dict(error="fixture")])
        with self.assertRaisesRegex(ValueError, "Failed/excluded"):
            accept(self.campaign)

    def test_mixed_implementation_rejected(self):
        path = self.campaign / "ours_rotated/execution.json"
        value = read_json(path)
        value["binary_sha256"] = "c" * 64
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "different implementation"):
            accept(self.campaign)

    def test_inconsistent_completion_marker_rejected(self):
        path = self.campaign / "COMPLETE.json"
        value = read_json(path)
        value["comparisons"][0]["application_cycles"] += 1
        write_json(path, value)
        with self.assertRaisesRegex(ValueError, "completion marker disagrees"):
            accept(self.campaign)

    def test_required_profile_gate_cannot_be_omitted(self):
        path = self.campaign / "config.json"
        value = read_json(path)
        value["dependency_profile"] = True
        write_json(path, value)
        with self.assertRaises(FileNotFoundError):
            accept(self.campaign)

    def test_outputs_readonly_counts_and_equivalence_binding(self):
        before = {p: digest(p) for p in self.campaign.rglob("*") if p.is_file()}
        output = self.root / "analysis"
        summary = analyze(self.campaign, output)
        self.assertEqual(summary["next_experiment"], dict(status="pending_reference_equivalence", registered_groups=0))
        self.assertFalse((output / "next_experiment.json").exists())
        self.assertEqual(summary["application_speedup"], 14 / 13)
        self.assertEqual(summary["chain_difference"]["accounted_delta_cycles"], 1)
        self.assertEqual([row["send_id"] for row in summary["largest_critical_message_changes"]], [1, 2])
        self.assertEqual([row["baseline_minus_rotated_service"] for row in summary["largest_critical_message_changes"]], [7, -6])
        self.assertTrue(summary["observed_order_changes"]["common_order_equal"])
        with (output / "message_pairs.csv").open() as stream:
            paired = list(csv.DictReader(stream))
        self.assertEqual([int(r["send_id"]) for r in paired], [1, 2])
        self.assertEqual(paired[0]["baseline_on_chain"], "True")
        self.assertEqual(paired[0]["ours_rotated_on_chain"], "False")
        with (output / "baseline/critical_chain.csv").open() as stream:
            chain = list(csv.DictReader(stream))
        self.assertEqual(chain[0]["location_scope"], "logical_host_cpu_only")
        self.assertEqual(chain[0]["endpoint"], "")
        self.assertEqual(sum(int(r["service_cycles"]) for r in chain), 14)
        with (output / "critical_local_pairs.csv").open() as stream:
            local = list(csv.DictReader(stream))
        self.assertEqual([int(r["op_id"]) for r in local], [0, 5])
        self.assertEqual([int(r["duration_cycles"]) for r in local], [2, 2])
        self.assertEqual(before, {p: digest(p) for p in self.campaign.rglob("*") if p.is_file()})
        verification = dict(passed=True, same_full_work_and_events=True, reference=str(self.root / "reference"),
            candidate=str(self.campaign), arms=[dict(placement=n, exact_full_event_match=True, hashes=[dict(file=f,
                sha256=digest(self.campaign / n / f)) for f in ("trace.json", "events.jsonl")])
                for n in ("baseline", "ours_rotated")])
        bad = copy.deepcopy(verification)
        bad["arms"][0]["hashes"][0]["sha256"] = "d" * 64
        write_json(output / "bad-equivalence.json", bad)
        registration = Mock(return_value=dict(status="registered_not_executed", registered_groups=1))
        with self.assertRaisesRegex(ValueError, "differs from attributed"):
            finalize(output, output / "bad-equivalence.json", register_next=registration)
        registration.assert_not_called()
        write_json(output / "implementation_equivalence.json", verification)
        missing = copy.deepcopy(verification)
        missing["arms"][0]["hashes"].pop()
        write_json(output / "incomplete-equivalence.json", missing)
        with self.assertRaisesRegex(ValueError, "both complete input and event hashes"):
            finalize(output, output / "incomplete-equivalence.json")
        finalize(output, output / "implementation_equivalence.json", register_next=registration)
        registration.assert_called_once()
        self.assertEqual(read_json(output / "summary.json")["next_experiment"]["registered_groups"], 1)
        self.assertTrue(read_json(output / "FINAL_ACCEPTED.json")["implementation_equivalence"])
        self.assertEqual(read_json(output / "acceptance.json")["implementation_equivalence"]["status"], "passed")
        manifest = read_json(output / "ANALYZED.json")
        self.assertEqual(manifest["artifact_sha256"]["attribution.md"], digest(output / "attribution.md"))

    def test_registration_changes_only_supported_mapping_and_never_runs(self):
        # Temporary metadata fixtures test the registration contract only.
        info = accept(self.campaign)
        info["campaign"] = self.root / "runs/accepted_pair"
        info["config"].update(mapping="row_major", active_endpoints=4, seed=1)
        for arm in info["arms"].values():
            arm["network"]["endpoints"] = [dict(node=i, router=i, layer=0, position=dict(x=i, y=0)) for i in range(4)]
        project = self.root / "project"
        config = dict(info["config"], implementation_patch_files=["patches/booksim-wafer.patch"])
        write_json(project / "configs/llama16_fixed_state.json", config)
        binary = self.root / "build/booksim/rapidchiplet/booksim2/src/booksim"
        binary.parent.mkdir(parents=True)
        binary.write_text("non-executable unit fixture")
        write_json(self.root / "runs/fastest-consolidation-001/acceptance.json",
                   dict(passed=True, binary_sha256=digest(binary)))
        summary = dict(chains={name: dict(critical_local_work_cycles=999, application_cycles=1000)
                               for name in ("baseline", "ours_rotated")},
                       application_time_reduction_percent=.1, packet_latency_reduction_percent=15)
        output = self.root / "registration"
        output.mkdir()
        with patch("wafer_sim.experiments.next_experiment.__file__", str(project / "src/wafer_sim/experiments/next_experiment.py")):
            decision = register_mapping_check(info, summary, output)
            self.assertEqual(decision["registered_groups"], 1)
            proposed = read_json(output / "next_experiment_config.json")
            self.assertEqual({k for k in proposed if proposed[k] != config[k]}, {"mapping"})
            self.assertNotIn("mapping_seed", proposed)  # It is metadata, not an unconsumed config knob.
            registration = read_json(output / "next_experiment.json")
            self.assertEqual(registration["network_seed"], 1)
            self.assertEqual(registration["mapping_seed"], 1234)
            self.assertEqual(registration["status"], "registered_not_executed")
            for mapping in registration["expected_endpoint_mapping"].values():
                self.assertEqual(sorted(mapping), [0, 1, 2, 3])
                self.assertNotEqual(mapping, [0, 1, 2, 3])
            config["seed"] = 2
            write_json(project / "configs/llama16_fixed_state.json", config)
            with self.assertRaisesRegex(ValueError, "Active controls changed"):
                register_mapping_check(info, summary, output)


if __name__ == "__main__":
    unittest.main()
