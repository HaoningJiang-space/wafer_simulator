#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Run must be on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$project_root"
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
output=${1:?Usage: run_full_remote.sh /absolute/path/to/new-run-directory}
[[ $output == /* ]] || { echo 'Use an absolute output path' >&2; exit 1; }
export PYTHONPATH="$project_root/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
"$remote_root/.venv/bin/python" -u -m wafer_sim.cli \
    --config configs/llama16_fixed_state.json \
    --upstream "$remote_root/upstream/nw-design-for-wsi" \
    --binary "$remote_root/build/booksim/rapidchiplet/booksim2/src/booksim" \
    --output "$output"
