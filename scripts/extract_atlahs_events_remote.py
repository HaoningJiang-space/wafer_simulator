"""Extract complete source events; neither modify GOAL nor invoke BookSim."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
args = parser.parse_args()
if platform.node().split(".")[0] != "eex005":
    raise SystemExit("Source event data stays on eex005")
if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
    raise SystemExit("Commit source extraction code before recording evidence")
root = Path("/home/wangziheng/wafer_simulator")
sys.path.insert(0, str(root / "deps/atlahs-provenance"))
from wafer_sim.adapters.atlahs_capture import extract
result = extract(root / "upstream/atlahs", root / "downloads/atlahs/llama16/sqlite-001", args.output)
print(result["counts"], flush=True)
