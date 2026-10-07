"""Profile complete accepted work under one fixed memory/endpoint contract."""
import argparse
import os
from pathlib import Path
import platform
import pstats
import statistics
import subprocess
import sys
import time

from wafer_sim.experiments.memory_boundary import worker
from wafer_sim.io import digest, object_digest, read_json, write_json


def main():
    if platform.node().split('.')[0] != 'eex005':
        raise SystemExit('Run on eex005')
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--tests',type=Path)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--profile',action='store_true')
    parser.add_argument('--cpus',default='254,255')
    args=parser.parse_args()
    cpus=[int(c) for c in args.cpus.split(',')]
    if args.worker:
        worker(args.worker,'bounded',args.output,cpus,profile_execution=args.profile)
        return
    repo=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo):
        raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    tests=read_json(args.tests)
    if (not tests['passed'] or tests['source_commit']!=commit or
            digest(tests['tests_log'])!=tests['tests_log_sha256']):
        raise ValueError('Same-source passed semantic tests required')
    accepted=Path('/home/wangziheng/wafer_simulator/runs/memory-service-isolation-001')
    complete=read_json(accepted/'COMPLETE.json')
    if not complete['all_registered_work_complete']:
        raise ValueError('Accepted run incomplete')
    for name,expected in complete['artifacts_sha256'].items():
        if digest(accepted/name)!=expected:
            raise ValueError('Accepted artifact changed: '+name)
    if not args.output.is_absolute():raise ValueError('Fresh absolute output required')
    args.output.mkdir(exist_ok=False)
    write_json(args.output/'STARTED.json',dict(source_commit=commit,host=platform.node(),
        python=sys.version,executable_sha256=digest(Path(sys.executable).resolve()),
        tests_sha256=digest(args.tests),accepted_manifest_sha256=digest(accepted/'COMPLETE.json'),
        source_hashes={str(f.relative_to(repo)):digest(f) for f in [
            *sorted((repo/'src').rglob('*.py')),Path(__file__).resolve(),
            repo/'docs/MEMORY_EXECUTION_COST.md']},
        affinity=cpus,load=os.getloadavg(),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        contract='accepted burst_256; bounded; all descriptors unchanged',
        plan=dict(shapes=['s16','s64'],unprofiled_repeats=3,profiled_repeats=1)))
    launches=[];rows=[]
    try:
        for shape in ('s16','s64'):
            original=accepted/(shape+'__burst_256')
            descriptor=original/'INPUT_CONFIG.json'
            reference=read_json(original/'bounded-0/MEASURED.json')
            for repeat in range(4):
                profiled=repeat==3
                dest=args.output/f'{shape}-{repeat}'
                command=[sys.executable,str(Path(__file__).resolve()),str(dest),
                         '--worker',str(descriptor),'--cpus',args.cpus]
                if profiled:command.append('--profile')
                start=time.perf_counter();load=os.getloadavg()
                with (args.output/f'{shape}-{repeat}.log').open('w') as log:
                    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
                measured=read_json(dest/'MEASURED.json')
                actual=object_digest(read_json(dest/'execution.json'))
                if (actual!=reference['execution_identity'] or actual!=measured['execution_identity'] or
                        measured['input_identity']!=reference['input_identity'] or
                        measured['network_identity']['binary_sha256']!=reference['network_identity']['binary_sha256']):
                    raise ValueError('Fixed-contract execution or binary changed')
                launches.append(dict(shape=shape,repeat=repeat,profiled=profiled,worker=str(dest),
                    wall_seconds=time.perf_counter()-start,load_before=load,load_after=os.getloadavg(),
                    descriptor_sha256=digest(descriptor),exact_accepted_events=True))
                if profiled:
                    stats=pstats.Stats(str(dest/'execution.prof'))
                    functions=[dict(file=k[0],line=k[1],function=k[2],primitive_calls=v[0],
                        calls=v[1],self_seconds=v[2],cumulative_seconds=v[3])
                        for k,v in stats.stats.items()]
                    write_json(dest/'PROFILE.json',dict(scope='execute only; profiled wall including waits, not native CPU',
                        functions=sorted(functions,key=lambda r:r['self_seconds'],reverse=True)))
                print(shape,repeat,'profile' if profiled else 'unprofiled',measured['application_cycles'],flush=True)
            samples=[read_json(args.output/f'{shape}-{r}/MEASURED.json') for r in range(3)]
            rows.append(dict(shape=shape,application_cycles=samples[0]['application_cycles'],
                execution_wall_median=statistics.median(next(p['wall_seconds'] for p in s['phases'] if p['phase']=='execution') for s in samples),
                execution_python_cpu_median=statistics.median(next(p['python_cpu_seconds'] for p in s['phases'] if p['phase']=='execution') for s in samples),
                native_lifetime_cpu_median=statistics.median(s['native_total_cpu_seconds'] for s in samples),
                python_peak_rss_kib=max(s['python_lifetime_peak_rss_kib'] for s in samples)))
        write_json(args.output/'LAUNCHES.json',launches)
        write_json(args.output/'SUMMARY.json',dict(rows=rows,all_exact_accepted_events=True,
            profiled_samples_excluded_from_cost=True))
        write_json(args.output/'COMPLETE.json',dict(source_commit=commit,all_registered_work_complete=True,
            artifacts_sha256={str(f.relative_to(args.output)):digest(f)
                for f in sorted(args.output.rglob('*')) if f.is_file()}))
    except BaseException as error:
        write_json(args.output/'FAILED.json',dict(type=type(error).__name__,message=str(error)))
        raise


if __name__=='__main__':main()
