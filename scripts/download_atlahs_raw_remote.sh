#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Raw captures stay on eex005' >&2; exit 1; }
remote_root=${WAFER_REMOTE_ROOT:-/home/wangziheng/wafer_simulator}
destination="$remote_root/downloads/atlahs/llama16/raw"
mkdir -p "$destination"
base=http://storage2.spcl.ethz.ch/traces/ai/llama/Llama7B_N4_GPU16_TP1_PP1_DP16_BS32/nsys_reports
server_ip=$(getent ahostsv4 storage2.spcl.ethz.ch | awk 'NR==1 {print $1}')
test -n "$server_ip"
# Reuse the complete-capture downloader's working server-side resolver path.
options=(--noproxy '*' --resolve "storage2.spcl.ethz.ch:80:$server_ip"
         --fail --location --retry 3 --retry-delay 3 --connect-timeout 15
         --max-time 1800 --speed-time 60 --speed-limit 1024 --silent --show-error)
curl "${options[@]}" "$base/" -o "$destination/index.html"
reports=(nsys_report_nid005785_107285.nsys-rep nsys_report_nid005786_109975.nsys-rep
         nsys_report_nid005789_106910.nsys-rep nsys_report_nid005800_104761.nsys-rep)
for report in "${reports[@]}"; do
    if [[ ! -f "$destination/$report" ]]; then
        curl "${options[@]}" --continue-at - --dump-header "$destination/$report.headers" \
            "$base/$report" -o "$destination/$report.part"
        mv "$destination/$report.part" "$destination/$report"
        printf '%s\n' "$base/$report" > "$destination/$report.url"
    fi
    sha256sum "$destination/$report"
done > "$destination/SHA256SUMS"
date -u +'%Y-%m-%dT%H:%M:%SZ' > "$destination/downloaded-at.txt"
cat "$destination/SHA256SUMS"
