"""Inspect the entire registered graph on eex005; this does not run a simulation."""
import argparse
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.dependency_structure import inspect
from wafer_sim.io import write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("graph_directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Inspect the full input on eex005")
    if args.output.exists():
        raise SystemExit("Refusing to overwrite prior evidence")
    if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
        raise SystemExit("Commit the inspection code before recording evidence")
    result = inspect(args.graph_directory)
    result.update(host=platform.node(), source_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip())
    write_json(args.output, result)
    print(result)


if __name__ == "__main__":
    main()
