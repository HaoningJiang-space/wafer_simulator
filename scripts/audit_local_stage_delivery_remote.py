"""Read every delivered source row against unchanged operations and totals."""
from collections import Counter
import csv
from datetime import datetime, timezone
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

from wafer_sim.analysis.placement_attribution import _environment
from wafer_sim.io import digest, read_json, write_json

if platform.node().split(".")[0] != "eex005":
    raise SystemExit("Full delivery readback runs on eex005")
root = Path("/home/wangziheng/wafer_simulator")
sys.path.insert(0, str(root / "deps/atlahs-provenance"))
output = root / "runs/local-stage-provenance-001"
ops = np.load(root / "downloads/atlahs/llama16/graph-001/operations.npy", mmap_mode="r")
summary = read_json(output / "LOCAL_STAGES.json")
for name, sha in summary["artifacts_sha256"].items():
    if digest(output / name) != sha:
        raise ValueError(f"Delivered artifact changed: {name}")
totals = {arm: Counter() for arm in ("baseline", "ours_rotated")}
seen = set()
with (output / "local_stage_provenance.csv").open() as stream:
    for row in csv.DictReader(stream):
        op_id = int(row["op_id"])
        if op_id in seen:
            raise ValueError("Duplicate delivered operation")
        seen.add(op_id)
        for column, field in (("host", "rank"), ("label", "label"), ("goal_line", "line"),
                              ("cpu", "cpu"), ("duration_cycles", "amount")):
            if int(row[column]) != int(ops[op_id][field]):
                raise ValueError("Delivered operation differs from original graph")
        for arm, column in (("baseline", "baseline_on_chain"), ("ours_rotated", "rotated_on_chain")):
            if row[column] == "True":
                totals[arm][row["category"]] += int(row["duration_cycles"])
for arm, values in totals.items():
    if dict(values) != summary["chains"][arm]["duration_cycles"]:
        raise ValueError("CSV source category totals differ from report")
if len(seen) != summary["selected_union_operations"]:
    raise ValueError("Delivered chain union is incomplete")
_environment(output, "source_analysis_environment.json")
write_json(output / "PROVENANCE_COMPLETE.json", dict(passed=True, csv_rows=len(seen),
    checked_at=datetime.now(timezone.utc).isoformat(),
    checker_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    checker_sha256=digest(__file__),
    scope="All selected-chain source rows and totals checked; M1 execution acceptance remains separate",
    artifacts_sha256={p.name: digest(p) for p in output.iterdir()
                      if p.is_file() and p.name != "PROVENANCE_COMPLETE.json"}))
print(f"Checked all {len(seen)} delivered local-stage rows", flush=True)
