#!/usr/bin/env bash
set -euo pipefail
# Run ON eex005 after the source commit has been pushed and checked out.
project_root=$(cd "$(dirname "$0")/.." && pwd)
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
upstream="$remote_root/upstream/nw-design-for-wsi"
build_root="$remote_root/build/booksim-fixed"
commit=9470042fb2d8b5368556e46cc75ac818dbf31522
if [[ $(hostname -s) != eex005 ]]; then
    echo 'Build must run on eex005' >&2
    exit 1
fi
if [[ ! -d "$build_root" ]]; then
    git -C "$upstream" worktree add --detach "$build_root" "$commit"
fi
if [[ $(git -C "$build_root" rev-parse HEAD) != "$commit" ]]; then
    echo 'Unexpected build worktree version' >&2
    exit 1
fi
if git -C "$build_root" apply --reverse --check "$project_root/patches/booksim-completion.patch" 2>/dev/null; then
    : # exact patch already applied
else
    git -C "$build_root" diff --exit-code
    git -C "$build_root" apply --check "$project_root/patches/booksim-completion.patch"
    git -C "$build_root" apply "$project_root/patches/booksim-completion.patch"
fi
mkdir -p "$remote_root/logs"
make -C "$build_root/rapidchiplet/booksim2/src" -j4 \
    CXX="g++ -I$remote_root/deps/json-source/single_include" \
    > "$remote_root/logs/build-fixed.log" 2>&1
sha256sum "$build_root/rapidchiplet/booksim2/src/booksim" \
    "$project_root/patches/booksim-completion.patch"
