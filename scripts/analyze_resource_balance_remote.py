"""Accept existing rank-local controls and memory balance without simulation."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.resource_balance import analyze
from wafer_sim.io import digest, write_json


def main():
    if platform.node().split(".")[0] != "eex005": raise SystemExit("Run on eex005")
    parser = argparse.ArgumentParser()
    for name in ("historical", "global_run", "local_run", "balance_run", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean committed source required")
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    try:
        summary, details = analyze(args.historical, args.global_run, args.local_run, args.balance_run)
        write_json(args.output / "SUMMARY.json", summary)
        write_json(args.output / "DETAILS.json", details)
        with (args.output / "comparison.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summary["rows"][0]))
            writer.writeheader(); writer.writerows(summary["rows"])
        write_json(args.output / "ANALYZED.json", dict(passed=True,
            source_commit=subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
            runs=summary["runs"], audited_arms=summary["audited_arms"],
            artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
        print((args.output / "comparison.csv").read_text())
    except BaseException as error:
        write_json(args.output / "FAILED.json", dict(type=type(error).__name__, message=str(error)))
        raise


if __name__ == "__main__": main()
