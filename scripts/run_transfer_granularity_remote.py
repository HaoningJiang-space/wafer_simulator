"""Run the two registered complete inputs and component service characterization."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from wafer_sim.io import read_json,write_json,digest


def main():
    if platform.node().split('.')[0]!='eex005': raise SystemExit('Run on eex005')
    parser=argparse.ArgumentParser()
    parser.add_argument('output',type=Path)
    parser.add_argument('--tests',type=Path)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--backend',choices=('booksim','coarse','packet_pipeline'))
    parser.add_argument('--registration',default='configs/transfer_granularity.json')
    parser.add_argument('--repetitions',type=int,default=1)
    parser.add_argument('--cpus')
    args=parser.parse_args()
    from wafer_sim.experiments.transfer_granularity import worker,characterize,Meter
    if args.worker:
        worker(args.worker,args.backend,args.output,args.repetitions,[int(x) for x in args.cpus.split(',')]);return
    from wafer_sim.adapters.wow import export_placement
    repo=Path(__file__).resolve().parents[1];runtime=Path('/home/wangziheng/wafer_simulator')
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']): raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    tests=read_json(args.tests)
    if (not tests['passed'] or tests['source_commit']!=commit or
        digest(tests['tests_log'])!=tests['tests_log_sha256']): raise ValueError('Same-revision tests required')
    if not args.output.is_absolute(): raise ValueError('Fresh absolute output required')
    args.output.mkdir(exist_ok=False)
    registration=read_json(repo/args.registration)
    backends=registration.get('backends',['booksim','coarse'])
    if set(backends) not in ({'booksim','coarse'},{'booksim','coarse','packet_pipeline'}) or len(backends)!=len(set(backends)):
        raise ValueError('Invalid registered backend comparison')
    experiment=read_json(repo/'configs/transformer_wow_pair.json')
    wc=read_json(repo/experiment['workload_config'])
    cpus=sorted(os.sched_getaffinity(0))[-2:] if not args.cpus else [int(x) for x in args.cpus.split(',')]
    if len(set(cpus))!=2 or not set(cpus)<=os.sched_getaffinity(0): raise ValueError('Two allowed CPUs required')
    experiment['mapping']=registration['mapping']
    experiment['execution_policy']['collective_algorithm']=registration['algorithm']
    write_json(args.output/'STARTED.json',dict(source_commit=commit,registration=registration,
        test_receipt_sha256=digest(args.tests),host=platform.node(),python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),affinity=cpus,load=os.getloadavg(),
        cpuinfo=Path('/proc/cpuinfo').read_text(),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        native_build_commit=(runtime/'build/booksim-online/source_commit').read_text().strip(),
        binary_sha256={name:digest(runtime/path) for name,path in {
            'online':'build/booksim-online/online_booksim','standalone':'build/booksim/rapidchiplet/booksim2/src/booksim'}.items()},
        source_manifest={str(p.relative_to(repo)):digest(p) for p in sorted((repo/'src').rglob('*.py'))},
        protocol_sha256=digest(repo/registration.get('protocol','docs/TRANSFER_GRANULARITY_PROTOCOL.md'))))
    meter=Meter()
    with meter.phase('common_geometry_export'):
        export_placement(runtime/'upstream/nw-design-for-wsi',args.output/'geometry',registration['placement'],
                         experiment['wafer_diameter_mm'],experiment['wafer_utilization'])
    write_json(args.output/'COMMON_COST.json',meter.rows)
    launches=[];excluded=[]
    try:
        for ci,case in enumerate(registration['cases']):
            directory=args.output/case['name'];directory.mkdir()
            descriptor=dict(experiment=experiment,workload=dict(wc,
                block=dict(registration['block'],sequence=case['sequence']),
                memory_bytes_per_cycle=registration['memory_bytes_per_cycle']),
                network_json=str(args.output/'geometry/network.json'),
                geometry_directory=str(args.output/'geometry'),runtime=str(runtime),
                service_tolerance_percent=registration['message_error_tolerance_percent'],backends=backends)
            write_json(directory/'INPUT_CONFIG.json',descriptor)
            for mode in ('cold','reuse_graph'):
                for repeat in range(registration['cold_repetitions'] if mode=='cold' else 1):
                    offset=(ci+repeat+(mode=='reuse_graph'))%len(backends)
                    order=backends[offset:]+backends[:offset]
                    for backend in order:
                        output=directory/f'{mode}-{repeat}-{backend}'
                        command=[sys.executable,str(Path(__file__).resolve()),str(output),
                            '--worker',str(directory/'INPUT_CONFIG.json'),'--backend',backend,
                            '--repetitions',str(registration['graph_reuse_repetitions'] if mode=='reuse_graph' else 1),
                            '--cpus',','.join(map(str,cpus))]
                        load=os.getloadavg();start=time.perf_counter()
                        with (directory/f'{output.name}.log').open('w') as log:
                            completed=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                        elapsed=time.perf_counter()-start
                        if completed.returncode: raise RuntimeError(f'Worker failed: {output}')
                        result=read_json(output/'MEASURED.json')
                        launches.append(dict(case=case['name'],mode=mode,backend=backend,repeat=repeat,
                            worker=str(output),worker_wall_seconds=elapsed,load_before=load,load_after=os.getloadavg()))
                        print(case['name'],mode,backend,[r['application_cycles'] for r in result['trials']],flush=True)
            results=[read_json(Path(r['worker'])/'MEASURED.json') for r in launches if r['case']==case['name']]
            if len({r['input_identity'] for r in results})!=1: raise ValueError('Different backend input identity')
            for backend in backends:
                if len({t['execution_identity'] for r in results if r['backend']==backend for t in r['trials']})!=1:
                    raise ValueError('Cold/reuse simulated events differ')
            if all(t['complete'] for r in results for t in r['trials']):
                characterize(directory/'INPUT_CONFIG.json',directory/'isolated')
            else: excluded.append(case['name'])
        write_json(args.output/'LAUNCHES.json',launches)
        if excluded: write_json(args.output/'EXCLUDED.json',dict(cases=excluded,reason='incomplete capacity admission; no input changes'))
        write_json(args.output/'COMPLETE.json',dict(source_commit=commit,measurement_complete=True,
            all_registered_work_complete=not excluded,excluded_cases=excluded,
            artifacts_sha256={str(p.relative_to(args.output)):digest(p) for p in sorted(args.output.rglob('*')) if p.is_file()}))
    except BaseException as error:
        write_json(args.output/'FAILED.json',dict(type=type(error).__name__,message=str(error)));raise


if __name__=='__main__': main()
