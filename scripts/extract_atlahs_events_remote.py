"""Extract complete source events; neither modify GOAL nor invoke BookSim."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--historical", action="store_true", help="Use the isolated March 2025 author revision")
parser.add_argument("--merge-non-overlap", action="store_true", help="Use the author's existing stream coalescing option")
args = parser.parse_args()
if platform.node().split(".")[0] != "eex005":
    raise SystemExit("Source event data stays on eex005")
if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
    raise SystemExit("Commit source extraction code before recording evidence")
root = Path("/home/wangziheng/wafer_simulator")
sys.path.insert(0, str(root / "deps/atlahs-provenance"))
from wafer_sim.adapters.atlahs_capture import extract, UPSTREAM_COMMIT, HISTORICAL_COMMIT
result = extract(root / ("upstream/atlahs-20250324" if args.historical else "upstream/atlahs"),
                 root / "downloads/atlahs/llama16/sqlite-001", args.output,
                 HISTORICAL_COMMIT if args.historical else UPSTREAM_COMMIT, args.merge_non_overlap)
print(result["counts"], flush=True)
