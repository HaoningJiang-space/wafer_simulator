"""Bind source rules to unchanged published work, then classify existing chains."""
from collections import Counter
import csv
import hashlib
from itertools import zip_longest
from pathlib import Path
import re

import numpy as np

from wafer_sim.adapters.atlahs_observer import CATEGORIES, DTYPE
from wafer_sim.io import digest, read_json, write_json


def normalized_goal(path):
    """Ignore only calc amounts here; every amount is checked separately."""
    sha, counts = hashlib.sha256(), Counter()
    for raw in Path(path).open("rb"):
        if b": calc " in raw:
            counts["calc"] += 1
            raw = re.sub(rb"(: calc )-?\d+", rb"\1DURATION", raw)
        elif b": send " in raw:
            counts["send"] += 1
        elif b": recv " in raw:
            counts["recv"] += 1
        elif b" requires " in raw:
            counts["requires"] += 1
        sha.update(raw)
    return sha.hexdigest(), dict(counts)


def check_correspondence(original, graph, regenerated, output):
    """A failed source association cannot be used to relabel published work.

    Historical NPKit choices are random and cached. Source association permits
    those amounts to differ, only when all other serialized information is
    identical and each modeled key has one preserved original cost. No amounts
    in the original graph are changed; this is not a new simulation input.
    """
    original, graph, regenerated, output = map(Path, (original, graph, regenerated, output))
    output.mkdir(parents=True, exist_ok=False)
    manifest = read_json(regenerated / "REGENERATION.json")
    provenance = read_json(regenerated / "CALC_PROVENANCE.json")
    if not provenance["complete"] or digest(regenerated / "calc_provenance.bin") != provenance["binary_sha256"]:
        raise ValueError("Incomplete or changed source observation")
    if digest(original) != manifest["goal_sha256"]["original"] or digest(
            regenerated / "candidate.goal") != manifest["goal_sha256"]["regenerated"]:
        raise ValueError("Reconstruction input changed")
    graph_audit = read_json(graph / "graph_audit.json")
    if graph_audit["source_sha256"] != manifest["goal_sha256"]["original"] or not graph_audit["dependency_gate_passed"]:
        raise ValueError("Original audited graph does not match published source")
    ops = np.load(graph / "operations.npy", mmap_mode="r")
    ids = np.flatnonzero(ops["kind"] == 0)
    calc = ops[ids]
    source = np.memmap(regenerated / "calc_provenance.bin", dtype=DTYPE, mode="r")
    left, left_counts = normalized_goal(original)
    right, right_counts = normalized_goal(regenerated / "candidate.goal")
    identity = len(source) == len(calc) and all(np.array_equal(source[f], calc[g])
        for f, g in (("rank", "rank"), ("label", "label"), ("cpu", "cpu")))
    result = dict(original_goal_sha256=digest(original), regenerated_goal_sha256=digest(regenerated / "candidate.goal"),
        normalized_original_sha256=left, normalized_regenerated_sha256=right,
        original_counts=left_counts, regenerated_counts=right_counts,
        calc_identity_match=identity, unchanged_serialized_structure=left == right,
        normalization_scope="Only calc numeric amounts; labels, CPU/NIC identities, messages, tags and every dependency remain exact",
        new_simulations_launched=0, original_input_modified=False,
        upstream_commit=manifest["upstream_commit"], reconstruction_directory=str(regenerated.resolve()))
    if identity:
        modeled = np.isin(source["category"], [2, 3, 4])
        mismatch = source["duration"] != calc["amount"]
        result.update(duration_differences=int(mismatch.sum()),
                      non_npkit_duration_differences=int((mismatch & ~modeled).sum()))
        frozen, inconsistent = {}, []
        for key in np.unique(source["model_key"][modeled]):
            values = np.unique(calc["amount"][source["model_key"] == key])
            if len(values) != 1:
                inconsistent.append(int(key))
            else:
                frozen[int(key)] = int(values[0])
        result.update(original_npkit_costs_constant_by_observed_key=not inconsistent,
                      inconsistent_keys=inconsistent,
                      published_npkit_costs_by_observed_key=frozen)
        result["source_correspondence_passed"] = bool(left == right and not result[
            "non_npkit_duration_differences"] and not inconsistent)
    else:
        result["source_correspondence_passed"] = False
    if left != right:
        with original.open() as a, (regenerated / "candidate.goal").open() as b:
            for number, (x, y) in enumerate(zip_longest(a, b, fillvalue=""), 1):
                norm = lambda text: re.sub(r"(: calc )-?\d+", r"\1DURATION", text)
                if norm(x) != norm(y):
                    result["first_structure_difference"] = dict(line=number, original=x, regenerated=y)
                    break
    result["input_sha256"] = {str(p.resolve()): digest(p) for p in (
        graph / "operations.npy", graph / "graph_audit.json", regenerated / "REGENERATION.json",
        regenerated / "CALC_PROVENANCE.json")}
    write_json(output / "SOURCE_CORRESPONDENCE.json", result)
    return result


