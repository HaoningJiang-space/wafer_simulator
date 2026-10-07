"""Full sixteen-rank collective normalization; never a truncated simulation."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.analysis.collective_sources import extract, validate
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.chakra_collectives import match_collectives
from wafer_sim.workloads.collectives import from_match

ROOT = Path("/home/wangziheng/wafer_simulator")


def rank_job(job):
    rank, output, expected = job
    sys.path.insert(0, str(ROOT / "deps/chakra-schema/generated"))
    import et_def_pb2 as schema
    source = ROOT / "downloads/atlahs/llama16-chakra" / f"chakra.{rank}.et"
    if digest(source) != expected["input_sha256"]:
        raise ValueError("Accepted source changed")
    ledger = output / f"rank-{rank:02}-source.jsonl.gz"
    report = extract(source, schema, ledger, rank)
    if report["counts"]["source_nodes"] != expected["nodes"] or report["input_bytes"] != expected["input_bytes"]:
        raise ValueError("Source incompletely read")
    check = validate(source, schema, ledger, report)
    if digest(source) != expected["input_sha256"]:
        raise ValueError("Source changed while processing")
    report.update(input_sha256=expected["input_sha256"], source_ledger_sha256=digest(ledger))
    write_json(output / f"rank-{rank:02}.json", report)
    write_json(output / f"rank-{rank:02}-validation.json", check)
    return report, check


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Complete source processing runs on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("tests", type=Path)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "-C", str(project), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(project), "status", "--porcelain"]):
        raise ValueError("Clean committed source required")
    tests = read_json(args.tests)
    if (not tests["passed"] or tests["source_commit"] != commit or
            digest(tests["tests_log"]) != tests["tests_log_sha256"] or
            not Path(tests["tests_log"]).read_text().rstrip().endswith("OK")):
        raise ValueError("Passing tests for this implementation required")
    source_receipt = ROOT / "runs/chakra-source-003/DECODED.json"
    expected_receipt = project / "docs/results/chakra-normalization-001/DECODED.json"
    if digest(source_receipt) != digest(expected_receipt):
        raise ValueError("Source receipt differs from accepted record")
    support_path = ROOT / "runs/chakra-source-003/SOURCE_SUPPORT.json"
    if digest(support_path) != read_json(source_receipt)["artifacts_sha256"]["SOURCE_SUPPORT.json"]:
        raise ValueError("Source support identity changed")
    support = read_json(support_path)
    for name, sha in support["generated_schema_sha256"].items():
        if digest(ROOT / "deps/chakra-schema/generated" / name) != sha:
            raise ValueError("Generated schema changed")
    if len(support["ranks"]) != 16 or {r["rank"] for r in support["ranks"]} != set(range(16)):
        raise ValueError("Exactly sixteen complete ranks required")
    if not args.output.is_absolute():
        raise ValueError("Use a fresh absolute output directory")
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "STARTED.json", dict(source_commit=commit, source_support_sha256=digest(support_path),
        tests_sha256=digest(args.tests), host=platform.node(), python=sys.version,
        executable=sys.executable, executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable, "-m", "pip", "freeze"], text=True).splitlines(),
        new_simulations_launched=0))
    reports, validations, counts = [], [], Counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for report, check in pool.map(rank_job, [(r["rank"], args.output, r) for r in support["ranks"]]):
            reports.append(report); validations.append(check); counts.update(check["counts"])
            print(f"rank={report['rank']} nodes={report['counts']['source_nodes']} readback_passed=True", flush=True)
    matched = match_collectives(reports)
    calls = {(r["rank"], c["node_id"]): c for r in reports for c in r["calls"]}
    logical = []
    for match in matched["collectives"]:
        if match["participant_and_volume_match"]:
            logical.append(asdict(from_match(match, calls)))
    write_json(args.output / "MATCHES.json", matched)
    write_json(args.output / "LOGICAL.json", dict(collectives=logical, complete_target_workload=False,
        source_aliases_resolved=False, target_data_versions_bound=False, simulated_application_time=None))
    summary = dict(source_commit=commit, counts=dict(counts), rank_count=16,
        cpu_collectives=len(calls), logical_collectives=len(logical),
        matched_calls=sum(len(m["calls"]) for m in matched["collectives"] if m["participant_and_volume_match"]),
        cpu_collectives_without_identity=sum(c["identity"] is None for c in calls.values()),
        logical_kinds=dict(Counter(c["kind"] for c in logical)),
        parser_errors=sum(len(r["errors"]) for r in reports),
        unmatched_gpu_collectives=sum(g["owner"] is None for r in reports for g in r["gpu_collectives"]),
        cross_rank_rejections=dict(Counter(reason for m in matched["collectives"] for reason in m["issues"])),
        complete_target_workload=False, new_simulations_launched=0)
    write_json(args.output / "SUMMARY.json", summary)
    write_json(args.output / "VALIDATED.json", dict(passed=True, ranks=validations, source_commit=commit,
        complete_target_workload=False, full_raw_correspondence_checked=True,
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__ == "__main__":
    main()
