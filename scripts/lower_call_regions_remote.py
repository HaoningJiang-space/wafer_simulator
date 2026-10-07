"""Complete-source call ownership and independent readback on eex005."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import platform
import subprocess
import sys
import time

from wafer_sim.analysis.call_regions import validate_partition
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.chakra_regions import matrix_index, write_partition

ROOT = Path("/home/wangziheng/wafer_simulator")


def process_rank(job):
    rank, source, output, records, expected_sha, expected_nodes = job
    started = time.monotonic()
    path = source / f"rank-{rank:02}.jsonl.gz"
    if digest(path) != expected_sha:
        raise ValueError("Validated source ledger changed")
    report = write_partition(path, output, rank, records)
    if report["nodes"] != expected_nodes:
        raise ValueError("Source not fully partitioned")
    validation = validate_partition(path, output / f"rank-{rank:02}-owners.jsonl.gz",
        output / f"rank-{rank:02}-regions.jsonl.gz", output / f"rank-{rank:02}-edges.jsonl.gz", rank, records)
    if digest(path) != expected_sha:
        raise ValueError("Source changed during normalization")
    validation["elapsed_seconds"] = time.monotonic() - started
    write_json(output / f"rank-{rank:02}-validation.json", validation)
    return report, validation


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full capture processing stays on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("tests", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise ValueError("Fresh absolute output directory required")
    project = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(project), "status", "--porcelain"]):
        raise ValueError("Clean committed source required")
    commit = subprocess.check_output(["git", "-C", str(project), "rev-parse", "HEAD"], text=True).strip()
    tests = read_json(args.tests)
    if not tests["passed"] or tests["source_commit"] != commit or not tests["tests_log_ends_with_ok"]:
        raise ValueError("Passing semantic-test receipt for this commit required")
    log = Path(tests["tests_log"])
    if digest(log) != tests["tests_log_sha256"] or not log.read_text().rstrip().endswith("OK"):
        raise ValueError("Semantic test evidence changed")
    config_path = project / "configs/llama16_call_regions.json"
    config = read_json(config_path)
    source = ROOT / config["effects_directory"]
    receipt_path = source / "EXTRACTED.json"
    validation_path = ROOT / config["effects_validation"]
    matrix_path = ROOT / config["matrix_ledger"]
    for path, sha in ((receipt_path, config["effects_receipt_sha256"]),
                      (validation_path, config["effects_validation_sha256"]),
                      (matrix_path, config["matrix_ledger_sha256"])):
        if digest(path) != sha:
            raise ValueError(f"Pinned source evidence changed: {path.name}")
    receipt, validation = read_json(receipt_path), read_json(validation_path)
    if (not validation["passed"] or validation["extraction_receipt_sha256"] != digest(receipt_path)
            or not receipt["all_files_fully_read"]):
        raise ValueError("Independent full-source correspondence required")
    expected = receipt["artifacts_sha256"]
    if digest(source / "EFFECTS.json") != expected["EFFECTS.json"]:
        raise ValueError("Source effects summary changed")
    effects = read_json(source / "EFFECTS.json")
    matrices = matrix_index(matrix_path)
    ranks = effects["ranks"]
    if (len(ranks) != config["rank_count"] or {r["rank"] for r in ranks} != set(range(config["rank_count"]))
            or set(matrices) != set(range(config["rank_count"]))
            or sum(len(records) for records in matrices.values()) != config["matrix_records"]):
        raise ValueError("Complete sixteen-rank source and matrix set required")
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "STARTED.json", dict(source_commit=commit, config=config,
               config_sha256=digest(config_path), tests_receipt_sha256=digest(args.tests),
               environment=dict(host=platform.node(), python=sys.version, executable=sys.executable),
               complete_target_workload=False, new_simulations_launched=0))
    jobs = [(r["rank"], source, args.output, matrices[r["rank"]],
             expected[f"rank-{r['rank']:02}.jsonl.gz"], r["counts"]["nodes"]) for r in ranks]
    reports, checks, counts = [], [], Counter()
    with ProcessPoolExecutor(max_workers=config["workers"]) as pool:
        for report, check in pool.map(process_rank, jobs):
            reports.append(report); checks.append(check); counts.update(check["counts"])
            print(f"rank={report['rank']} nodes={report['nodes']} regions={report['regions']} "
                  f"refined={report['refined_regions']} independent_readback=True", flush=True)
    if counts["nodes"] != config["nodes"]:
        raise ValueError("Full capture total mismatch")
    write_json(args.output / "REGIONS.json", dict(source_commit=commit, ranks=reports, counts=dict(counts),
        proposed_multi_record_regions=sum(r["proposed_multi_record_regions"] for r in reports),
        refined_regions=sum(r["refined_regions"] for r in reports),
        source_layers_preserved=True, allocation_epochs_resolved=False, exact_footprints_resolved=False,
        source_order_is_target_order=False, complete_target_workload=False,
        simulated_application_time=None, new_simulations_launched=0,
        scope="Disjoint source-call ownership with original dependency ports; not target execution"))
    write_json(args.output / "VALIDATED.json", dict(passed=True, rank_count=len(checks), ranks=checks,
        counts=dict(counts), source_commit=commit, tests_receipt_sha256=digest(args.tests),
        all_source_nodes_owned_once=True, every_source_dependency_preserved=True,
        complete_target_workload=False, new_simulations_launched=0,
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__ == "__main__":
    main()
