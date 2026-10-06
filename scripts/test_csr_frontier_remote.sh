#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Tests must run on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$project_root"
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
test_root=${WAFER_CSR_TEST_OUTPUT:-"$remote_root/runs/csr-frontier-semantics-001"}
mkdir "$test_root"
export PYTHONPATH="$project_root/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
for variant in node-reuse csr-frontier; do
    export WAFER_TEST_BINARY="$remote_root/build/booksim-$variant/rapidchiplet/booksim2/src/booksim"
    export WAFER_TEST_OUTPUT="$test_root/$variant"
    export WAFER_TEST_DEPENDENCY_PROFILE=0
    [[ $variant != csr-frontier ]] || export WAFER_TEST_DEPENDENCY_PROFILE=1
    if ! "$remote_root/.venv/bin/python" -m unittest discover -s tests -p test_semantics.py \
        > "$test_root/$variant.log" 2>&1; then
        cat "$test_root/$variant.log"
        exit 1
    fi
    tail -n 4 "$test_root/$variant.log"
done
"$remote_root/.venv/bin/python" scripts/verify_dependency_semantics.py \
    "$test_root/node-reuse" "$test_root/csr-frontier" "$test_root/equivalence.json"
