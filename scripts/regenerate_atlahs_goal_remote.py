"""Check complete source reconstruction, without executing the candidate GOAL."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("output", type=Path)
parser.add_argument("--source-host-order", type=int, nargs=4, required=True)
parser.add_argument("--historical", action="store_true")
parser.add_argument("--extracted", type=Path)
parser.add_argument("--observe", action="store_true")
args = parser.parse_args()
if platform.node().split(".")[0] != "eex005":
    raise SystemExit("Complete source reconstruction runs on eex005")
if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
    raise SystemExit("Commit code before recording reconstruction evidence")
root = Path("/home/wangziheng/wafer_simulator")
sys.path.insert(0, str(root / "deps/atlahs-provenance"))
from wafer_sim.adapters.atlahs_capture import regenerate
print(regenerate(args.extracted or root / "runs/local-source-events-001",
                 root / ("upstream/atlahs-20250324" if args.historical else "upstream/atlahs"),
                 root / "downloads/atlahs/llama16/llama.goal", args.output, args.source_host_order,
                 observe=args.observe), flush=True)
