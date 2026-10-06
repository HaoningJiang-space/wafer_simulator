#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Build must run on eex005' >&2; exit 1; }
project_root=$(cd "$(dirname "$0")/.." && pwd)
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
build_root="$remote_root/build/booksim-node-reuse"
commit=9470042fb2d8b5368556e46cc75ac818dbf31522
if [[ ! -d "$build_root" ]]; then
    git -C "$remote_root/upstream/nw-design-for-wsi" worktree add --detach "$build_root" "$commit"
fi
[[ $(git -C "$build_root" rev-parse HEAD) == "$commit" ]]
patches=("$project_root/patches/booksim-completion.patch"
         "$project_root/patches/booksim-topology-ref.patch"
         "$project_root/patches/booksim-runtime-opt.patch"
         "$project_root/patches/booksim-node-reuse.patch")
manifest="$build_root/.wafer-node-reuse-patches"
patch_digest=$(sha256sum "${patches[@]}" | sha256sum | cut -d ' ' -f1)
if [[ -f "$manifest" ]]; then
    read -r recorded_patches recorded_diff < "$manifest"
    [[ "$recorded_patches" == "$patch_digest" ]]
    [[ "$recorded_diff" == "$(git -C "$build_root" diff | sha256sum | cut -d ' ' -f1)" ]]
else
    git -C "$build_root" diff --exit-code
    # Later patches modify the completion patch. Apply in dependency order;
    # checking all patches together compares each against the unpatched tree.
    for patch_file in "${patches[@]}"; do
        git -C "$build_root" apply --check "$patch_file"
        git -C "$build_root" apply "$patch_file"
    done
    # Include the added source header in the recorded working-tree diff.
    git -C "$build_root" add -N rapidchiplet/booksim2/src/node_reuse.hpp
    printf '%s %s\n' "$patch_digest" "$(git -C "$build_root" diff | sha256sum | cut -d ' ' -f1)" > "$manifest"
fi
make -C "$build_root/rapidchiplet/booksim2/src" -j4 \
    CXX="g++ -I$remote_root/deps/json-source/single_include" \
    > "$remote_root/logs/build-node-reuse.log" 2>&1
sha256sum "$build_root/rapidchiplet/booksim2/src/booksim" "${patches[@]}"
