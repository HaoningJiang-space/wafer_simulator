"""Inventory the complete 16-rank public Llama source on eex005."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import csv
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.io import digest, read_json, write_json
from wafer_sim.analysis.chakra_source import inspect_rank


def inspect_file(job):
    rank, capture, generated, expected_sha = job
    path = capture / f"chakra.{rank}.et"
    sys.path.insert(0, str(generated))
    import et_def_pb2 as schema
    before = path.stat()
    actual = digest(path)
    if actual != expected_sha:
        raise ValueError(f"Input changed: {path}")
    report, signatures, work = inspect_rank(path, schema)
    after = path.stat()
    if report["bytes_read"] != before.st_size or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed or full bytes were not consumed")
    report.update(rank=rank, input_sha256=actual, input_bytes=before.st_size,
                  source_url=(capture / (path.name + ".url")).read_text().strip())
    return report, signatures, work


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full capture processing stays on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise SystemExit("Use a new absolute output directory")
    args.output.mkdir(parents=True, exist_ok=False)
    root = Path("/home/wangziheng/wafer_simulator")
    capture = root / "downloads/atlahs/llama16-chakra"
    upstream = root / "upstream/chakra"
    generated = root / "deps/chakra-schema/generated"
    expected = "9ff3e3e2f276b4c0554a83f8747bf00b2786fa85"
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != expected or subprocess.check_output(["git", "-C", str(upstream), "status", "--porcelain"]):
        raise ValueError("Chakra source must be clean at the pinned commit")
    te = root / "upstream/TransformerEngine"
    te_commit = subprocess.check_output(["git", "-C", str(te), "rev-parse", "HEAD"], text=True).strip()
    if te_commit != "e5edd6cc3d5a868bb3fe4e81088d22aab505a30d" or subprocess.check_output([
            "git", "-C", str(te), "status", "--porcelain"]):
        raise ValueError("TransformerEngine semantic source must match its clean pin")
    files = {f"chakra.{rank}.et" for rank in range(16)}
    if {p.name for p in capture.glob("*.et")} != files or list(capture.glob("*.part")):
        raise ValueError("Complete acquisition of exactly 16 ranks is required")
    sums = {name: sha for sha, name in (line.split() for line in (capture / "SHA256SUMS").read_text().splitlines())}
    if set(sums) != files:
        raise ValueError("Download hash manifest must cover all ranks")
    ranks, signature_totals, total_counts = [], Counter(), Counter()
    jobs = [(rank, capture, generated, sums[f"chakra.{rank}.et"]) for rank in range(16)]
    # Independent complete source files, no simulation order or source event
    # order is changed. Bound host processing to four workers.
    with ProcessPoolExecutor(max_workers=4) as pool, (args.output / "matrix_work.jsonl").open("w") as stream:
        for report, signatures, work in pool.map(inspect_file, jobs):
            rank = report["rank"]
            write_json(args.output / f"rank-{rank:02}.json", report)
            for record in work:
                stream.write(json.dumps(dict(rank=rank, **record), sort_keys=True) + "\n")
            ranks.append({k: v for k, v in report.items() if k != "examples"})
            signature_totals.update(signatures)
            total_counts.update(report["counts"])
            print(f"rank={rank} nodes={report['nodes']} all_bytes_read=True", flush=True)
    with (args.output / "operator_signatures.csv").open("w") as stream:
        writer = csv.writer(stream)
        writer.writerow(("kind", "domain", "name", "input_shapes", "output_shapes", "occurrences"))
        writer.writerows((*signature, count) for signature, count in sorted(signature_totals.items()))
    source_support = root / "runs/spatial-support-001/SOURCE_SUPPORT.json"
    report = dict(source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        source_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], text=True).strip()),
        chakra_commit=revision, python=platform.python_version(),
        te_semantic_reference=dict(commit=te_commit, source_sha256={name: digest(te / name) for name in (
            "transformer_engine/pytorch/csrc/ts_fp8_op.cpp",
            "transformer_engine/common/gemm/cublaslt_gemm.cu",
            "transformer_engine/common/include/transformer_engine/transformer_engine.h")},
            capture_build_version_established=False, kernel_execution=False),
        environment={package: importlib.metadata.version(package) for package in ("protobuf", "grpcio-tools")},
        schema_sha256={p.name: digest(p) for p in sorted((upstream / "schema/protobuf").glob("*.proto"))},
        generated_schema_sha256={p.name: digest(p) for p in sorted(generated.glob("*_pb2.py"))},
        input_sha256=sums, input_bytes=sum(r["input_bytes"] for r in ranks), ranks=ranks,
        rank_count=len(ranks), total_nodes=sum(r["nodes"] for r in ranks), counts=dict(sorted(total_counts.items())),
        source_goals_comparison=dict(same_configuration_label=True, same_capture_established=False,
            atlahs_source_support_sha256=digest(source_support),
            atlahs_collective_event_counts=read_json(source_support)["event_type_counts"]),
        all_files_fully_decoded=True, all_data_graphs_closed_acyclic=all(r["data_dependency_graph"]["closed_acyclic"] for r in ranks),
        full_spatial_execution_ready=False, new_simulations_launched=0,
        interpretation="Complete source inventory, not logical-model acceptance. Control parents are not silently converted to execution predecessors.")
    write_json(args.output / "SOURCE_SUPPORT.json", report)
    write_json(args.output / "DECODED.json", dict(all_files_fully_decoded=True, rank_count=16,
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__ == "__main__":
    main()
