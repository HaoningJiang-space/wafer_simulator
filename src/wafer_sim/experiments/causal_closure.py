"""Registered G1 component campaign only; predictor runs before Native."""
import argparse
from copy import deepcopy
import os
from pathlib import Path
import platform
import subprocess
import sys
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.architecture.causal_merge import validate, topology
from wafer_sim.analysis.causal_closure import read_observation, compare
from wafer_sim.execution.plan import Transfer
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json,digest,object_digest

REPO=Path(__file__).resolve().parents[3]
BASELINE='d37fc5551d90adb03f2595f9e23ef0199b39be3a572f315ef154bad172d93beb'
REG='configs/causal_closure.json'


def configuration(contract,directory):
    c=validate(contract);directory.mkdir()
    (directory/'network.anynet').write_text(topology(c));write_json(directory/'empty.json',[])
    settings={k:c[k] for k in ('num_vcs','packet_size','vc_alloc_delay','sw_alloc_delay','routing_delay','credit_delay',
        'wait_for_tail_credit','vc_busy_when_full','output_buffer_size','input_speedup','output_speedup','internal_speedup',
        'buffer_policy','vc_allocator','sw_allocator','alloc_iters','speculative','hold_switch_for_packet')}
    settings.update(vc_buf_size=c['capacity_flits'],buf_size=-1,st_prepare_delay=0,st_final_delay=c['crossbar_delay'],
        topology='anynet',network_file=str(directory/'network.anynet'),routing_function='modular_routing',
        modular_routing_function='simple_cycle_breaking_set',modular_selection_function='adaptive',
        mode='trace',trace_file=str(directory/'empty.json'),trace_report=str(directory/'trace_report.json'),
        trace_skip_idle=0,ignore_cycles=0,classes=1,subnets=1,traffic='uniform',seed=1,
        injection_rate=1.0,injection_rate_uses_flits=1,use_read_write=0,sample_period=1000000000,
        warmup_periods=0,sim_count=1,trace_time_out=60,deadlock_warn_timeout=200000,
        path_for_stats=str(directory/'link_stats.csv'))
    path=directory/'network.conf';path.write_text(''.join(f'{k} = {v};\n' for k,v in settings.items()));return path


def native_run(binary,contract,messages,directory,observed,limit):
    config=configuration(contract,directory)
    old=os.environ.get('WAFER_CAUSAL_OBSERVATION')
    if observed:os.environ['WAFER_CAUSAL_OBSERVATION']=str(directory/'OBSERVATION.jsonl')
    else:os.environ.pop('WAFER_CAUSAL_OBSERVATION',None)
    client=None
    try:
        client=OnlineBookSim(binary,config,directory,flit_bytes=contract['flit_bytes'])
        todo=sorted(enumerate(messages),key=lambda item:(item[1]['ready'],item[0]))
        # The registration keeps submissions in their message-ID order.
        if [i for i,_ in todo]!=list(range(len(messages))):raise ValueError('Unsupported submission identity order')
        while todo or client.pending:
            while todo and todo[0][1]['ready']==client.now:
                mid,m=todo.pop(0);client.submit(str(mid),Transfer(str(mid),'source','destination',m['source'],3,
                    m['flits']*contract['flit_bytes']),client.now)
            if not todo and not client.pending:break
            client.advance(todo[0][1]['ready'] if todo else limit)
            if client.now>=limit and client.pending:raise TimeoutError('Incomplete Native component')
        record=client.close();write_json(directory/'NETWORK_RESULT.json',record);return record
    finally:
        if client:client.abort()
        if old is None:os.environ.pop('WAFER_CAUSAL_OBSERVATION',None)
        else:os.environ['WAFER_CAUSAL_OBSERVATION']=old


