#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == ee4e072 ]] || exit 1
repo=$(cd "$(dirname "$0")/.." && pwd)
root=${WAFER_REMOTE_ROOT:-/Projects/haoning/wafer_simulator}
[[ -z $(git -C "$repo" status --porcelain) ]]
commit=9470042fb2d8b5368556e46cc75ac818dbf31522
build="$root/build/booksim-boundary"
if [[ ! -d "$build" ]]; then
    git -C "$root/upstream/nw-design-for-wsi" worktree add --detach "$build" "$commit"
    git -C "$build" apply "$repo/patches/booksim-wafer.patch"
fi
if [[ ! -f "$build/.boundary-patches" ]]; then
    git -C "$build" apply --reverse --check "$repo/patches/booksim-wafer.patch"
    git -C "$build" apply --check "$repo/patches/booksim-endpoint-hooks.patch"
    git -C "$build" apply "$repo/patches/booksim-endpoint-hooks.patch"
    sha256sum "$repo/patches/booksim-wafer.patch" "$repo/patches/booksim-endpoint-hooks.patch" > "$build/.boundary-patches"
else
    sha256sum --check "$build/.boundary-patches"
fi
native="$build/rapidchiplet/booksim2/src"
make -C "$native" -j4 CXX="g++ -I$root/deps/json-source/single_include" > "$build/build.log" 2>&1
includes=(-I"$native" -I"$native/allocators" -I"$native/arbiters" -I"$native/routers" -I"$native/networks" -I"$native/power" -I"$root/deps/json-source/single_include")
g++ -std=c++17 -O3 "${includes[@]}" -Dmain=unused_booksim_main -c "$native/main.cpp" -o "$build/globals.o"
g++ -std=c++17 -O3 -Wall "${includes[@]}" -DWAFER_ENDPOINT_BOUNDARY -c "$repo/src/wafer_sim/adapters/native/online_booksim.cpp" -o "$build/online.o"
objects=()
for object in "$native"/*.o "$native"/*/*.o; do
    [[ $(basename "$object") == main.o ]] || objects+=("$object")
done
g++ -std=c++17 -O3 "$build/online.o" "$build/globals.o" "${objects[@]}" -o "$build/endpoint_booksim"
sha256sum "$build/endpoint_booksim" "${objects[@]}" > "$build/binaries.sha256"
git -C "$repo" rev-parse HEAD > "$build/source_commit"
g++ --version > "$build/compiler.txt"
