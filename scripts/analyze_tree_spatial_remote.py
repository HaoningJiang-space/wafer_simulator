"""Read and independently check the registered tree/direct spatial comparison."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.collective_projection import analyze
from wafer_sim.io import write_json, digest


def main():
    if platform.node().split(".")[0] != "eex005": raise SystemExit("Run on eex005")
    parser = argparse.ArgumentParser()
    for name in ("direct", "tree", "output"): parser.add_argument(name, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean source required")
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    try:
        summary, details = analyze(args.direct, args.tree)
        write_json(args.output / "SUMMARY.json", summary)
        # Each compact mechanism record omits the full service chain, which
        # remains in the accepted remote execution directories.
        for key, detail in details.items():
            write_json(args.output / (key.replace("/", "-") + ".json"), detail)
        write_json(args.output / "MECHANISMS.json", {key: dict(work=d["work"],
            critical_transfers=d["critical_transfers"], collectives=d["collectives"],
            endpoints=d["spatial"]["endpoint_rows"], cut=d["spatial"]["cut"])
            for key, d in details.items()})
        with (args.output / "comparison.csv").open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(summary["rows"][0]))
            writer.writeheader(); writer.writerows(summary["rows"])
        write_json(args.output / "ANALYZED.json", dict(passed=True, runs=summary["runs"],
            current_audited_arms=summary["current_audited_arms"],
            source_commit=subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
            artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
        print((args.output / "comparison.csv").read_text())
    except BaseException as error:
        write_json(args.output / "FAILED.json", dict(type=type(error).__name__, message=str(error)))
        raise


if __name__ == "__main__": main()
