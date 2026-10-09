"""One frozen D1 hypothesis: independent flow components, then D0/D1/S work."""
import argparse
from dataclasses import asdict
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from wafer_sim.adapters.shared_spatial_service import SharedSpatialNetwork, contract
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.adapters.independent_spatial_service import machine_identity
from wafer_sim.adapters.wafer_machine import export_booksim
from wafer_sim.analysis.shared_spatial_service import audit as audit_d1, audit_network
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.spatial_scaling import prepare
from wafer_sim.experiments.independent_spatial_service import (
    REPO, FROZEN_D0, prepared_model as prepare_d0, input_identity, check as check_d0, finish)
from wafer_sim.experiments.isolated_response import semantic_config
from wafer_sim.experiments.transfer_granularity import Meter, usage, native_peak
from wafer_sim.experiments.wafer_machine import replay
from wafer_sim.experiments.d1_provenance import verify_frozen_v1, backend_identity
from wafer_sim.adapters.periphery_case import compile_case
from wafer_sim.adapters.memory_periphery import TransactionPolicy
from wafer_sim.execution.plan import Transfer
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json,write_json,digest,object_digest
from wafer_sim.experiments.server import require_active_server

REGISTRATION='configs/shared_spatial_service.json'
FROZEN_D1=FROZEN_D0+['src/wafer_sim/architecture','src/wafer_sim/workloads',
    'src/wafer_sim/adapters/timing.py','src/wafer_sim/adapters/online_booksim.py',
    'src/wafer_sim/adapters/independent_spatial_service.py','src/wafer_sim/experiments/independent_spatial_service.py',
    'configs/independent_spatial_service.json','docs/results/independent-spatial-service-001']


def registration():
    reg=read_json(REPO/REGISTRATION)
    return reg,read_json(REPO/reg['base_registration'])


def table():
    published=REPO/'docs/results/independent-spatial-service-001'
    verified=read_json(published/'DELIVERY_VERIFIED.json')
    if not verified['passed'] or digest(published/'calibration/TABLE.json')!=verified['published_files_sha256']['calibration/TABLE.json']:
        raise ValueError('Changed accepted D0 calibration')
    return read_json(published/'calibration/TABLE.json')


def gate(output, tests):
    root=require_active_server();reg,base=registration()
    if not output.is_absolute() or output.exists():raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']):raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip();receipt=read_json(tests)
    if (not receipt['passed'] or receipt['source_commit']!=commit or 'test_shared_spatial_service' not in receipt['modules'] or
            digest(receipt['tests_log'])!=receipt['tests_log_sha256']):raise ValueError('Same-source D1 tests required')
    source_changes=verify_frozen_v1(REPO,reg['frozen_commit'],FROZEN_D1)
    accepted=read_json(REPO/'docs/results/independent-spatial-service-001/SUMMARY.json');input_checks=[]
    for side in base['sides']:
        for layout in base['layouts']:
            for model in reg['models']:
                prepared=prepared_model(side,layout,model)
                old=next(r for r in accepted if (r['side'],r['layout'],r['model'])==(side,layout,model if model!='D1' else 'S'))
                if prepared[9]['physical_input_sha256']!=old['physical_input_sha256']:
                    raise ValueError('Changed frozen v1 physical/work/plan input')
                if model!='D1' and prepared[9]['projection_sha256']!=old['projection_sha256']:
                    raise ValueError('Changed accepted D0/S projection')
                input_checks.append(dict(side=side,layout=layout,model=model,
                    physical_input_sha256=prepared[9]['physical_input_sha256'],projection_sha256=prepared[9]['projection_sha256']))
    binary=root/'build/booksim-online/online_booksim';expected=table()['binary_sha256']
    if digest(binary)!=expected:raise ValueError('Changed accepted native reference binary')
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[-2:]);output.mkdir()
    files=[*sorted((REPO/'src').rglob('*.py')),REPO/REGISTRATION,REPO/reg['base_registration'],
        REPO/'configs/wafer_machine.json',REPO/'docs/SHARED_SPATIAL_SERVICE_PROTOCOL.md',REPO/'tests/test_shared_spatial_service.py']
    write_json(output/'STARTED.json',dict(source_commit=commit,registration=reg,base_registration=base,tests=receipt,
        host=platform.node(),python=sys.version,executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        affinity=sorted(os.sched_getaffinity(0)),load=os.getloadavg(),binary_sha256=expected,
        accepted_D0_table_sha256=digest(REPO/'docs/results/independent-spatial-service-001/calibration/TABLE.json'),
        frozen_paths=FROZEN_D1,compatible_source_changes=source_changes,frozen_input_checks=input_checks,
        machine_organization='v1-bank-endpoints',transaction_policy='whole',backend_selection='explicit D0/D1/S',
        source_hashes={str(p.relative_to(REPO)):digest(p) for p in files}))
    return binary


