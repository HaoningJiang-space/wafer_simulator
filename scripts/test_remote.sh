#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Tests must run on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
cd "$project_root"
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
test_root=${1:?Usage: test_remote.sh /absolute/path/to/new-test-directory [saved-semantic-reference]}
[[ $test_root == /* ]] || { echo 'Use an absolute output path' >&2; exit 1; }
mkdir "$test_root"
native="$remote_root/build/booksim/rapidchiplet/booksim2/src"
export PYTHONPATH="$project_root/src"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
export WAFER_TEST_BINARY="$native/booksim"
export WAFER_TEST_OUTPUT="$test_root/semantics"
export WAFER_TEST_DEPENDENCY_PROFILE=1
if ! "$remote_root/.venv/bin/python" -m unittest discover -s tests -p test_semantics.py \
    > "$test_root/semantics.log" 2>&1; then
    cat "$test_root/semantics.log"
    exit 1
fi
tail -n 4 "$test_root/semantics.log"
export WAFER_NATIVE_REGRESSION_INPUT="$test_root/semantics"
if ! "$remote_root/.venv/bin/python" -m unittest discover -s tests -p test_goal_completion.py \
    > "$test_root/readback.log" 2>&1; then
    cat "$test_root/readback.log"
    exit 1
fi
tail -n 4 "$test_root/readback.log"

# Validate ownership/reset with checked containers; this host lacks ASan runtimes.
g++ -std=c++17 -g -O1 -D_GLIBCXX_DEBUG -D_GLIBCXX_ASSERTIONS \
    -I"$native" "$project_root/tests/native_node_reuse.cpp" "$native/credit.cpp" \
    -o "$test_root/node-reuse-checked"
"$test_root/node-reuse-checked" > "$test_root/node-reuse.log" 2>&1

# Keep arbitration semantics checked against reference-derived grants without
# maintaining a second implementation or building older optimization variants.
includes=(-I"$native" -I"$native/allocators" -I"$native/arbiters" -I"$native/routers"
          -I"$native/networks" -I"$native/power" -I"$remote_root/deps/json-source/single_include")
g++ -std=c++17 -O3 "${includes[@]}" -Dmain=unused_booksim_main -c "$native/main.cpp" \
    -o "$test_root/main.o"
objects=()
for object in "$native"/*.o "$native"/*/*.o; do
    [[ $(basename "$object") == main.o ]] || objects+=("$object")
done
g++ -std=c++17 -O3 "${includes[@]}" "$project_root/tests/native_allocator_replay.cpp" \
    "$test_root/main.o" "${objects[@]}" -o "$test_root/allocator"
"$test_root/allocator" > "$test_root/allocator-grants.txt"
(cd "$test_root" && sha256sum -c "$project_root/tests/fixtures/allocator-grants.sha256")
cat "$test_root/node-reuse.log"

# Optional comparison uses saved events, not another running implementation.
if [[ $# -ge 2 ]]; then
    "$remote_root/.venv/bin/python" scripts/verify_dependency_semantics.py \
        "$2" "$test_root/semantics" "$test_root/equivalence.json"
fi
