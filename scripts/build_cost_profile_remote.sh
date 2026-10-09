#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == ee4e072 ]] || { echo 'Build on hn072' >&2; exit 1; }
repo=$(cd "$(dirname "$0")/.." && pwd)
root=${WAFER_REMOTE_ROOT:-/Projects/haoning/wafer_simulator}
out=${1:?Fresh absolute isolated build directory required}
[[ "$out" == "$root/build/"* && ! -e "$out" ]]
[[ -z $(git -C "$repo" status --porcelain) ]]
mkdir "$out"
# Migration retained accepted binaries, not intermediate objects. Rebuild only
# in this isolated copy of the delivered pinned ordinary upstream sources.
cp -a "$repo/third_party/nw-design-for-wsi" "$out/upstream"
patch -d "$out/upstream" -p1 < "$repo/patches/booksim-wafer.patch"
native="$out/upstream/rapidchiplet/booksim2/src"
parser_tools="$root/deps/parser-tools-001"
[[ -x "$parser_tools/usr/bin/flex" && -x "$parser_tools/usr/bin/bison" ]]
BISON_PKGDATADIR="$parser_tools/usr/share/bison" make -C "$native" -j4 \
    LEX="$parser_tools/usr/bin/flex" YACC="$parser_tools/usr/bin/bison -y" \
    CXX="g++ -I$root/deps/json-source/single_include" > "$out/build.log" 2>&1
cp "$parser_tools/PACKAGES.sha256" "$out/parser-tools.sha256"
cp "$repo/src/wafer_sim/adapters/native/online_booksim.cpp" "$out/online_booksim.cpp"
patch -d "$out" -p1 < "$repo/patches/online-booksim-cost-profile.patch"
includes=(-I"$native" -I"$native/allocators" -I"$native/arbiters" -I"$native/routers"
          -I"$native/networks" -I"$native/power" -I"$root/deps/json-source/single_include")
g++ -std=c++17 -O3 "${includes[@]}" -Dmain=unused_booksim_main -c "$native/main.cpp" -o "$out/globals.o"
g++ -std=c++17 -O3 -Wall "${includes[@]}" -c "$out/online_booksim.cpp" -o "$out/online.o"
objects=()
for object in "$native"/*.o "$native"/*/*.o; do
    [[ $(basename "$object") == main.o ]] || objects+=("$object")
done
g++ -std=c++17 -O3 "$out/online.o" "$out/globals.o" "${objects[@]}" -o "$out/online_booksim"
sha256sum "$out/online_booksim" "$out/online_booksim.cpp" "$repo/patches/online-booksim-cost-profile.patch" "$repo/patches/booksim-wafer.patch" \
    "$root/build/booksim-online/online_booksim" "$native/booksim" "${objects[@]}" > "$out/binaries.sha256"
git -C "$repo" rev-parse HEAD > "$out/source_commit"
g++ --version > "$out/compiler.txt"
sha256sum "$out/online_booksim"
