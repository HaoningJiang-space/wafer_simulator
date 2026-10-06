#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Tests must run on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
test_root="$remote_root/runs/node-reuse-contract-001"
mkdir "$test_root"
candidate="$remote_root/build/booksim-node-reuse/rapidchiplet/booksim2/src"
g++ -std=c++17 -g -O1 -fsanitize=address,undefined -fno-omit-frame-pointer \
    -I"$candidate" "$project_root/tests/native_node_reuse.cpp" "$candidate/credit.cpp" \
    -o "$test_root/node-reuse-sanitized"
ASAN_OPTIONS=detect_leaks=1 "$test_root/node-reuse-sanitized" > "$test_root/node-reuse.log" 2>&1
for variant in runtime-opt node-reuse; do
    native="$remote_root/build/booksim-$variant/rapidchiplet/booksim2/src"
    includes=(-I"$native" -I"$native/allocators" -I"$native/arbiters" -I"$native/routers"
              -I"$native/networks" -I"$native/power" -I"$remote_root/deps/json-source/single_include")
    # Preserve the native globals and GetSimTime definitions while supplying
    # the test's main; the simulator entry point is linked but never invoked.
    g++ -std=c++17 -O3 "${includes[@]}" -Dmain=unused_booksim_main -c "$native/main.cpp" \
        -o "$test_root/$variant-main.o"
    objects=()
    for object in "$native"/*.o "$native"/*/*.o; do
        [[ $(basename "$object") == main.o ]] || objects+=("$object")
    done
    g++ -std=c++17 -O3 "${includes[@]}" "$project_root/tests/native_allocator_replay.cpp" \
        "$test_root/$variant-main.o" "${objects[@]}" -o "$test_root/$variant-allocator"
    "$test_root/$variant-allocator" > "$test_root/$variant-grants.txt"
done
cmp "$test_root/runtime-opt-grants.txt" "$test_root/node-reuse-grants.txt"
sha256sum "$test_root"/*-grants.txt
cat "$test_root/node-reuse.log"
