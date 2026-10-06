#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Build must run on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
build_root="$remote_root/build/booksim-runtime-opt"
commit=9470042fb2d8b5368556e46cc75ac818dbf31522
if [[ ! -d "$build_root" ]]; then
    git -C "$remote_root/upstream/nw-design-for-wsi" worktree add --detach "$build_root" "$commit"
fi
[[ $(git -C "$build_root" rev-parse HEAD) == "$commit" ]]
patches=("$project_root/patches/booksim-completion.patch"
         "$project_root/patches/booksim-topology-ref.patch"
         "$project_root/patches/booksim-runtime-opt.patch")
if git -C "$build_root" apply --reverse --check "${patches[@]}" 2>/dev/null; then
    :
else
    git -C "$build_root" diff --exit-code
    git -C "$build_root" apply --check "${patches[@]}"
    git -C "$build_root" apply "${patches[@]}"
fi
make -C "$build_root/rapidchiplet/booksim2/src" -j4 \
    CXX="g++ -I$remote_root/deps/json-source/single_include" \
    > "$remote_root/logs/build-runtime-opt.log" 2>&1
sha256sum "$build_root/rapidchiplet/booksim2/src/booksim" "${patches[@]}"
