"""Join complete accepted source ledgers on eex005; no simulation launch."""
import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.analysis.collective_ports import join_ports
from wafer_sim.io import digest,read_json,write_json

ROOT=Path("/home/wangziheng/wafer_simulator")


def job(args):
    rank,out,expected=args
    paths={"collectives":ROOT/f"runs/collective-source-003/rank-{rank:02}.json",
           "effects":ROOT/f"runs/tensor-effects-001/rank-{rank:02}.jsonl.gz",
           "owners":ROOT/f"runs/call-regions-002/rank-{rank:02}-owners.jsonl.gz"}
    for key,path in paths.items():
        if digest(path)!=expected[key]: raise ValueError("Accepted input ledger changed")
    result=join_ports(read_json(paths["collectives"]),paths["effects"],paths["owners"],out/f"rank-{rank:02}.jsonl.gz")
    result["inputs_sha256"]={str(path):expected[key] for key,path in paths.items()}
    for key,path in paths.items():
        if digest(path)!=expected[key]: raise ValueError("Input changed during join")
    write_json(out/f"rank-{rank:02}.json",result)
    return result


def main():
    if platform.node().split(".")[0]!="eex005": raise SystemExit("Source processing stays on eex005")
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path); parser.add_argument("tests",type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    commit=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if subprocess.check_output(["git","-C",str(repo),"status","--porcelain"]):
        raise ValueError("Clean committed source required")
    tests=read_json(args.tests)
    if (not tests["passed"] or tests["source_commit"]!=commit or digest(tests["tests_log"])!=tests["tests_log_sha256"]
            or not Path(tests["tests_log"]).read_text().rstrip().endswith("OK")):
        raise ValueError("Passing tests for this commit required")
    receipts={}
    for name,remote,local in (
        ("collectives","collective-source-003/VALIDATED.json","collectives-001/VALIDATED.json"),
        ("owners","call-regions-002/VALIDATED.json","call-regions-001/VALIDATED.json"),
        ("effects","tensor-effects-001/EXTRACTED.json","tensor-effects-001/EXTRACTED.json")):
        path=ROOT/"runs"/remote
        if digest(path)!=digest(repo/"docs/results"/local): raise ValueError("Accepted receipt changed")
        receipts[name]=read_json(path)
    if not args.output.is_absolute(): raise ValueError("Absolute fresh output required")
    args.output.mkdir(parents=True,exist_ok=False)
    write_json(args.output/"STARTED.json",dict(source_commit=commit,tests_sha256=digest(args.tests),
        host=platform.node(),python=sys.version,executable=sys.executable,executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,"-m","pip","freeze"],text=True).splitlines(),new_simulations_launched=0))
    jobs=[]
    for rank in range(16):
        names={"collectives":f"rank-{rank:02}.json","effects":f"rank-{rank:02}.jsonl.gz","owners":f"rank-{rank:02}-owners.jsonl.gz"}
        jobs.append((rank,args.output,{key:receipts[key]["artifacts_sha256"][name] for key,name in names.items()}))
    reports=[]; counts=Counter()
    with ProcessPoolExecutor(max_workers=4) as pool:
        for report in pool.map(job,jobs):
            reports.append(report); counts.update(report["counts"])
            print(f"rank={report['rank']} nodes={report['counts']['source_nodes']} ports_checked=True",flush=True)
    if counts["source_nodes"]!=4530939 or counts["collective_calls"]!=33632:
        raise ValueError("Complete source/call counts differ")
    write_json(args.output/"SUMMARY.json",dict(source_commit=commit,counts=dict(counts),ranks=reports,
        value_versions_bound=False,complete_target_workload=False,new_simulations_launched=0))
    write_json(args.output/"VALIDATED.json",dict(passed=True,source_commit=commit,rank_count=16,
        all_collective_ports_joined=True,value_versions_bound=False,complete_target_workload=False,
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__=="__main__": main()
