"""Validate finished study identities and summarize existing native events."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess
from statistics import mean

from wafer_sim.analysis.collective_contention import summarize
from wafer_sim.io import read_json, write_json, digest


def main():
    if platform.node().split(".")[0] != "eex005": raise SystemExit("Run on eex005")
    parser=argparse.ArgumentParser()
    parser.add_argument("run",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git","-C",str(repo),"status","--porcelain"]):
        raise ValueError("Clean source required")
    complete=read_json(args.run/"COMPLETE.json")
    if (args.run/"FAILED.json").exists() or not complete["all_execution_and_reference_checks_passed"]:
        raise ValueError("Accepted complete study required")
    for name,h in complete["artifacts_sha256"].items():
        if digest(args.run/name)!=h: raise ValueError("Changed artifact: "+name)
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    rows=[]
    for case in read_json(args.run/"SUMMARY.json")["cases"]:
        for arm in case["placements"]:
            directory=args.run/case["name"]/arm["placement"]
            record=read_json(directory/"execution.json")
            result=record["booksim"]
            traffic=summarize(read_json(directory/"network.json"),result["network_messages"])
            chain=read_json(directory/"critical_chain.json")
            phases={(p["operation"],p["phase"]):p for p in result["phases"]}
            traffic["collectives"]={op:dict(result["operations"][op],
                transfers=[p for p in result["phases"] if p["operation"]==op and p["kind"]=="transfer"],
                critical_transfers=[dict(action=phases[op,s["phase"]]["action"],start=s["start"],finish=s["finish"])
                                    for s in chain["segments"] if s["operation"]==op and s["category"]=="network"])
                for op in arm["collectives"]}
            write_json(args.output/(case["name"]+"-"+arm["placement"]+".json"),traffic)
            rows.append(dict(case=case["name"],placement=arm["placement"],
                application_cycles=arm["booksim_cycles"],coarse_cycles=arm["coarse_cycles"],
                attention_cycles=arm["collectives"]["attention_sum"]["duration"],
                ffn_cycles=arm["collectives"]["ffn_sum"]["duration"],
                endpoints=arm["worker_endpoints"],peak_messages=arm["peak_outstanding_messages"],
                first_injection_wait=arm["first_injection_wait_cycles"],
                first_flit_router_excess=traffic["first_flit_router_excess_cycles"],
                mean_message_cycles=mean(m["finish"]-m["ready"] for m in result["network_messages"]),
                mean_inter_router_links=mean(len(f["router_path"])-1 for m in result["network_messages"] for f in m["flits"]),
                memory_queue_wait=arm["memory_queue_wait_cycles"],
                critical_compute=arm["critical_chain_cycles"].get("compute",0),
                critical_memory=arm["critical_chain_cycles"].get("memory",0),
                critical_network=arm["critical_chain_cycles"].get("network",0)))
    with (args.output/"comparison.csv").open("w") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    write_json(args.output/"SUMMARY.json",dict(rows=rows,run_source_commit=complete["source_commit"]))
    write_json(args.output/"ANALYZED.json",dict(run=str(args.run),
        source_commit=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(),
        input_complete_sha256=digest(args.run/"COMPLETE.json"),
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
    print((args.output/"comparison.csv").read_text())


if __name__=="__main__":main()
