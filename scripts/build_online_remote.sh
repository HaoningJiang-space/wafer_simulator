#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Build must run on eex005' >&2; exit 1; }
repo=$(cd "$(dirname "$0")/.." && pwd)
root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
native="$root/build/booksim/rapidchiplet/booksim2/src"
out="$root/build/booksim-online"
[[ -f "$native/booksim" && -f "$root/build/booksim/.wafer-patches" ]]
[[ -z $(git -C "$repo" status --porcelain) ]]
# Link the unchanged accepted native objects; only the interface and renamed
# main (global BookSim symbols) are compiled in this separate build directory.
mkdir -p "$out"
includes=(-I"$native" -I"$native/allocators" -I"$native/arbiters" -I"$native/routers"
          -I"$native/networks" -I"$native/power" -I"$root/deps/json-source/single_include")
g++ -std=c++17 -O3 "${includes[@]}" -Dmain=unused_booksim_main -c "$native/main.cpp" -o "$out/globals.o"
g++ -std=c++17 -O3 -Wall "${includes[@]}" -c "$repo/src/wafer_sim/adapters/native/online_booksim.cpp" -o "$out/online.o"
objects=()
for object in "$native"/*.o "$native"/*/*.o; do
    [[ $(basename "$object") == main.o ]] || objects+=("$object")
done
g++ -std=c++17 -O3 "$out/online.o" "$out/globals.o" "${objects[@]}" -o "$out/online_booksim"
sha256sum "$native/booksim" "$out/online_booksim" "${objects[@]}" > "$out/binaries.sha256"
git -C "$repo" rev-parse HEAD > "$out/source_commit"
g++ --version > "$out/compiler.txt"
sha256sum "$out/online_booksim"
