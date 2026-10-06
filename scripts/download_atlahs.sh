#!/usr/bin/env bash
set -euo pipefail
if [[ $(hostname -s) != eex005 ]]; then
    echo 'Download datasets on eex005 only' >&2
    exit 1
fi
destination=${1:-/home/wangziheng/wafer_simulator/downloads/atlahs/llama16}
mkdir -p "$destination"
url=http://storage2.spcl.ethz.ch/traces/ai/llama/Llama7B_N4_GPU16_TP1_PP1_DP16_BS32/llama.goal
printf '%s\n' "$url" > "$destination/source-url.txt"
# The official data host serves HTTP; its HTTPS port refuses connections.
# Resolve through the server's system resolver (curl's resolver timed out).
server_ip=$(getent ahostsv4 storage2.spcl.ethz.ch | awk 'NR==1 {print $1}')
test -n "$server_ip"
curl --noproxy '*' --resolve "storage2.spcl.ethz.ch:80:$server_ip" \
    --fail --location --retry 3 --retry-delay 3 --connect-timeout 15 \
    --max-time 1800 --speed-time 60 --speed-limit 1024 --continue-at - \
    --dump-header "$destination/download-headers.txt" \
    "$url" --output "$destination/llama.goal.part"
mv "$destination/llama.goal.part" "$destination/llama.goal"
sha256sum "$destination/llama.goal" > "$destination/SHA256SUMS"
stat --printf='%s bytes\n' "$destination/llama.goal"
cat "$destination/SHA256SUMS"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$destination/downloaded-at.txt"
