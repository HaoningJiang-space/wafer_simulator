"""Full sixteen-rank effect extraction; no performance simulation."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
import json
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.analysis.chakra_effects import inspect_effects
from wafer_sim.io import digest, read_json, write_json

ROOT = Path("/home/wangziheng/wafer_simulator")


def inspect_one(job):
    rank, output, expected_sha, expected_nodes, expected_bytes = job
    sys.path.insert(0, str(ROOT / "deps/chakra-schema/generated"))
    import et_def_pb2 as schema
    source = ROOT / "downloads/atlahs/llama16-chakra" / f"chakra.{rank}.et"
    before = source.stat()
    if digest(source) != expected_sha:
        raise ValueError("Source identity changed")
    ledger = output / f"rank-{rank:02}.jsonl.gz"
    report, operators = inspect_effects(source, schema, ledger, rank)
    after = source.stat()
    if ((report["counts"]["nodes"], report["input_bytes"]) != (expected_nodes, expected_bytes)
            or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns)):
        raise ValueError("Incomplete source read or source changed")
    report.update(input_sha256=expected_sha, ledger_sha256=digest(ledger), ledger_bytes=ledger.stat().st_size)
    write_json(output / f"rank-{rank:02}.json", report)
    return report, operators


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full-source processing runs on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise ValueError("Use a fresh absolute output path")
    args.output.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(project), "status", "--porcelain"]):
        raise ValueError("Committed clean source required")
    source_path = ROOT / "runs/chakra-source-003/SOURCE_SUPPORT.json"
    support = read_json(source_path)
    for name, sha in support["generated_schema_sha256"].items():
        if digest(ROOT / "deps/chakra-schema/generated" / name) != sha:
            raise ValueError("Generated official schema changed")
    jobs = [(r["rank"], args.output, r["input_sha256"], r["nodes"], r["input_bytes"]) for r in support["ranks"]]
    if len(jobs) != 16 or {j[0] for j in jobs} != set(range(16)):
        raise ValueError("Exactly sixteen complete source ranks required")
    reports, counts, operators = [], Counter(), Counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for report, ops in pool.map(inspect_one, jobs):
            reports.append(report); counts.update(report["counts"]); operators.update(ops)
            print(f"rank={report['rank']} nodes={report['counts']['nodes']} fully_read=True", flush=True)
    with (args.output / "operator_effects.csv").open("w") as stream:
        writer = csv.writer(stream); writer.writerow(("operator", "category", "occurrences"))
        writer.writerows((*key, count) for key, count in sorted(operators.items()))
    summary = dict(source_commit=subprocess.check_output(["git", "-C", str(project), "rev-parse", "HEAD"], text=True).strip(),
        source_dirty=False, source_support_sha256=digest(source_path), counts=dict(sorted(counts.items())),
        rank_count=len(reports), ranks=reports,
        source_layers_preserved=True, complete_target_workload=False, versions_applied_to_capture=False,
        source_order_is_target_order=False, simulated_application_time=None, new_simulations_launched=0,
        scope="Full source IO effects and unresolved cases; not a lowered logical DAG or target timing")
    write_json(args.output / "EFFECTS.json", summary)
    write_json(args.output / "EXTRACTED.json", dict(all_files_fully_read=True, rank_count=16,
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__ == "__main__":
    main()
