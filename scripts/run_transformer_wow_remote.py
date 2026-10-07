"""Run and accept a complete registered online WoW Transformer placement pair."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.experiments.wow_transformer import run_placement
from wafer_sim.io import read_json,write_json,digest


def main():
    if platform.node().split(".")[0] != "eex005": raise SystemExit("Run on eex005")
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("test_receipt",type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    runtime=Path("/home/wangziheng/wafer_simulator")
    commit=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if subprocess.check_output(["git","-C",str(repo),"status","--porcelain"]):
        raise ValueError("Clean committed source required")
    tests=read_json(args.test_receipt)
    if (not tests["passed"] or tests["source_commit"] != commit or
            digest(tests["tests_log"]) != tests["tests_log_sha256"] or
            "test_online_booksim" not in tests["modules"] or
            not Path(tests["tests_log"]).read_text().rstrip().endswith("OK")):
        raise ValueError("Passing same-revision native interface and semantic tests required")
    config=read_json(repo/"configs/transformer_wow_pair.json")
    source_config=repo/config["workload_config"]
    workload=read_json(source_config)
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    write_json(args.output/"CONFIG.json",dict(experiment=config,workload=workload))
    native=runtime/"build/booksim/rapidchiplet/booksim2/src/booksim"
    online=runtime/"build/booksim-online/online_booksim"
    write_json(args.output/"STARTED.json",dict(source_commit=commit,host=platform.node(),
        python=sys.version,executable=sys.executable,executable_sha256=digest(Path(sys.executable).resolve()),
        config_sha256=digest(repo/"configs/transformer_wow_pair.json"),workload_config_sha256=digest(source_config),
        tests_receipt_sha256=digest(args.test_receipt),native_binary_sha256=digest(native),
        online_binary_sha256=digest(online),online_source_sha256=digest(repo/"src/wafer_sim/adapters/native/online_booksim.cpp"),
        build_source_commit=(runtime/"build/booksim-online/source_commit").read_text().strip(),
        linked_objects_manifest_sha256=digest(runtime/"build/booksim-online/binaries.sha256"),
        compiler=(runtime/"build/booksim-online/compiler.txt").read_text(),
        packages=subprocess.check_output([sys.executable,"-m","pip","freeze"],text=True).splitlines()))
    rows=[]
    try:
        for method in config["placements"]:
            row=run_placement(config,workload,args.output,runtime,method)
            rows.append(row)
            print(method,row["booksim_cycles"],row["coarse_cycles"],flush=True)
        if (len(rows)!=2 or len({r["logical_identity"] for r in rows}) != 1 or
                len({r["compute_memory_identity"] for r in rows}) != 1):
            raise ValueError("Pair did not preserve complete work and local resource model")
        write_json(args.output/"SUMMARY.json",dict(source_commit=commit,placements=rows,
            baseline_minus_rotated_cycles=rows[0]["booksim_cycles"]-rows[1]["booksim_cycles"],
            application_speedup=rows[0]["booksim_cycles"]/rows[1]["booksim_cycles"],
            native_wafer_compute_calibrated=False,physical_cost_matched=False,
            complete_block_forward=True,source_trace_replayed=False))
        write_json(args.output/"COMPLETE.json",dict(source_commit=commit,placements=[r["placement"] for r in rows],
            all_execution_and_reference_checks_passed=True,artifacts_sha256={str(p.relative_to(args.output)):digest(p)
                for p in sorted(args.output.rglob("*")) if p.is_file()}))
    except BaseException as error:
        write_json(args.output/"FAILED.json",dict(type=type(error).__name__,message=str(error)))
        raise


if __name__ == "__main__": main()
