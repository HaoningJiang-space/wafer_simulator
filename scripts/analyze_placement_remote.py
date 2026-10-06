"""Attribute an accepted complete pair on eex005, without launching simulation."""
import argparse
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.placement_attribution import analyze, finalize
from wafer_sim.experiments.next_experiment import register_mapping_check


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("campaign", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--finalize-equivalence", type=Path)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full event analysis runs only on eex005")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Commit analysis code before recording evidence")
    if args.finalize_equivalence:
        from wafer_sim.io import read_json
        if Path(read_json(args.output / "acceptance.json")["campaign"]).resolve() != args.campaign.resolve():
            raise SystemExit("Finalization campaign differs from the analyzed campaign")
        finalize(args.output, args.finalize_equivalence)
    else:
        analyze(args.campaign, args.output, register_next=register_mapping_check)


if __name__ == "__main__":
    main()
