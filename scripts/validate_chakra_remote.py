"""Independent upstream decode counts and matrix-ledger conservation."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import importlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.io import digest, read_json, write_json

ROOT = Path("/home/wangziheng/wafer_simulator")


def upstream_count(path):
    sys.path.insert(0, str(ROOT / "deps/chakra-schema/generated"))
    sys.path.insert(0, str(ROOT / "upstream/chakra/src/third_party/utils"))
    schema = importlib.import_module("et_def_pb2")
    upstream = importlib.import_module("protolib")
    count = 0
    with path.open("rb") as stream:
        if not upstream.decodeMessage(stream, schema.GlobalMetadata()):
            raise ValueError("Upstream reader could not read metadata")
        node = schema.Node()
        while upstream.decodeMessage(stream, node):
            count += 1
        offset = stream.tell()
    return count, offset


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Complete data validation stays on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("tests", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = read_json(args.source / "DECODED.json")
    for name, sha in receipt["artifacts_sha256"].items():
        if digest(args.source / name) != sha:
            raise ValueError(f"Decoded artifact changed: {name}")
    support = read_json(args.source / "SOURCE_SUPPORT.json")
    paths = [ROOT / "downloads/atlahs/llama16-chakra" / f"chakra.{rank}.et" for rank in range(16)]
    for path in paths:
        if digest(path) != support["input_sha256"][path.name]:
            raise ValueError("Input identity changed")
    with ProcessPoolExecutor(max_workers=4) as pool:
        independent = list(pool.map(upstream_count, paths))
    if any((report["nodes"], report["bytes_read"]) != actual
           for report, actual in zip(support["ranks"], independent)):
        raise ValueError("Official decoder and strict reader differ")
    seen, counts, by_operator, source_scopes = set(), Counter(), Counter(), Counter()
    with (args.source / "matrix_work.jsonl").open() as stream:
        for line in stream:
            work = json.loads(line)
            key = work["rank"], work["node_id"]
            if key in seen or work["source_time_used"] or work["tensor_versions_resolved"]:
                raise ValueError("Duplicate work or unsupported normalization claim")
            seen.add(key)
            a, b = work["inputs"][:2]
            out, = work["outputs"]
            batch = a["shape"][0] if work["operator"] == "aten::bmm" else 1
            # Independent dimension invariant: |A| |B| / (batch |D|) = K^2.
            # The normalizer uses transposed dimensions instead.
            denom = batch * out["num_elements"]
            square, remainder = divmod(a["num_elements"] * b["num_elements"], denom)
            k = math.isqrt(square)
            if remainder or k * k != square or work["work_amount"] != out["num_elements"] * k:
                raise ValueError("Normalized dense MAC count violates element conservation")
            if work["input_logical_bytes"] != sum(t["num_elements"] * t["element_bytes"] for t in work["inputs"]):
                raise ValueError("Logical operand bytes differ")
            if work["output_logical_bytes"] != out["num_elements"] * out["element_bytes"]:
                raise ValueError("Logical output bytes differ")
            if work["operator"] == "tex_ts::te_gemm_ts":
                extra = out["num_elements"] if work["reads_old_destination"] else 0
                if work["extra_scalar_adds"] != extra or len(work["inputs"]) != 2 + bool(extra):
                    raise ValueError("Accumulation work or old-destination dependency differs")
            counts["matrix_primitives"] += 1
            counts["matrix_mac"] += work["work_amount"]
            counts["extra_scalar_adds"] += work.get("extra_scalar_adds", 0)
            counts["with_direct_gpu_child"] += bool(work["direct_gpu_children"])
            by_operator[work["operator"]] += 1
            source_scopes[str(work["source_profiler_step"])] += 1
    for key in ("matrix_primitives", "matrix_mac", "extra_scalar_adds"):
        if counts[key] != support["counts"]["normalized_" + key]:
            raise ValueError("Matrix inventory totals differ")
    logs = args.tests.read_text()
    if not logs.rstrip().endswith("OK"):
        raise ValueError("Semantic test log did not pass")
    result = dict(passed=True, strict_and_official_reader_match_all_ranks=True,
        source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        normalization_commit=support["source_commit"], full_rank_count=16,
        total_nodes=sum(n for n, _ in independent), total_input_bytes=sum(size for _, size in independent),
        matrix_counts=dict(counts), matrix_operator_counts=dict(by_operator),
        matrix_source_scopes=dict(source_scopes),
        source_support_sha256=digest(args.source / "SOURCE_SUPPORT.json"),
        source_receipt_sha256=digest(args.source / "DECODED.json"),
        matrix_ledger_sha256=digest(args.source / "matrix_work.jsonl"),
        semantic_tests_log=dict(path=str(args.tests), sha256=digest(args.tests)),
        upstream_decoder_sha256=digest(ROOT / "upstream/chakra/src/third_party/utils/protolib.py"),
        scope="Full-file decoding and partial matrix-work conservation, not complete spatial execution or target timing",
        simulated_application_time=None, new_simulations_launched=0)
    write_json(args.output / "VALIDATION.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