def classify(graph, regenerated, attribution, output):
    graph, regenerated, attribution, output = map(Path, (graph, regenerated, attribution, output))
    correspondence = read_json(output / "SOURCE_CORRESPONDENCE.json")
    if not correspondence["source_correspondence_passed"]:
        raise ValueError("Source reconstruction has not been associated with all published work")
    ops = np.load(graph / "operations.npy", mmap_mode="r")
    ids = np.flatnonzero(ops["kind"] == 0)
    source = np.memmap(regenerated / "calc_provenance.bin", dtype=DTYPE, mode="r")
    positions = np.full(len(ops), -1, dtype="i8")
    positions[ids] = np.arange(len(ids))
    memberships, totals, all_ids = {}, {}, set()
    for arm in ("baseline", "ours_rotated"):
        chain = list(csv.DictReader((attribution / arm / "critical_chain.csv").open()))
        selected = [int(row["op_id"]) for row in chain if row["kind"] == "calc"]
        memberships[arm] = set(selected)
        all_ids.update(selected)
        counts, durations = Counter(), Counter()
        for op_id in selected:
            category = CATEGORIES[int(source[positions[op_id]]["category"])]
            counts[category] += 1
            durations[category] += int(ops[op_id]["amount"])
        local = sum(int(row["service_cycles"]) for row in chain if row["kind"] != "send")
        if sum(durations.values()) != local:
            raise ValueError("Classified local stages do not close against observed chain")
        totals[arm] = dict(counts=dict(counts), duration_cycles=dict(durations), local_cycles=local)
    rows = []
    for op_id in sorted(all_ids):
        op, record = ops[op_id], source[positions[op_id]]
        category = CATEGORIES[int(record["category"])]
        resource = {"measured_interval": "unresolved composite interval; no calibrated target service",
                    "reduction_model": "local reduction and memory service",
                    "copy_model": "local copy and memory service",
                    "reduction_copy_model": "local reduction/copy and memory service",
                    "intra_host_transfer_model": "source and peer GPU endpoints; target transfer pending pairing",
                    "synchronization_placeholder": "logical dependency only",
                    "unknown": "unknown"}[category]
        rows.append(dict(op_id=op_id, host=int(op["rank"]), label=int(op["label"]),
            goal_line=int(op["line"]), cpu=int(op["cpu"]), duration_cycles=int(op["amount"]),
            category=category, source_line=int(record["source_line"]), source_gpu=int(record["gpu"]),
            source_stream=int(record["stream"]), source_group=int(record["group"]),
            source_event=int(record["event"]), peer_gpu=int(record["peer_gpu"]),
            transfer_role={0: "", 1: "send", 2: "recv"}[int(record["role"])],
            model_bytes=int(record["model_bytes"]), source_model_key=int(record["model_key"]),
            interval_start_ns=int(record["interval_start"]), interval_end_ns=int(record["interval_end"]),
            baseline_on_chain=op_id in memberships["baseline"],
            rotated_on_chain=op_id in memberships["ours_rotated"], target_resource=resource,
            evidence="all serialized structure matched; original costs preserved"))
    def write_csv(path, records):
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(records)
    write_csv(output / "local_stage_provenance.csv", rows)
    major = sorted((r for r in rows if r["duration_cycles"]), key=lambda r: (-r["duration_cycles"], r["op_id"]))[:30]
    write_csv(output / "major_local_stages.csv", major)
    result = dict(chains=totals, selected_union_operations=len(rows), major_stages=major,
        original_durations_preserved=True, pure_compute_time_inferred=False,
        full_source_categories={CATEGORIES[int(k)]: int(v) for k, v in
                                zip(*np.unique(source["category"], return_counts=True))},
        new_simulations_launched=0,
        artifacts_sha256={name: digest(output / name) for name in (
            "SOURCE_CORRESPONDENCE.json", "local_stage_provenance.csv", "major_local_stages.csv")})
    write_json(output / "LOCAL_STAGES.json", result)
    return result
