"""Run the declared complete analytical execution unit and compact rate controls."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.experiments.timed_example import run_case
from wafer_sim.io import digest,object_digest,read_json,write_json


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Execution and validation stay on eex005")
    parser=argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("tests",type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    commit=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip()
    if subprocess.check_output(["git","-C",str(repo),"status","--porcelain"]):
        raise ValueError("Clean committed code required")
    tests=read_json(args.tests)
    if (not tests["passed"] or tests["source_commit"]!=commit or
            digest(tests["tests_log"])!=tests["tests_log_sha256"] or
            not Path(tests["tests_log"]).read_text().rstrip().endswith("OK")):
        raise ValueError("Passing semantic validation for this revision required")
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    config_path=repo/"configs/timed_execution_example.json"
    config=read_json(config_path)
    args.output.mkdir(parents=True,exist_ok=False)
    write_json(args.output/"CONFIG.json",config)
    write_json(args.output/"STARTED.json",dict(source_commit=commit,host=platform.node(),
        python=sys.version,executable=sys.executable,executable_sha256=digest(Path(sys.executable).resolve()),
        config_sha256=digest(config_path),tests_receipt_sha256=digest(args.tests),
        packages=subprocess.check_output([sys.executable,"-m","pip","freeze"],text=True).splitlines(),
        scope="Declared analytical execution unit, not measured wafer or Llama timing"))
    summary=[]; identity=None
    for case in config["controlled_cases"]:
        record=run_case(config,case)
        logical_identity=object_digest(dict(workload=record["workload"],placement=record["placement"],
                                           collective=record["collective"]))
        if identity is not None and identity!=logical_identity: raise ValueError("Logical work or placement changed")
        identity=logical_identity
        write_json(args.output/f"{case}.json",record)
        row=dict(case=case,application_cycles=record["result"]["application_cycles"],
                 operation_finishes={op:values["finish"] for op,values in record["result"]["operations"].items()},
                 peak_bytes=record["result"]["peak_bytes"],audit=record["audit"])
        summary.append(row); print(row,flush=True)
    write_json(args.output/"SUMMARY.json",dict(source_commit=commit,cases=summary,
        logical_work_and_placement_sha256=identity,source_time_replayed=False,
        architecture_calibrated=False,network_model="store-and-forward resource calendar",
        old_chakra_recovery_required=False,new_booksim_or_llama_runs=0))
    write_json(args.output/"COMPLETE.json",dict(source_commit=commit,all_cases_audited=True,
        analytical_execution_cases=len(summary),artifacts_sha256={p.name:digest(p) for p in
            sorted(args.output.iterdir()) if p.is_file()}))


if __name__=="__main__": main()
