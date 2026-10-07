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
    parser.add_argument("--study",action="store_true",help="Registered eight-head TP4/TP8 and two-policy study")
    parser.add_argument("--serial-control",action="store_true",help="TP2 diagnostic: serialize the same corrected collective actions")
    parser.add_argument("--global-completion-control",action="store_true",help="Retain historical collective publication at global retirement")
    parser.add_argument("--balance",action="store_true",help="Registered TP8 row-major memory-bandwidth pairs")
    parser.add_argument("--tree",action="store_true",help="Fixed logical binary tree at three registered memory regimes")
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
    if sum((args.study,args.serial_control,args.balance,args.tree))>1: raise ValueError("Separate study, balance, tree and serial control")
    if (args.balance or args.tree) and args.global_completion_control: raise ValueError("Study uses registered rank-local semantics")
    if args.serial_control: config["action_schedule"]="serial_control"
    if args.global_completion_control:
        config["execution_policy"]["collective_completion"]="global_retirement"
    source_config=repo/config["workload_config"]
    workload=read_json(source_config)
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    study=read_json(repo/"configs/transformer_collective_study.json") if args.study else None
    balance_path=repo/("configs/transformer_tree_study.json" if args.tree else "configs/transformer_resource_balance.json")
    balance=read_json(balance_path) if args.balance or args.tree else None
    if args.tree:
        config["execution_policy"]["collective_algorithm"]=balance["collective_algorithm"]
    write_json(args.output/"CONFIG.json",dict(experiment=config,workload=workload,study=study,balance=balance))
    native=runtime/"build/booksim/rapidchiplet/booksim2/src/booksim"
    online=runtime/"build/booksim-online/online_booksim"
    write_json(args.output/"STARTED.json",dict(source_commit=commit,host=platform.node(),
        python=sys.version,executable=sys.executable,executable_sha256=digest(Path(sys.executable).resolve()),
        config_sha256=digest(repo/"configs/transformer_wow_pair.json"),workload_config_sha256=digest(source_config),
        study_config_sha256=digest(repo/"configs/transformer_collective_study.json") if study else None,
        balance_config_sha256=digest(balance_path) if balance else None,
        tests_receipt_sha256=digest(args.test_receipt),native_binary_sha256=digest(native),
        online_binary_sha256=digest(online),online_source_sha256=digest(repo/"src/wafer_sim/adapters/native/online_booksim.cpp"),
        build_source_commit=(runtime/"build/booksim-online/source_commit").read_text().strip(),
        linked_objects_manifest_sha256=digest(runtime/"build/booksim-online/binaries.sha256"),
        compiler=(runtime/"build/booksim-online/compiler.txt").read_text(),
        packages=subprocess.check_output([sys.executable,"-m","pip","freeze"],text=True).splitlines()))
    rows=[]
    try:
        if study or balance:
            cases=[]
            variants=([(p,m,workload["memory_bytes_per_cycle"],study["heads"],f"tp{p}-{m}")
                       for p in study["shards"] for m in study["mappings"]] if study else
                      [(balance["shards"],balance["mapping"],bw,balance["heads"],f"memory-{bw}")
                       for bw in balance["memory_bytes_per_cycle"]])
            for shards,mapping,bw,heads,name in variants:
                    directory=args.output/name;directory.mkdir()
                    case_config=dict(config,mapping=mapping)
                    case_workload=dict(workload,memory_bytes_per_cycle=bw,
                                       block=dict(workload["block"],heads=heads,shards=shards))
                    write_json(directory/"CONFIG.json",dict(experiment=case_config,workload=case_workload))
                    pair=[run_placement(case_config,case_workload,directory,runtime,m) for m in config["placements"]]
                    if (len({r["logical_identity"] for r in pair}) != 1 or
                            len({r["compute_memory_identity"] for r in pair}) != 1):
                        raise ValueError("Study pair changed work or local resources")
                    case=dict(name=name,shards=shards,mapping=mapping,memory_bytes_per_cycle=bw,placements=pair)
                    write_json(directory/"SUMMARY.json",case)
                    cases.append(dict(case,placements=[{k:v for k,v in r.items() if k not in {"messages","worker_locations"}}
                                                       for r in pair]))
                    print(name,[(r["placement"],r["booksim_cycles"],r["peak_outstanding_messages"]) for r in pair],flush=True)
            for shards in sorted({v[0] for v in variants}):
                selected=[r for c in cases if c["shards"]==shards for r in c["placements"]]
                if len({r["logical_identity"] for r in selected})!=1:
                    raise ValueError("Mapping changed the logical workload")
            write_json(args.output/"SUMMARY.json",dict(source_commit=commit,cases=cases,
                native_wafer_compute_calibrated=False,physical_cost_matched=False))
            write_json(args.output/"COMPLETE.json",dict(source_commit=commit,cases=[c["name"] for c in cases],
                all_execution_and_reference_checks_passed=True,artifacts_sha256={str(p.relative_to(args.output)):digest(p)
                    for p in sorted(args.output.rglob("*")) if p.is_file()}))
            return
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