def prepared_model(side,layout,model):
    reg,_=registration()
    if model!='D1':return prepare_d0(side,layout,model,table() if model=='D0' else None)
    prepared=list(prepare(side,layout,'U1'));prepared[6]=contract(prepared[0],reg)
    prepared[8]=dict(prepared[8],contract=prepared[6])
    prepared[9]=dict(prepared[9],model='D1',projection_sha256=object_digest(prepared[8]))
    return prepared


def check(prepared,result):
    if prepared[6]['model']!='D1':return check_d0(prepared,result)
    c,_,_,base,b,timing,spec,*_=prepared
    checked=audit_d1(c,base,b,timing,spec,result)
    if any(o['capacity_wait_cycles'] for o in result['operations'].values()):raise ValueError('Unexpected staging bottleneck')
    return checked


def component_cases():
    reg,_=registration();cases=[]
    families=[('hb0','dram-0-0','sram-0'),('dram3','dram-0-0','sram-18'),
        ('c2c3','sram-0','sram-18'),('io-in','host-memory','sram-18'),('io-out','sram-18','host-memory')]
    def message(source,destination,size,ready=0):return dict(source_memory=source,destination_memory=destination,bytes=size,ready=ready)
    for family,source,destination in families:
        for size in reg['single_sizes_bytes']:
            cases.append(dict(name=f'single-{family}-{size}',kind='single',messages=[message(source,destination,size)]))
    patterns=[('two-shared',[('dram-0-0','sram-18'),('dram-6-0','sram-24')],reg['stagger_cycles']),
        ('three-shared',[('dram-0-0','sram-18'),('dram-6-0','sram-24'),('dram-12-0','sram-30')],reg['stagger_cycles']),
        ('two-disjoint',[('dram-0-0','sram-18'),('dram-1-0','sram-19')],[0,509]),
        ('two-reverse',[('dram-0-0','sram-18'),('dram-18-0','sram-0')],[0]),
        ('two-dram-c2c',[('dram-0-0','sram-18'),('sram-6','sram-24')],reg['stagger_cycles']),
        ('two-dram-io',[('dram-6-0','sram-24'),('host-memory','sram-18')],reg['stagger_cycles']),
        ('three-mixed',[('dram-0-0','sram-18'),('sram-6','sram-24'),('host-memory','sram-30')],[0,509]),
        ('two-source',[('sram-0','dram-6-0'),('sram-0','dram-12-0')],[0])]
    for name,ends,offsets in patterns:
        for offset in offsets:
            cases.append(dict(name=f'{name}-stagger-{offset}',kind=name,
                messages=[message(source,destination,65536,i*offset) for i,(source,destination) in enumerate(ends)]))
    return cases


