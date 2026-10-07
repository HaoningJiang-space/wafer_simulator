"""Recover all accepted collective calls on eex005; no placement simulation."""
import argparse
from collections import Counter
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.analysis.collective_recovery import join_recovery
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.workloads.collective_recovery import recover

ROOT = Path("/home/wangziheng/wafer_simulator")


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full source processing stays on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("tests", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean committed source required")
    tests = read_json(args.tests)
    if (not tests["passed"] or tests["source_commit"] != commit or
            digest(tests["tests_log"]) != tests["tests_log_sha256"] or
            not Path(tests["tests_log"]).read_text().rstrip().endswith("OK")):
        raise ValueError("Passing semantic tests for this commit required")
    if not args.output.is_absolute():
        raise ValueError("Fresh absolute output required")
    inputs, paths = {}, {}
    for kind, run, checked in (("calls", "collective-source-003", "collectives-001"),
                                ("ports", "collective-ports-001", "collective-values-001")):
        receipt = ROOT / "runs" / run / "VALIDATED.json"
        if digest(receipt) != digest(repo / "docs/results" / checked / "VALIDATED.json"):
            raise ValueError("Accepted receipt changed")
        inputs[str(receipt)] = digest(receipt)
        hashes = read_json(receipt)["artifacts_sha256"]
        for rank in range(16):
            name = f"rank-{rank:02}.json" + ("l.gz" if kind == "ports" else "")
            path = ROOT / "runs" / run / name
            if digest(path) != hashes[name]:
                raise ValueError("Accepted source ledger changed")
            inputs[str(path)], paths[kind, rank] = hashes[name], path
    reports = [read_json(paths["calls", r]) for r in range(16)]
    plans, barriers, matches = recover(reports)
    if len(plans) != 33632:
        raise ValueError("Complete call coverage changed")
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "STARTED.json", dict(source_commit=commit, host=platform.node(),
        tests_sha256=digest(args.tests), python=sys.version, executable=sys.executable,
        executable_sha256=digest(Path(sys.executable).resolve()), inputs_sha256=inputs,
        new_simulations_launched=0))
    counts, issues = Counter(), Counter()
    for rank in range(16):
        counts.update(join_recovery(paths["ports", rank], args.output / f"rank-{rank:02}.jsonl.gz", rank, plans))
    for plan in plans.values():
        issues.update(plan["required_binding_evidence"])
    write_json(args.output / "BARRIERS.json", dict(bindings=barriers, calibrated_control_time=False))
    write_json(args.output / "MATCHES.json", matches)
    summary = dict(source_commit=commit, counts=dict(counts), required_evidence_counts=dict(issues),
        bound_barrier_instances=len(barriers), matched_instances=len(matches["collectives"]),
        supported_instances=sum(not m["issues"] for m in matches["collectives"]),
        all_calls_retained=True, complete_target_workload=False, new_simulations_launched=0)
    write_json(args.output / "SUMMARY.json", summary)
    for path, sha in inputs.items():
        if digest(path) != sha:
            raise ValueError("Input changed during recovery")
    write_json(args.output / "VALIDATED.json", dict(passed=True, source_commit=commit,
        all_calls_retained=True, complete_target_workload=False,
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
    print(summary, flush=True)


if __name__ == "__main__":
    main()
