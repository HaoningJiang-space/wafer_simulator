"""Independent full-source/ledger correspondence and effect-role readback."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
import gzip
import hashlib
from itertools import zip_longest
import json
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.chakra import read_metadata, nodes, decode_io

ROOT = Path("/home/wangziheng/wafer_simulator")


def validate_rank(job):
    rank, source_dir, expected = job
    sys.path.insert(0, str(ROOT / "deps/chakra-schema/generated"))
    import et_def_pb2 as schema
    raw = ROOT / "downloads/atlahs/llama16-chakra" / f"chakra.{rank}.et"
    if digest(raw) != expected["input_sha256"]:
        raise ValueError("Original source changed")
    counts, categories, detail = Counter(), Counter(), Counter()
    cpu_calls, child_counts, ids = {}, Counter(), set()
    common_digest = hashlib.sha256()
    with raw.open("rb") as stream, gzip.open(source_dir / f"rank-{rank:02}.jsonl.gz", "rt") as ledger:
        read_metadata(stream, schema)
        for original, line in zip_longest(nodes(stream, schema), ledger):
            if original is None or line is None:
                raise ValueError("Ledger has missing or extra source nodes")
            offset, node = original
            row = json.loads(line)
            common = dict(rank=rank, node_id=node.id, byte_offset=offset, name=node.name,
                          source_ctrl_deps=list(node.ctrl_deps), source_data_deps=list(node.data_deps))
            if any(row[k] != v for k, v in common.items()) or node.id in ids:
                raise ValueError("Source identities or dependencies differ")
            ids.add(node.id)
            common_digest.update((json.dumps(common, sort_keys=True) + "\n").encode())
            effect = row["effects"]; category = effect["category"]
            categories[category] += 1
            counts["nodes"] += 1
            counts["control_references"] += len(node.ctrl_deps)
            counts["data_dependencies"] += len(node.data_deps)
            attrs = {a.name: a for a in node.attr}
            cpu = attrs["is_cpu_op"].bool_val
            if row["source_domain"] != ("CPU" if cpu else "GPU"):
                raise ValueError("Source domain changed")
            if cpu and node.type != schema.METADATA_NODE:
                cpu_calls[node.id] = (node.name, category)
                child_counts.update(node.ctrl_deps)
            if "inputs" not in effect:
                continue  # unresolved descriptor is retained, not semantically accepted
            refs = effect["inputs"] + effect["outputs"]
            by_path = {ref["path"]: ref for ref in refs}
            if len(by_path) != len(refs):
                raise ValueError("Duplicate operand identity")
            original_io = dict(i=decode_io(node.inputs), o=decode_io(node.outputs))
            for ref in refs:
                side, indices = ref["path"].split(":")
                values, shapes, types = original_io[side]
                parts = list(map(int, indices.split(".")))
                value, shape = values[parts[0]], shapes[parts[0]]
                for index in parts[1:]:
                    value, shape = value[index], shape[index]
                wanted = [ref[k] for k in ("tensor_id", "storage_id", "source_offset", "num_elements",
                                            "element_bytes", "source_device")]
                if value != wanted or shape != ref["shape"]:
                    raise ValueError("Tensor descriptor changed")
            for role in ("reads", "writes", "allocations", "metadata_inputs", "potential_writes",
                         "operand_inputs", "result_outputs"):
                if any(p not in by_path for p in effect.get(role, [])):
                    raise ValueError("Effect references a missing tensor")
            if category in {"allocate_uninitialized", "alias", "schema_functional", "declared_mutation", "storage_rebind"}:
                if effect["writes"]:
                    raise ValueError("Non-writing/unresolved rule invented a definite byte write")
            if category == "alias":
                if effect["allocations"] or effect["reads"]:
                    raise ValueError("Alias invented allocation or tensor read")
                for alias in effect["aliases"]:
                    out = by_path[alias["output"]]
                    if not alias["inputs"] or any((by_path[p]["storage_id"], by_path[p]["source_device"]) !=
                            (out["storage_id"], out["source_device"]) for p in alias["inputs"]):
                        raise ValueError("Alias crossed storage identity")
            if node.name == "tex_ts::te_gemm_ts" and category == "write":
                accumulating = bool(original_io["i"][0][20])
                if effect["reads"] != ["i:0", "i:5"] + (["i:10"] if accumulating else []):
                    raise ValueError("GEMM destination access differs")
                if effect["writes"] != ["o:0"] or effect["allocations"] or "i:18" in effect["reads"]:
                    raise ValueError("GEMM output or workspace became wrong logical activity")
            if effect["source_durations_used"] or effect["allocation_epochs_resolved"] or effect["exact_footprints_resolved"]:
                raise ValueError("Unsupported source-to-target claim")
            meta = any(ref["source_device"] == "meta" and ref["num_elements"] for ref in refs)
            if row["contains_meta_tensors"] != meta:
                raise ValueError("Meta-device activity mislabeled")
            detail[(node.name, category, meta)] += 1
        if stream.tell() != expected["input_bytes"]:
            raise ValueError("Incomplete source bytes")
    if counts["nodes"] != expected["counts"]["nodes"]:
        raise ValueError("Full node totals differ")
    if any(categories[key.removeprefix("category:")] != value for key, value in expected["counts"].items()
           if key.startswith("category:")):
        raise ValueError("Effect categories differ")
    leaves = Counter(key for node, key in cpu_calls.items() if not child_counts[node])
    counts["cpu_calls_with_cpu_children"] = sum(bool(child_counts[n]) for n in cpu_calls)
    counts["cpu_leaf_calls"] = sum(leaves.values())
    return dict(rank=rank, counts=dict(counts), correspondence_sha256=common_digest.hexdigest(), passed=True), leaves, detail


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full-source verification stays on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("tests", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = read_json(args.source / "EXTRACTED.json")
    for name, sha in receipt["artifacts_sha256"].items():
        if digest(args.source / name) != sha:
            raise ValueError("Extraction artifact changed")
    summary = read_json(args.source / "EFFECTS.json")
    if not receipt["all_files_fully_read"] or summary["rank_count"] != 16:
        raise ValueError("Full extraction required")
    if not args.tests.read_text().rstrip().endswith("OK"):
        raise ValueError("Semantic tests did not pass")
    reports, counts, leaves, details = [], Counter(), Counter(), Counter()
    jobs = [(r["rank"], args.source, r) for r in summary["ranks"]]
    if {j[0] for j in jobs} != set(range(16)) or len(jobs) != 16:
        raise ValueError("Complete rank set required")
    with ProcessPoolExecutor(max_workers=4) as pool:
        for report, leaf, detail in pool.map(validate_rank, jobs):
            reports.append(report); counts.update(report["counts"]); leaves.update(leaf); details.update(detail)
            print(f"rank={report['rank']} source_and_ledger_match=True", flush=True)
    for name, header, values in (
        ("cpu_leaf_effects.csv", ("operator", "category", "occurrences"), leaves),
        ("operator_meta_effects.csv", ("operator", "category", "contains_meta_tensors", "occurrences"), details)):
        with (args.output / name).open("w") as stream:
            writer = csv.writer(stream); writer.writerow(header)
            writer.writerows((*key, count) for key, count in sorted(values.items()))
    write_json(args.output / "VALIDATION.json", dict(passed=True, ranks=reports, counts=dict(counts),
        extraction_commit=summary["source_commit"], source_commit=subprocess.check_output([
            "git", "rev-parse", "HEAD"], text=True).strip(),
        extraction_receipt_sha256=digest(args.source / "EXTRACTED.json"),
        effects_summary_sha256=digest(args.source / "EFFECTS.json"),
        tests=dict(path=str(args.tests), sha256=digest(args.tests)),
        derived_artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir())},
        full_source_identity_and_dependencies_match=True, role_bindings_checked=True,
        complete_target_workload=False, new_simulations_launched=0,
        scope="Exact complete-source correspondence and declared operator effects; no flattened DAG or target timing"))


if __name__ == "__main__":
    main()
