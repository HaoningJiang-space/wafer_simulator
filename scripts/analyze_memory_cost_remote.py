"""Re-read complete cost probes; keep raw profiles/events on eex005."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.execution_cost import analyze
from wafer_sim.adapters.memory_boundary import fuse_movements
from wafer_sim.experiments.memory_boundary import prepare
from wafer_sim.io import digest, write_json


def main():
    if platform.node().split('.')[0]!='eex005':raise SystemExit('Run on eex005')
    parser=argparse.ArgumentParser()
    parser.add_argument('before',type=Path);parser.add_argument('after',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if not args.output.is_absolute():raise ValueError('Fresh absolute output required')
    args.output.mkdir(exist_ok=False)
    def prepare_case(descriptor):
        binding,timing,_,_=prepare(descriptor)
        binding,_=fuse_movements(binding)
        return binding,timing
    result=analyze(args.before,args.after,
        '/home/wangziheng/wafer_simulator/runs/memory-service-isolation-001',prepare_case)
    write_json(args.output/'SUMMARY.json',result)
    with (args.output/'cost.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['rows'][0]))
        writer.writeheader();writer.writerows(result['rows'])
    write_json(args.output/'ANALYZED.json',dict(passed=True,host=platform.node(),
        analysis_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        input_manifests_sha256={str(p):digest(p/'COMPLETE.json') for p in (args.before,args.after)},
        artifacts_sha256={str(p.relative_to(args.output)):digest(p) for p in args.output.iterdir() if p.is_file()}))
    for row in result['rows']:
        print(row['shape'],row['application_cycles'],row['execution_speedup'],
              row['before_profile_admission_calls'],row['after_profile_admission_calls'])
    print('checked artifacts',result['checked_artifacts'],'full records/protocols',len(result['checks']))


if __name__=='__main__':main()