def verify_d0_rule():
    """Check compact rule against accepted empty-network data, never full work."""
    data=table();reg,base=registration();checked=0;path_differences=0
    for side in base['sides']:
        c,_,_,_,binding,*_=prepare(side,'local','U1');n=SharedSpatialNetwork(binding,c.timing,contract(c,reg))
        part=data['machines'][machine_identity(c)]
        for k,e in part['entries'].items():
            source,destination,size=map(int,k.split(':'));path,_,latency=n.route(source,destination)
            duration=2*((size+63)//64)+latency
            if duration!=e['duration_cycles']:raise ValueError('D1 single-flow rule differs from D0 component '+k)
            if any(r['routers']!=list(path) for r in e['routes']):path_differences+=1
            checked+=1
    return dict(passed=True,component_conditions=checked,solo_service_mismatches=0,
        isolated_route_choices_differ=path_differences,table_sha256=object_digest(data),no_full_application_input=True)


def component_probe(directory,case,model,binary):
    root=require_active_server();reg,base=registration();directory.mkdir();meter=Meter()
    with meter.phase('preparation'):
        c,_,_,_,binding,*_=prepare(reg['component_side'],'local','U1');spec=contract(c,reg)
        messages=[]
        for i,m in enumerate(case['messages']):
            messages.append(dict(**m,token=f'component-{i}',source=c.endpoints[m['source_memory']],destination=c.endpoints[m['destination_memory']]))
        write_json(directory/'INPUT.json',dict(case=case,machine=asdict(c.physical),messages=messages))
    child=usage(resource.RUSAGE_CHILDREN)
    with meter.phase('network_configuration'):
        if model=='S':
            sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'));conf=export_booksim(c,directory,base['network_seed'])
        else:write_json(directory/'NETWORK.json',spec)
    with meter.phase('network_initialization'):
        client=OnlineBookSim(binary,conf,directory,flit_bytes=c.physical.flit_bytes) if model=='S' else SharedSpatialNetwork(binding,c.timing,spec)
    todo=list(messages)
    try:
        with meter.phase('execution'):
            while todo or client.pending:
                while todo and todo[0]['ready']==client.now:
                    m=todo.pop(0);client.submit(m['token'],Transfer('component',m['source_memory'],m['destination_memory'],
                        m['source'],m['destination'],m['bytes']),client.now)
                if not todo and not client.pending:break
                until=todo[0]['ready'] if todo else reg['component_cycle_limit']
                client.advance(until)
                if client.now>=reg['component_cycle_limit'] and client.pending:raise TimeoutError('Incomplete shared component')
        peaks=dict(python_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            native_peak_rss_kib=native_peak(client) if model=='S' else 0)
        with meter.phase('network_close_serialization'):record=client.close()
    finally:client.abort()
    with meter.phase('independent_audit'):
        checked=audit_messages(c.target.network,record['messages']) if model=='S' else audit_network(c.target.network,
            dict(network_messages=record['messages'],**{k:v for k,v in record.items() if k not in ('complete','messages')}))
        write_json(directory/'AUDIT.json',checked);write_json(directory/'NETWORK_RESULT.json',record)
    row=dict(name=case['name'],kind=case['kind'],model=model,phases=meter.rows,**peaks,
        native_cpu_seconds=usage(resource.RUSAGE_CHILDREN)-child,message_sha256=object_digest(record['messages']),
        durations=[m['finish']-m['ready'] for m in sorted(record['messages'],key=lambda m:m['id'])],
        native_flits=sum(len(m['flits']) for m in record['messages']) if model=='S' else 0,
        flow_epochs=len(record['flow_epochs']) if model=='D1' else 0)
    write_json(directory/'MEASURED.json',row)
    return row


def components(output,tests):
    binary=gate(output,tests);reg,base=registration();started=time.perf_counter()
    try:
        write_json(output/'D0_RULE_VERIFIED.json',verify_d0_rule());cases=component_cases();write_json(output/'CASES.json',cases)
        rows=[]
        for case in cases:
            for rep in range(reg['component_repetitions']):
                for model in ('D1','S') if rep==0 else ('S','D1'):
                    name=f"{case['name']}-{model}-rep-{rep}";row=component_probe(output/name,case,model,binary)
                    row.update(directory=name,repetition=rep);rows.append(row)
            subset=[r for r in rows if r['name']==case['name']]
            for model in ('D1','S'):
                if len({r['message_sha256'] for r in subset if r['model']==model})!=1:raise ValueError('Nondeterministic component')
            if case['kind']=='single':
                if next(r['durations'] for r in subset if r['model']=='D1')!=next(r['durations'] for r in subset if r['model']=='S'):
                    raise ValueError('D1 single-flow law fails native '+case['name'])
            print(case['name'],[(r['model'],r['durations']) for r in subset if r['repetition']==0],flush=True)
        write_json(output/'SUMMARY.json',rows)
        write_json(output/'COST.json',dict(wall_seconds=time.perf_counter()-started,cases=len(cases),executions=len(rows),
            python_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,scope='incremental components; existing D0 calibration reused'))
        finish(output,kind='D1_components',cases=len(cases),executions=len(rows))
    except BaseException as exc:write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc)));raise


