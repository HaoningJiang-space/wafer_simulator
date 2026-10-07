"""Read accepted full-block results without launching any simulation."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.wow_transformer import analyze
from wafer_sim.io import digest, write_json


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Run on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean source required")
    if not args.output.is_absolute():
        raise ValueError("Fresh absolute output required")
    report = analyze(args.run)
    args.output.mkdir(exist_ok=False)
    write_json(args.output / "attribution.json", report)
    for field in ("operations", "paths"):
        rows = report[field]
        with (args.output / (field + ".csv")).open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write_json(args.output / "ANALYZED.json", dict(
        source_commit=subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        run=str(args.run.resolve()), input_complete_sha256=report["input_complete_sha256"],
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
    print([(a["placement"], a["application_cycles"], a["peak_outstanding_messages"]) for a in report["arms"]])


if __name__ == "__main__":
    main()
