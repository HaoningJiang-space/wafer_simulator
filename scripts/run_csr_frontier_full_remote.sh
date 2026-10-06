#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Run must be on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$project_root"
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
export PYTHONPATH="$project_root/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
"$remote_root/.venv/bin/python" -u -m wafer_sim.cli \
    --config configs/llama16_csr_frontier.json \
    --upstream "$remote_root/upstream/nw-design-for-wsi" \
    --binary "$remote_root/build/booksim-csr-frontier/rapidchiplet/booksim2/src/booksim" \
    --output "$remote_root/runs/llama16-full-006-csr-frontier"
"$remote_root/.venv/bin/python" -u scripts/verify_full_replay.py \
    "$remote_root/runs/llama16-full-005-node-reuse" "$remote_root/runs/llama16-full-006-csr-frontier" \
    "$remote_root/runs/llama16-csr-frontier-equivalence.json" --wait-seconds 93600
