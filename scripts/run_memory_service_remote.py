"""Same-work memory-contract isolation; reuse the accepted endpoint worker."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from wafer_sim.experiments.memory_boundary import worker
from wafer_sim.io import read_json, write_json, digest, object_digest


def main():
    if platform.node().split('.')[0] != 'eex005':
        raise SystemExit('Run on eex005')
    p=argparse.ArgumentParser()
    p.add_argument('output',type=Path);p.add_argument('--tests',type=Path)
    p.add_argument('--worker',type=Path);p.add_argument('--mode');p.add_argument('--cpus')
    a=p.parse_args();repo=Path(__file__).resolve().parents[1]
    cpus=[int(v) for v in a.cpus.split(',')] if a.cpus else sorted(os.sched_getaffinity(0))[-2:]
    if a.worker:
        worker(a.worker,a.mode,a.output,cpus);return
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo):
        raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    tests=read_json(a.tests)
    if not tests['passed'] or tests['source_commit']!=commit or digest(tests['tests_log'])!=tests['tests_log_sha256']:
        raise ValueError('Same-source tests required')
    reg=read_json(repo/'configs/memory_service_isolation.json');prior=Path(reg['accepted_run'])
    old=read_json(prior/'COMPLETE.json');old_start=read_json(prior/'STARTED.json')
    if not old['all_registered_work_complete']:raise ValueError('Accepted run incomplete')
    for name,h in old['artifacts_sha256'].items():
        if digest(prior/name)!=h:raise ValueError('Accepted artifact changed: '+name)
    runtime=Path('/home/wangziheng/wafer_simulator')
    binaries={name:digest(runtime/path) for name,path in {
        'boundary':'build/booksim-boundary/endpoint_booksim',
        'accepted_online':'build/booksim-online/online_booksim',
        'standalone':'build/booksim/rapidchiplet/booksim2/src/booksim'}.items()}
    if binaries!=old_start['binaries']:raise ValueError('Native binary changed')
    if not a.output.is_absolute():raise ValueError('Fresh absolute output')
    a.output.mkdir(exist_ok=False)
    controls={**old_start['registration'],'isolation':reg}
    write_json(a.output/'STARTED.json',dict(source_commit=commit,host=platform.node(),python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),registration=controls,
        binaries=binaries,accepted_manifest_sha256=digest(prior/'COMPLETE.json'),
        tests_sha256=digest(a.tests),affinity=cpus,load=os.getloadavg(),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        source_hashes={str(f.relative_to(repo)):digest(f) for f in [
            *sorted((repo/'src').rglob('*.py')),*sorted((repo/'src/wafer_sim/adapters/native').glob('*')),
            repo/'configs/memory_service_isolation.json',repo/'docs/MEMORY_SERVICE_ISOLATION.md']},
        build_source=old_start['build_source'],build_manifest_sha256=old_start['build_manifest_sha256']))
    launches=[];compatibility={}
    try:
        # Accepted contract first: passing it is the gate to the new policy.
        for contract in reg['contracts']:
            for shape in reg['cases']:
                name=shape+'__'+contract['name'];base=a.output/name;base.mkdir()
                d=read_json(prior/shape/'INPUT_CONFIG.json')
                if contract['memory_quantum_bytes'] is not None:
                    d['memory_quantum_bytes']=contract['memory_quantum_bytes']
                write_json(base/'INPUT_CONFIG.json',d)
                for repeat in range(reg['repetitions']):
                    modes=reg['modes'][repeat:]+reg['modes'][:repeat]
                    for mode in modes:
                        dest=base/f'{mode}-{repeat}';start=time.perf_counter();load=os.getloadavg()
                        command=[sys.executable,str(Path(__file__).resolve()),str(dest),
                                 '--worker',str(base/'INPUT_CONFIG.json'),'--mode',mode,
                                 '--cpus',','.join(map(str,cpus))]
                        with (base/f'{mode}-{repeat}.log').open('w') as log:
                            proc=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                        if proc.returncode:raise RuntimeError('Worker failed: '+str(dest))
                        record=read_json(dest/'MEASURED.json')
                        launches.append(dict(case=name,shape=shape,contract=contract['name'],mode=mode,
                            repeat=repeat,worker=str(dest),worker_wall_seconds=time.perf_counter()-start,
                            load_before=load,load_after=os.getloadavg()))
                        if contract['memory_quantum_bytes'] is None:
                            expected=object_digest(read_json(prior/shape/(mode+'-0')/'execution.json'))
                            if record['execution_identity']!=expected:raise ValueError('Accepted events changed')
                            compatibility[shape+'/'+mode]=dict(exact_events=True,sha256=expected)
                        print(name,mode,repeat,record['application_cycles'],flush=True)
                samples=[read_json(Path(r['worker'])/'MEASURED.json') for r in launches if r['case']==name]
                if len({r['input_identity'] for r in samples})!=1:raise ValueError('Changed work across boundary arms')
                for mode in reg['modes']:
                    if len({r['execution_identity'] for r in samples if r['mode']==mode})!=1:
                        raise ValueError('Repeat event divergence')
            if contract['memory_quantum_bytes'] is None:
                write_json(a.output/'COMPATIBILITY.json',compatibility)
        write_json(a.output/'LAUNCHES.json',launches)
        write_json(a.output/'COMPLETE.json',dict(source_commit=commit,all_registered_work_complete=True,
            artifacts_sha256={str(f.relative_to(a.output)):digest(f) for f in sorted(a.output.rglob('*')) if f.is_file()}))
    except BaseException as error:
        write_json(a.output/'FAILED.json',dict(type=type(error).__name__,message=str(error)));raise


if __name__=='__main__':main()
