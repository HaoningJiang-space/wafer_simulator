#!/usr/bin/env bash
# All 16 published ranks, never a sampled/truncated application input.
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Capture downloads stay on eex005' >&2; exit 1; }
root=/home/wangziheng/wafer_simulator
base=http://storage2.spcl.ethz.ch/traces/astra-sim-traces/Llama7B_N4_GPU16_TP1_PP1_DP16_BS32
destination="$root/downloads/atlahs/llama16-chakra"
mkdir -p "$destination"
server_ip=$(getent ahostsv4 storage2.spcl.ethz.ch | awk 'NR==1 {print $1}')
test -n "$server_ip"
options=(--noproxy '*' --resolve "storage2.spcl.ethz.ch:80:$server_ip"
         --fail --location --retry 3 --retry-delay 3 --connect-timeout 15
         --max-time 1800 --speed-time 60 --speed-limit 1024 --silent --show-error)
curl "${options[@]}" "$base/" -o "$destination/index.html"
for rank in {0..15}; do
    name="chakra.$rank.et"
    if [[ ! -f "$destination/$name" ]]; then
        curl "${options[@]}" --continue-at - --dump-header "$destination/$name.headers" \
            "$base/$name" -o "$destination/$name.part"
        mv "$destination/$name.part" "$destination/$name"
        printf '%s\n' "$base/$name" > "$destination/$name.url"
    fi
    printf 'Downloaded rank %s\n' "$rank"
done
(cd "$destination" && sha256sum chakra.{0..15}.et > SHA256SUMS)
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$destination/downloaded-at.txt"
# This receipt states byte acquisition only, not semantic completeness/equivalence.
printf '%s\n' 'All 16 files acquired; schema/content validation remains required.'