def worker(output,side,layout,model,frozen_input):
    root=require_active_server();reg,base=registration();output.mkdir();meter=Meter()
    with meter.phase('graph_binding_preparation'):prepared=prepared_model(side,layout,model)
    c,_,_,_,binding,timing,spec,*_=prepared
    if object_digest(input_identity(prepared))!=object_digest(read_json(frozen_input)):raise ValueError('Changed frozen input')
    child=usage(resource.RUSAGE_CHILDREN)
    with meter.phase('network_configuration'):
        if model=='D1':write_json(output/'NETWORK.json',spec)
        else:
            sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'));conf=export_booksim(c,output,base['network_seed'])
    with meter.phase('network_initialization'):
        native=None
        if model=='D1':client=SharedSpatialNetwork(binding,timing,spec)
        else:
            native=OnlineBookSim(root/'build/booksim-online/online_booksim',conf,output,flit_bytes=c.physical.flit_bytes)
            if model=='D0':
                from wafer_sim.adapters.independent_spatial_service import IndependentSpatialNetwork
                client=IndependentSpatialNetwork(native,spec)
            else:client=native
    try:
        with meter.phase('execution'):result=execute(binding,timing,network=client,cycle_limit=base['cycle_limit'])
        peaks=dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,native_peak_rss_kib=native_peak(native) if native else 0)
        with meter.phase('network_close_serialization'):record=client.close()
        if model=='D1':write_json(output/'flow_network.json',record)
    finally:client.abort()
    child_cpu=usage(resource.RUSAGE_CHILDREN)-child
    with meter.phase('result_serialization'):write_json(output/'execution.json',result)
    with meter.phase('independent_audit'):
        checked=check(prepared,result);write_json(output/'AUDIT.json',checked)
        chain=critical_chain(binding,result);write_json(output/'critical_chain.json',chain)
        identity=backend_identity(model,spec,result)
    raw=result.get('native_network_messages',result['network_messages']) if model!='D1' else []
    write_json(output/'MEASURED.json',dict(side=side,layout=layout,model=model,application_cycles=result['application_cycles'],
        execution_sha256=object_digest(result),physical_input_sha256=prepared[9]['physical_input_sha256'],
        projection_sha256=prepared[9]['projection_sha256'],phases=meter.rows,**peaks,native_total_cpu_seconds=child_cpu,
        status=checked['status'],chain_cycles=chain['cycles'],logical_messages=len(result['network_messages']),
        native_flits=sum(len(m['flits']) for m in raw),flow_epochs=len(result.get('flow_epochs',[])),
        python_full_worker_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        result_bytes=(output/'execution.json').stat().st_size,affinity=sorted(os.sched_getaffinity(0)),load=os.getloadavg(),
        **identity,backend_contract_sha256=object_digest(spec)))