def run(output,binary,tests):
    root=require_active_server();commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']):raise ValueError('Clean source required')
    if not output.is_absolute() or not output.is_relative_to(root/'runs') or output.exists():raise ValueError('Fresh server output required')
    receipt=read_json(tests)
    if not receipt['passed'] or receipt['source_commit']!=commit or receipt['modules']!=['test_causal_closure'] or digest(receipt['tests_log'])!=receipt['tests_log_sha256']:
        raise ValueError('Same-source tests required')
    if (binary.parent/'source_commit').read_text().strip()!=commit or (binary.parent/'FAILED.txt').exists():raise ValueError('Same-source clean build required')
    for line in (binary.parent/'binaries.sha256').read_text().splitlines():
        expected,path=line.split(None,1)
        if digest(path.lstrip('*'))!=expected:raise ValueError('Changed isolated build')
    baseline=root/'build/booksim-online/online_booksim'
    if digest(baseline)!=BASELINE:raise ValueError('Changed accepted S binary')
    reg=read_json(REPO/REG);os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-2:]);output.mkdir()
    files=[REPO/REG,Path(__file__).resolve(),REPO/'src/wafer_sim/adapters/causal_merge.py',REPO/'src/wafer_sim/architecture/causal_merge.py',
           REPO/'src/wafer_sim/analysis/causal_closure.py',REPO/'src/wafer_sim/adapters/native/wafer_causal_service.inc',
           REPO/'src/wafer_sim/adapters/native/wafer_causal_service.hpp',REPO/'patches/booksim-causal-closure-observation.patch',
           REPO/'patches/booksim-local-service-observation.patch',REPO/'patches/booksim-wafer.patch',REPO/'patches/online-booksim-local-service.patch',
           REPO/'src/wafer_sim/adapters/native/online_booksim.cpp',REPO/'src/wafer_sim/adapters/online_booksim.py']
    write_json(output/'STARTED.json',dict(source_commit=commit,registration_sha256=digest(REPO/REG),tests=receipt,
        host=platform.node(),python=sys.version,executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        affinity=sorted(os.sched_getaffinity(0)),baseline_binary_sha256=BASELINE,observed_binary_sha256=digest(binary),
        build_manifest_sha256=digest(binary.parent/'binaries.sha256'),compiler_sha256=digest(binary.parent/'compiler.txt'),
        source_hashes={str(p.relative_to(REPO)):digest(p) for p in files},application_executions=0,compression_implemented=False))
    rows=[]
    try:
        for case in reg['cases']:
            directory=output/case['name'];directory.mkdir();contract=deepcopy(reg['contract'])
            contract['capacity_flits']=case.get('capacity_flits',contract['capacity_flits'])
            inp=dict(contract=contract,messages=case['messages']);write_json(directory/'INPUT.json',inp)
            prediction=simulate(contract,case['messages'],reg['cycle_limit']);write_json(directory/'PREDICTION.json',prediction)
            # No reference process/evidence exists in this case before prediction.
            reference=native_run(baseline,contract,case['messages'],directory/'reference',False,reg['cycle_limit'])
            observed=native_run(binary,contract,case['messages'],directory/'observed',True,reg['cycle_limit'])
            if (object_digest(reference['messages'])!=object_digest(observed['messages']) or reference['final']!=observed['final'] or
                    digest(directory/'reference/online_protocol.jsonl')!=digest(directory/'observed/online_protocol.jsonl')):
                raise ValueError('Observer changed Native service/protocol')
            check=compare(contract,prediction,observed,read_observation(directory/'observed/OBSERVATION.jsonl'))
            check.update(name=case['name'],capacity_flits=contract['capacity_flits'],exact_observer_events=True,
                         input_sha256=digest(directory/'INPUT.json'),prediction_sha256=digest(directory/'PREDICTION.json'))
            write_json(directory/'CHECKED.json',check);rows.append(check)
            print(case['name'],check['passed'],check['predicted_finishes'],check['native_finishes'],check['mismatches'],flush=True)
        if digest(baseline)!=BASELINE:raise ValueError('Reference binary changed')
        write_json(output/'SUMMARY.json',dict(rows=rows,g1_accuracy_passed=all(r['passed'] for r in rows),
            native_executions=2*len(rows),application_executions=0,independent_prediction=True,compression_implemented=False))
        write_json(output/'COMPLETE.json',dict(complete=True,accuracy_passed=all(r['passed'] for r in rows),source_commit=commit,
            artifacts_sha256={str(p.relative_to(output)):digest(p) for p in output.rglob('*') if p.is_file()}))
    except BaseException as error:
        write_json(output/'FAILED.json',dict(type=type(error).__name__,message=str(error)));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('output','binary','tests'):parser.add_argument('--'+key,required=True,type=Path)
    args=parser.parse_args();run(args.output,args.binary,args.tests)
