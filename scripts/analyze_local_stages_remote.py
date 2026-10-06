"""Check full source association and classify accepted existing critical chains."""
import argparse
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.local_stages import check_correspondence, classify
from wafer_sim.analysis.source_intervals import analyze_intervals
from wafer_sim.io import write_json

parser = argparse.ArgumentParser()
parser.add_argument("regenerated", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
if platform.node().split(".")[0] != "eex005":
    raise SystemExit("Complete source analysis runs on eex005")
if subprocess.check_output(["git", "status", "--porcelain"], text=True).strip():
    raise SystemExit("Commit source analysis before recording evidence")
root = Path("/home/wangziheng/wafer_simulator")
graph = root / "downloads/atlahs/llama16/graph-001"
result = check_correspondence(root / "downloads/atlahs/llama16/llama.goal", graph,
                              args.regenerated, args.output)
write_json(args.output / "analysis_code.json", dict(commit=subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True).strip(), host=platform.node()))
print({k: v for k, v in result.items() if k != "published_npkit_costs_by_observed_key"}, flush=True)
if result["source_correspondence_passed"]:
    print(classify(graph, args.regenerated, root / "runs/postrun-006-attribution-001", args.output)["chains"], flush=True)
    intervals = analyze_intervals(args.regenerated, root / "downloads/atlahs/llama16/sqlite-001", args.output)
    print(dict(intervals_checked=len(intervals["intervals"])), flush=True)