def run(output,tests,component_root):
    from wafer_sim.analysis.shared_spatial_study import verify_components
    campaign_started=time.perf_counter()
    binary=gate(output,tests);reg,base=registration();gate_seconds=time.perf_counter()-campaign_started;worker_seconds=0;replay_seconds=0
    try:
        validation_started=time.perf_counter()
        checked=verify_components(component_root);write_json(output/'COMPONENTS_VERIFIED.json',checked)
        component_revalidation_seconds=time.perf_counter()-validation_started
        for side in base['sides']:
            for layout in base['layouts']:
                common=prepared_model(side,layout,'S')
                # Snapshot only declared machine/work/placement and whole policy.
                # No S timing/routes enter the public or model prediction inputs.
                public=compile_case(common[0].physical,common[1],common[2],TransactionPolicy('whole'),interface_organization='bank')
                write_json(output/f'public_inputs/{side}-{layout}.json',public.to_record(condition='v1_whole',layout=layout))
                for model in reg['models']:
                    write_json(output/f'inputs/{side}-{layout}-{model}.json',input_identity(prepared_model(side,layout,model)))
        for rep in range(base['repetitions']):
            for side in base['sides']:
                for layout in base['layouts']:
                    for model in reg['models'][rep:]+reg['models'][:rep]:
                        name=f'{side}-{layout}-{model}';started=time.perf_counter()
                        with (output/'worker.log').open('a') as log:
                            subprocess.run([sys.executable,'-m','wafer_sim.experiments.shared_spatial_service','--worker',
                                '--output',str(output/f'{name}-rep-{rep}'),'--side',str(side),'--layout',layout,'--model',model,
                                '--input',str(output/f'inputs/{name}.json')],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
                        elapsed=time.perf_counter()-started;worker_seconds+=elapsed
                        write_json(output/f'{name}-rep-{rep}/PROCESS.json',dict(wall_seconds=elapsed,
                            scope='fresh whole worker including imports, preparation, execution, logging, serialization and audit'))
                        print(name,rep,flush=True)
        rows=[];accepted=read_json(REPO/'docs/results/independent-spatial-service-001/SUMMARY.json')
        sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'))
        for side in base['sides']:
            c,*_=prepare(side,'local','S')
            for layout in base['layouts']:
                physical=set()
                for model in reg['models']:
                    samples=[]
                    for rep in range(base['repetitions']):
                        d=output/f'{side}-{layout}-{model}-rep-{rep}';r=read_json(d/'MEASURED.json')
                        r.update(directory=d.name,process_wall_seconds=read_json(d/'PROCESS.json')['wall_seconds'])
                        samples.append(r);rows.append(r);physical.add(r['physical_input_sha256'])
                    if len({r['execution_sha256'] for r in samples})!=1:raise ValueError('Unstable application events')
                    if model!='D1':
                        old=next(r for r in accepted if (r['side'],r['layout'],r['model'])==(side,layout,model))
                        if samples[0]['execution_sha256']!=old['execution_sha256']:raise ValueError('Frozen D0/S events changed')
                        d=output/f'{side}-{layout}-{model}-rep-0';meter=Meter()
                        with meter.phase('native_command_replay'):replay(c,binary,d,d/'replay',base['network_seed'])
                        replay_seconds+=meter.rows[0]['wall_seconds']
                        write_json(d/'REPLAY_COST.json',meter.rows)
                if len(physical)!=1:raise ValueError('Different model physical inputs')
        write_json(output/'SUMMARY.json',rows)
        write_json(output/'COST.json',dict(total_wall_seconds=time.perf_counter()-campaign_started,
            gate_and_input_checks_seconds=gate_seconds,fresh_worker_wall_seconds=worker_seconds,native_replay_seconds=replay_seconds,
            reused_component_revalidation_seconds=component_revalidation_seconds,new_component_executions=0,
            scope='Fresh whole workers, registered replay, reused evidence readback; calibration and original components separate'))
        finish(output,kind='D1_applications',cells=27,executions=len(rows),native_replays=18,
            components_root=str(component_root),components_manifest_sha256=digest(component_root/'COMPLETE.json'))
    except BaseException as exc:write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc)));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--tests',type=Path)
    p.add_argument('--components',action='store_true');p.add_argument('--component-root',type=Path)
    p.add_argument('--worker',action='store_true');p.add_argument('--side',type=int);p.add_argument('--layout');p.add_argument('--model');p.add_argument('--input',type=Path)
    a=p.parse_args()
    if a.worker:worker(a.output,a.side,a.layout,a.model,a.input)
    elif a.components:components(a.output,a.tests)
    else:run(a.output,a.tests,a.component_root)
