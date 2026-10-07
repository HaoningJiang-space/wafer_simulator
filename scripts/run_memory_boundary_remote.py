"""Run registered mechanism gates, then complete same-work application pairs."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from wafer_sim.io import read_json,write_json,digest


def main():
    if platform.node().split('.')[0]!='eex005':raise SystemExit('Run on eex005')
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--tests',type=Path)
    p.add_argument('--worker',type=Path);p.add_argument('--mode');p.add_argument('--cpus')
    a=p.parse_args()
    from wafer_sim.experiments.memory_boundary import worker
    cpus=[int(v) for v in a.cpus.split(',')] if a.cpus else sorted(os.sched_getaffinity(0))[-2:]
    if a.worker:worker(a.worker,a.mode,a.output,cpus);return
    repo=Path(__file__).resolve().parents[1];runtime=Path('/home/wangziheng/wafer_simulator')
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo):raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    tests=read_json(a.tests)
    if not tests['passed'] or tests['source_commit']!=commit or digest(tests['tests_log'])!=tests['tests_log_sha256']:
        raise ValueError('Same-source verified tests required')
    if not a.output.is_absolute():raise ValueError('Fresh absolute output required')
    a.output.mkdir(exist_ok=False)
    reg=read_json(repo/'configs/memory_network_boundary.json')
    prior=runtime/'runs/transfer-granularity-001'
    write_json(a.output/'STARTED.json',dict(source_commit=commit,host=platform.node(),python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),registration=reg,affinity=cpus,
        tests_sha256=digest(a.tests),load=os.getloadavg(),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        binaries={n:digest(runtime/path) for n,path in {
            'boundary':'build/booksim-boundary/endpoint_booksim','accepted_online':'build/booksim-online/online_booksim',
            'standalone':'build/booksim/rapidchiplet/booksim2/src/booksim'}.items()},
        source_hashes={str(f.relative_to(repo)):digest(f) for f in [
            *sorted((repo/'src').rglob('*.py')),*sorted((repo/'src/wafer_sim/adapters/native').glob('*')),
            repo/'patches/booksim-endpoint-hooks.patch',repo/'patches/booksim-wafer.patch',repo/'docs/MEMORY_NETWORK_BOUNDARY_PROTOCOL.md']},
        build_manifest_sha256=digest(runtime/'build/booksim-boundary/binaries.sha256'),
        build_source=(runtime/'build/booksim-boundary/source_commit').read_text().strip()))
    launches=[]
    mechanisms=reg['mechanisms']
    def run_case(name,descriptor,repeats):
        base=a.output/name;base.mkdir();write_json(base/'INPUT_CONFIG.json',descriptor)
        for repeat in range(repeats):
            modes=reg['modes'][repeat:]+reg['modes'][:repeat]
            for mode in modes:
                dest=base/f'{mode}-{repeat}';start=time.perf_counter();load=os.getloadavg()
                command=[sys.executable,str(Path(__file__).resolve()),str(dest),'--worker',str(base/'INPUT_CONFIG.json'),
                         '--mode',mode,'--cpus',','.join(map(str,cpus))]
                with (base/f'{mode}-{repeat}.log').open('w') as log:
                    proc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                if proc.returncode:raise RuntimeError(f'Failed complete case: {dest}')
                record=read_json(dest/'MEASURED.json')
                launches.append(dict(case=name,mode=mode,repeat=repeat,worker=str(dest),worker_wall_seconds=time.perf_counter()-start,
                                     load_before=load,load_after=os.getloadavg()))
                print(name,mode,repeat,record['application_cycles'],record['boundary'],flush=True)
        records=[read_json(Path(l['worker'])/'MEASURED.json') for l in launches if l['case']==name]
        if len({r['input_identity'] for r in records})!=1:raise ValueError('Different machine/work across boundary arms')
        for mode in reg['modes']:
            if len({r['execution_identity'] for r in records if r['mode']==mode})!=1:raise ValueError('Repeat event identity changed')
    try:
        for fixture in mechanisms:
            descriptor=read_json(prior/'s16/INPUT_CONFIG.json')
            descriptor.update(boundary=reg,flows=fixture['flows'],memory_overrides=fixture.get('memory_overrides',{}))
            run_case(fixture['name'],descriptor,1)
        write_json(a.output/'MECHANISMS_COMPLETE.json',dict(passed=True,cases=[r['name'] for r in mechanisms]))
        for case in reg['cases']:
            descriptor=read_json(prior/case['name']/'INPUT_CONFIG.json');descriptor['boundary']=reg
            run_case(case['name'],descriptor,reg['repetitions'])
        write_json(a.output/'LAUNCHES.json',launches)
        write_json(a.output/'COMPLETE.json',dict(source_commit=commit,all_registered_work_complete=True,
            artifacts_sha256={str(f.relative_to(a.output)):digest(f) for f in sorted(a.output.rglob('*')) if f.is_file()}))
    except BaseException as error:
        write_json(a.output/'FAILED.json',dict(type=type(error).__name__,message=str(error)));raise

if __name__=='__main__':main()
