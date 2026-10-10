"""G2.1 accuracy then controlled same-core cost, no Native/application run."""
import argparse
from pathlib import Path
import platform
import random
import os
import signal
import subprocess
import sys
import threading
import time
from wafer_sim.adapters.causal_macro import run,derived_source
from wafer_sim.analysis.causal_macro_single import reference_boundaries,check_run,process_fields
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json,digest,object_digest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path);parser.add_argument('--tests',type=Path,required=True)
    args=parser.parse_args();root=require_active_server();repo=Path(__file__).resolve().parents[3]
    if not args.output.is_absolute() or not args.output.is_relative_to(root/'runs') or args.output.exists():raise ValueError('Fresh server run required')
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean main required')
    source=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    tests=read_json(args.tests)
    if not tests['passed'] or tests['source_commit']!=source or tests['tests_log_sha256']!=digest(args.tests.parent/'tests.log') or tests['executable_sha256']!=digest(Path(sys.executable).resolve()):
        raise ValueError('Successful authenticated same-source tests required')
    reg=read_json(repo/'configs/causal_macro_single.json');g1=read_json(repo/'configs/causal_closure.json')
    if digest(repo/'configs/causal_closure.json')!=reg['g1_registration_sha256'] or digest(repo/'src/wafer_sim/adapters/causal_merge.py')!=reg['g1_predictor_sha256']:
        raise ValueError('Changed G1 identity')
    args.output.mkdir();(args.output/'DERIVED_CORE.py').write_text(derived_source())
    files=['configs/causal_macro_single.json','configs/causal_closure.json','src/wafer_sim/adapters/causal_merge.py',
        'src/wafer_sim/architecture/causal_merge.py','src/wafer_sim/adapters/causal_macro.py',
        'src/wafer_sim/analysis/causal_macro_single.py','src/wafer_sim/analysis/causal_compressibility.py',
        'src/wafer_sim/experiments/causal_macro_single.py','src/wafer_sim/experiments/causal_macro_worker.py']
    environment=dict(host=platform.node(),python=sys.version,python_executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),affinity=reg['affinity'])
    write_json(args.output/'ENVIRONMENT.json',environment)
    write_json(args.output/'STARTED.json',dict(source_commit=source,source_hashes={p:digest(repo/p) for p in files},
        environment_sha256=digest(args.output/'ENVIRONMENT.json'),tests_sha256=digest(args.tests),
        derived_source_sha256=digest(args.output/'DERIVED_CORE.py'),native_executions=0,application_executions=0))
    rows=[];costs=[]
    try:
        accuracy=[(n,0) for n in reg['accuracy_flits']]+[(1025,reg['delayed_ready'])]
        for n,ready in accuracy:
            directory=args.output/f'accuracy-{n}-{ready}';directory.mkdir()
            inp=dict(contract=g1['contract'],messages=[dict(source=0,destination=3,flits=n,ready=ready)],cycle_limit=reg['cycle_limit'])
            write_json(directory/'INPUT.json',inp)
            candidate=run(inp['contract'],inp['messages'],inp['cycle_limit'],checkpoints=True)
            # Persist candidate before reference execution or boundary observation.
            write_json(directory/'MACRO_RECORD.json',candidate.record())
            cycles=[r['state']['cycle'] for r in candidate.metrics()['checkpoints']]
            reference,boundaries=reference_boundaries(inp['contract'],inp['messages'],inp['cycle_limit'],cycles)
            write_json(directory/'G1_REFERENCE.json',reference);write_json(directory/'G1_BOUNDARIES.json',boundaries)
            checked=check_run(candidate,reference,boundaries)
            plain=run(inp['contract'],inp['messages'],inp['cycle_limit'],compress=False)
            if plain.expand()!=reference:raise ValueError('Mechanical G1 derivation changed behavior')
            checked.update(flits=n,ready=ready,macro_disabled_exact=True,compact_sha256=object_digest(candidate.compact()))
            write_json(directory/'CHECKED.json',checked);rows.append(checked)
            print('accuracy',n,ready,'updates',checked['physical_cycle_updates'],'skipped',checked['skipped_cycles'],flush=True)
        jobs=[(n,r,mode) for n in reg['benchmark_flits'] for r in range(reg['repetitions']) for mode in ('g1','macro_off','macro_on')]
        random.Random(reg['order_seed']).shuffle(jobs)
        for n,repetition,mode in jobs:
            directory=args.output/f'cost-{n}-{repetition}-{mode}';directory.mkdir()
            inp=dict(contract=g1['contract'],messages=[dict(source=0,destination=3,flits=n,ready=0)],cycle_limit=reg['cycle_limit'])
            write_json(directory/'INPUT.json',inp)
            command=['taskset','-c',','.join(map(str,reg['affinity'])),'/usr/bin/time','-v','-o',str(directory/'PROCESS.time'),
                sys.executable,'-m','wafer_sim.experiments.causal_macro_worker',str(directory/'INPUT.json'),str(directory/'WORKER.json'),'--mode',mode]
            before=time.perf_counter();timed_out=[False]
            with (directory/'worker.log').open('w') as log:
                process=subprocess.Popen(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                def expire():
                    if process.poll() is None:
                        timed_out[0]=True;os.killpg(process.pid,signal.SIGKILL)
                watchdog=threading.Timer(reg['process_deadline_seconds'],expire);watchdog.start()
                try:exit_status=process.wait()  # Blocking waitpid; no timeout polling floor.
                finally:watchdog.cancel();watchdog.join()
            after=time.perf_counter();wall=after-before
            if timed_out[0] or exit_status!=0:raise RuntimeError('Timed-out/failed cost worker')
            measured=read_json(directory/'WORKER.json');gnu_time=process_fields((directory/'PROCESS.time').read_text())
            write_json(directory/'PROCESS.json',dict(started_counter=before,finished_counter=after,exit_status=exit_status,
                timed_out=timed_out[0],command=command,gnu_time=gnu_time,
                input_sha256=digest(directory/'INPUT.json'),worker_sha256=digest(directory/'WORKER.json')))
            if not measured['complete']:raise ValueError('Incomplete cost worker')
            measured.update(flits=n,repetition=repetition,worker_wall_seconds=wall,process_sha256=digest(directory/'PROCESS.time'),
                process_record_sha256=digest(directory/'PROCESS.json'),process=gnu_time)
            write_json(directory/'CHECKED.json',measured);costs.append(measured)
            print('cost',n,repetition,mode,round(wall,4),flush=True)
        for n in reg['benchmark_flits']:
            selected=[r for r in costs if r['flits']==n]
            if len({object_digest(r['compact']) for r in selected})!=1:raise ValueError('Cost modes changed logical output')
        write_json(args.output/'RESULTS.json',dict(accuracy_passed=True,accuracy=rows,cost=costs,native_executions=0,
            application_executions=0,scope='Single source-0 primary G1 contract, G2.1 only'))
        artifacts={str(p.relative_to(args.output)):digest(p) for p in args.output.rglob('*') if p.is_file()}
        write_json(args.output/'COMPLETE.json',dict(complete=True,accuracy_passed=True,source_commit=source,artifacts_sha256=artifacts,
            native_executions=0,application_executions=0))
    except BaseException as error:
        write_json(args.output/'FAILED.json',dict(complete=False,source_commit=source,error=repr(error),native_executions=0,application_executions=0))
        raise


if __name__=='__main__':main()
