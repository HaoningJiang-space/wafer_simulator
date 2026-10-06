#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Raw capture conversion stays on eex005' >&2; exit 1; }
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
raw="$remote_root/downloads/atlahs/llama16/raw"
destination=${1:?Usage: export_atlahs_raw_remote.sh NEW_SQLITE_DIRECTORY}
mkdir "$destination"
sha256sum -c "$raw/SHA256SUMS"
nsys --version > "$destination/nsys-version.txt"
for report in "$raw"/*.nsys-rep; do
    name=$(basename "$report" .nsys-rep)
    nsys export --type sqlite --output "$destination/$name.sqlite" "$report"
done
sha256sum "$destination"/*.sqlite > "$destination/SHA256SUMS"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$destination/exported-at.txt"
