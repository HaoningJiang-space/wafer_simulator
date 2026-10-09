"""Bounded S cost observations: two existing inputs, no model optimization."""
import argparse
import cProfile
from pathlib import Path
import os
import subprocess
import sys
import time

from wafer_sim.experiments.server import require_active_server
from wafer_sim.experiments import shared_spatial_service as study
from wafer_sim.analysis.native_service_profile import checked_worker
from wafer_sim.io import digest,read_json,write_json


def worker(directory, side, mode, binary, input_file):
    if mode == 'native_sections':
        os.environ['WAFER_COST_PROFILE_OUTPUT'] = str(directory/'NATIVE_PROFILE.json')
        original = study.OnlineBookSim
        def instrumented(_binary, *args, **kwargs):
            return original(binary, *args, **kwargs)
        study.OnlineBookSim = instrumented
        study.worker(directory,side,'remote_balanced','S',input_file)
    else:
        profiler=cProfile.Profile()
        profiler.runcall(study.worker,directory,side,'remote_balanced','S',input_file)
        profiler.dump_stats(str(directory/'worker.prof'))


def run(output,binary):
    root=require_active_server();repo=Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']): raise ValueError('Clean source required')
    accepted=root/'runs/d1-applications-001'; manifest=read_json(accepted/'COMPLETE.json')
    if not manifest['complete'] or (accepted/'FAILED.json').exists(): raise ValueError('Incomplete reference')
    published=read_json(repo/'docs/results/shared-spatial-service-001/VERIFIED.json')
    if digest(accepted/'COMPLETE.json') != published['run_manifest_sha256']:
        raise ValueError('Reference manifest differs from published acceptance')
    reference_start=read_json(accepted/'STARTED.json')
    expected=reference_start['binary_sha256']
    # Set the launcher before spawning workers, so import-time thread pools also
    # inherit the baseline's CPU set. Profiling is diagnostic, never a speedup.
    os.sched_setaffinity(0,reference_start['affinity'])
    baseline=root/'build/booksim-online/online_booksim'
    if digest(baseline)!=expected or digest(binary)==expected: raise ValueError('Invalid profiling binary identity')
    output.mkdir()
    write_json(output/'STARTED.json',dict(source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        reference_manifest_sha256=digest(accepted/'COMPLETE.json'),native_baseline_sha256=expected,
        instrumented_binary_sha256=digest(binary),instrumented_source_sha256=digest(binary.parent/'online_booksim.cpp'),
        patch_sha256=digest(repo/'patches/online-booksim-cost-profile.patch'),
        original_wrapper_sha256=digest(repo/'src/wafer_sim/adapters/native/online_booksim.cpp'),
        build_manifest_sha256=digest(binary.parent/'binaries.sha256'),
        compiler_sha256=digest(binary.parent/'compiler.txt'),
        parser_tools_manifest_sha256=digest(binary.parent/'parser-tools.sha256'),
        host=os.uname().nodename,python=sys.version,executable_sha256=digest(Path(sys.executable).resolve()),
        affinity=sorted(os.sched_getaffinity(0)),load=os.getloadavg(),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        source_hashes={str(p.relative_to(repo)):digest(p) for p in sorted((repo/'src').rglob('*')) if p.is_file() and p.suffix in ('.py','.cpp')},
        cases=[6,7],layout='remote_balanced',modes=['python_functions','native_sections'],
        scope='Four profiling executions. Baseline costs from unprofiled D1 study; no acceleration claim'))
    rows=[]
    try:
        for side in (6,7):
            reference=accepted/f'{side}-remote_balanced-S-rep-0'
            input_file=accepted/f'inputs/{side}-remote_balanced-S.json'
            if digest(input_file)!=manifest['artifacts_sha256'][str(input_file.relative_to(accepted))]:
                raise ValueError('Changed frozen S input')
            for mode in ('python_functions','native_sections'):
                dest=output/f'{side}-{mode}'
                command=[sys.executable,'-m','wafer_sim.experiments.profile_native_service',
                    '--output',str(dest),'--binary',str(binary),'--worker','--side',str(side),
                    '--mode',mode,'--input',str(input_file)]
                start=time.perf_counter()
                with (output/f'{side}-{mode}.log').open('w') as log:
                    subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
                worker_seconds=time.perf_counter()-start
                readback_started=time.perf_counter()
                row=checked_worker(dest,reference,manifest,mode)
                row.update(side=side,process_wall_seconds=worker_seconds,
                    readback_wall_seconds=time.perf_counter()-readback_started,directory=dest.name)
                write_json(dest/'CHECKED.json',row);rows.append(row)
                print(side,mode,'exact events/protocol',flush=True)
        if digest(baseline)!=expected: raise ValueError('Baseline binary changed')
        write_json(output/'SUMMARY.json',dict(rows=rows,all_exact_events=True,all_exact_protocol=True,
            baseline_costs=read_json(repo/'docs/results/shared-spatial-service-001/SUMMARY.json')['costs'],
            scope='Profiled timing is diagnostic; no baseline speedup is calculated'))
        write_json(output/'COMPLETE.json',dict(complete=True,executions=4,baseline_binary_unchanged=True,
            artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    except BaseException as error:
        write_json(output/'FAILED.json',dict(type=type(error).__name__,message=str(error)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--worker',action='store_true');parser.add_argument('--side',type=int)
    parser.add_argument('--mode',choices=('python_functions','native_sections'));parser.add_argument('--input',type=Path)
    args=parser.parse_args()
    if args.worker:worker(args.output,args.side,args.mode,args.binary,args.input)
    else:run(args.output,args.binary)
