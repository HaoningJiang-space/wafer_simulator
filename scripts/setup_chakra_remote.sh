#!/usr/bin/env bash
set -euo pipefail
[[ $(hostname -s) == eex005 ]] || { echo 'Schema generation runs on eex005' >&2; exit 1; }
project=$(cd "$(dirname "$0")/.." && pwd)
root=/home/wangziheng/wafer_simulator
"$root/.venv/bin/python" "$project/scripts/restore_upstreams_remote.py" --check
dep="$root/deps/chakra-schema"
mkdir -p "$dep/generated"
if [[ ! -x "$dep/venv/bin/python" ]]; then
    "$root/.venv/bin/python" -m venv "$dep/venv"
fi
"$dep/venv/bin/pip" install --timeout 15 --retries 1 -r "$project/configs/chakra_schema_requirements.txt"
schema="$root/upstream/chakra/schema/protobuf"
"$dep/venv/bin/python" -m grpc_tools.protoc -I "$schema" --python_out="$dep/generated" \
    "$schema/et_def.proto" "$schema/storage.proto"
"$dep/venv/bin/pip" freeze > "$dep/requirements.lock"
