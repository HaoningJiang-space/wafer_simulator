#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Analysis must run on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$project_root"
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
output=${1:?Usage: postrun_attribution_remote.sh /absolute/path/to/new-analysis-directory}
[[ $output == /* ]] || { echo 'Use an absolute output path' >&2; exit 1; }
candidate="$remote_root/runs/llama16-full-006-csr-frontier"
reference="$remote_root/runs/llama16-full-002"
export PYTHONPATH="$project_root/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
# Waiting consumes no simulation work; failed/excluded evidence is never analyzed.
"$remote_root/.venv/bin/python" -u - "$candidate" <<'PY'
from pathlib import Path
import sys,time
p=Path(sys.argv[1])
deadline=time.monotonic()+93600
while True:
    if any((p/name).exists() for name in ('failures.json','EXCLUDED.json')):
        raise SystemExit('Candidate is failed or excluded')
    if (p/'COMPLETE.json').exists():
        break
    if time.monotonic()>=deadline:
        raise SystemExit('Timed out waiting for complete candidate; no analysis result')
    time.sleep(60)
PY
"$remote_root/.venv/bin/python" -u scripts/analyze_placement_remote.py "$candidate" "$output"
# Architecture analysis is available first; direct 002-vs-006 acceptance follows
# only after the reference has completed its existing full audit.
"$remote_root/.venv/bin/python" -u scripts/verify_full_replay.py \
    "$reference" "$candidate" "$output/implementation_equivalence.json" --wait-seconds 93600
"$remote_root/.venv/bin/python" -u scripts/analyze_placement_remote.py \
    "$candidate" "$output" --finalize-equivalence "$output/implementation_equivalence.json"
