"""Pre-registered D0 component calibration and frozen U1/D0/S comparison."""
import argparse
from collections import Counter
from dataclasses import asdict
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from wafer_sim.adapters.independent_spatial_service import IndependentSpatialNetwork, contract, key, machine_identity
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.adapters.uniform_memory_network import UniformMemoryNetwork
from wafer_sim.adapters.wafer_machine import export_booksim
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.independent_spatial_service import audit as audit_d0
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.spatial_scaling import prepare, check_result
from wafer_sim.experiments.memory_abstraction import REPO, FROZEN
from wafer_sim.experiments.isolated_response import semantic_config
from wafer_sim.experiments.transfer_granularity import Meter, native_peak, usage
from wafer_sim.experiments.wafer_machine import replay
from wafer_sim.execution.plan import Transfer
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server

REGISTRATION = 'configs/independent_spatial_service.json'
FROZEN_D0 = FROZEN + ['src/wafer_sim/adapters/memory_abstraction.py',
    'src/wafer_sim/adapters/uniform_memory_network.py', 'src/wafer_sim/adapters/scaling_layout.py',
    'src/wafer_sim/experiments/spatial_scaling.py', 'configs/spatial_scaling.json']


def registration():
    reg = read_json(REPO/REGISTRATION)
    return reg, read_json(REPO/reg['base_registration'])


def gate(output, tests):
    root = require_active_server(); reg, _ = registration()
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']): raise ValueError('Clean source required')
    commit = subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    receipt = read_json(tests)
    if (not receipt['passed'] or receipt['source_commit'] != commit or 'test_independent_spatial_service' not in receipt['modules'] or
            digest(receipt['tests_log']) != receipt['tests_log_sha256']): raise ValueError('Same-source D0 tests required')
    if subprocess.check_output(['git','-C',str(REPO),'diff',reg['frozen_commit'],'--name-only','--',*FROZEN_D0]):
        raise ValueError('Frozen machine, work, U1/S or execution changed')
    binary = root/'build/booksim-online/online_booksim'
    expected = read_json(REPO/'docs/results/spatial-scaling-001/STARTED.json')['binary_sha256']
    if digest(binary) != expected: raise ValueError('Changed accepted native binary')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:])
    sys.path.insert(0, str(REPO/'third_party/nw-design-for-wsi'))
    output.mkdir()
    files = [*sorted((REPO/'src').rglob('*.py')), REPO/REGISTRATION,
        REPO/reg['base_registration'], REPO/'configs/wafer_machine.json', REPO/'docs/INDEPENDENT_SPATIAL_SERVICE_PROTOCOL.md']
    write_json(output/'STARTED.json', dict(source_commit=commit, registration=reg, base_registration=registration()[1],
        tests_receipt=receipt, tests_receipt_sha256=digest(tests), binary_sha256=expected,
        host=platform.node(), python=sys.version, executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        affinity=sorted(os.sched_getaffinity(0)), load=os.getloadavg(), frozen_paths=FROZEN_D0,
        source_hashes={str(p.relative_to(REPO)):digest(p) for p in files}))
    return binary


def finish(output, **fields):
    write_json(output/'COMPLETE.json', dict(complete=True, **fields,
        artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))


def component_cases():
    """Only machine and complete input plans; never reads application results."""
    reg, base_reg = registration(); machines, cases = {}, {}
    for side in base_reg['sides']:
        c, *_ = prepare(side, 'local', 'U1'); mid = machine_identity(c); machines[mid] = c
        for layout in base_reg['layouts']:
            prepared = prepare(side, layout, 'U1'); binding = prepared[4]
            banks = set(prepared[6]['dram_regions'])
            for plan in binding.plans.values():
                for phase in plan.phases:
                    t = phase.transfer
                    if t is None or not {t.source_memory,t.destination_memory} & banks: continue
                    k = key(t.source_endpoint,t.destination_endpoint,t.size_bytes)
                    cases[mid,k] = dict(machine_sha256=mid,side=side,key=k,source_memory=t.source_memory,
                        destination_memory=t.destination_memory,source=t.source_endpoint,destination=t.destination_endpoint,
                        bytes=t.size_bytes,supplemental=False)
    c, *_ = prepare(reg['supplemental_side'], 'local', 'U1'); mid = machine_identity(c)
    for hops in reg['supplemental_c2c_hops']:
        for size in reg['supplemental_sizes_bytes']:
            src,dst = 'dram-0-0',f'sram-{hops}'
            k = key(c.endpoints[src],c.endpoints[dst],size)
            cases[mid,k] = dict(machine_sha256=mid,side=reg['supplemental_side'],key=k,
                source_memory=src,destination_memory=dst,source=c.endpoints[src],destination=c.endpoints[dst],
                bytes=size,supplemental=True)
    return machines, [cases[k] for k in sorted(cases)]


def component_metrics(m):
    flits = sorted(m['flits'],key=lambda f:f['id'])
    injections = [f['injected'] for f in flits]
    return dict(duration_cycles=m['finish']-m['ready'],
        first_inject_wait=injections[0]-m['ready'], injection_span=injections[-1]-injections[0],
        injection_gap_histogram={str(k):v for k,v in sorted(Counter(b-a for a,b in zip(injections,injections[1:])).items())},
        routes=[dict(routers=list(p),flits=n) for p,n in sorted(Counter(tuple(f['router_path']) for f in flits).items())])


def probe(c, binary, directory, case, ready):
    reg, base_reg = registration(); directory.mkdir(); meter = Meter()
    with meter.phase('network_configuration'): config = export_booksim(c,directory,base_reg['network_seed'])
    write_json(directory/'INPUT.json',dict(case=case,ready=ready))
    child = usage(resource.RUSAGE_CHILDREN)
    with meter.phase('network_initialization'):
        client = OnlineBookSim(binary,config,directory,flit_bytes=c.physical.flit_bytes)
    try:
        with meter.phase('isolated_execution'):
            client.advance(ready)
            client.submit('component',Transfer('component',case['source_memory'],case['destination_memory'],
                case['source'],case['destination'],case['bytes']),ready)
            client.advance(ready+reg['component_cycle_budget'])
            if client.pending: raise TimeoutError('Component probe incomplete')
        peaks = dict(native_peak_rss_kib=native_peak(client))
        with meter.phase('network_close_serialization'): record = client.close()
    finally: client.abort()
    if len(record['messages']) != 1: raise ValueError('Component has background traffic')
    with meter.phase('independent_audit'):
        checked = audit_messages(c.target.network,record['messages'])
        metrics = component_metrics(record['messages'][0])
        write_json(directory/'AUDIT.json',checked); write_json(directory/'METRICS.json',metrics)
    write_json(directory/'MEASURED.json',dict(phases=meter.rows,**peaks,native_cpu_seconds=usage(resource.RUSAGE_CHILDREN)-child))
    return metrics, digest(directory/'online_network.json'), config


def calibrate(output, tests):
    binary = gate(output,tests); reg, _ = registration(); started = time.perf_counter()
    try:
        machines, cases = component_cases(); write_json(output/'CASES.json',cases)
        table = dict(schema='isolated-spatial-service-v1', validated=True, binary_sha256=digest(binary),
            scope=reg['scope'],machines={},semantic_network_config=None)
        for mid,c in machines.items():
            table['machines'][mid] = dict(machine=asdict(c.physical),topology_sha256=None,entries={})
        validation_count = 0
        for i,case in enumerate(cases):
            c = machines[case['machine_sha256']]; samples=[]; measurements=[]
            ready_cycles = list(reg['calibration_ready_cycles'])
            if case['supplemental']: ready_cycles.append(reg['validation_ready_cycle'])
            for rep,ready in enumerate(ready_cycles):
                name = f'component-{i:04d}-rep-{rep}'
                metrics,sha,conf = probe(c,binary,output/name,case,ready)
                part = table['machines'][case['machine_sha256']]
                top = digest(conf.parent.parent/'rc_topologies/network.anynet'); semantics = semantic_config(conf)
                if table['semantic_network_config'] is None: table['semantic_network_config'] = semantics
                if part['topology_sha256'] is None: part['topology_sha256'] = top
                if table['semantic_network_config'] != semantics or part['topology_sha256'] != top:
                    raise ValueError('Changed component policy/physical topology')
                samples.append(dict(directory=name,ready=ready,record_sha256=sha)); measurements.append(metrics)
            if any(m != measurements[0] for m in measurements):
                raise ValueError('Isolated service depends on idle ready clock; table is insufficient')
            table['machines'][case['machine_sha256']]['entries'][case['key']] = dict(**measurements[0],samples=samples)
            validation_count += int(case['supplemental'])
            if i % 25 == 0 or i == len(cases)-1: print('component',i+1,'/',len(cases),flush=True)
        write_json(output/'TABLE.json',table)
        write_json(output/'COST.json',dict(wall_seconds=time.perf_counter()-started,
            python_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            component_cases=len(cases),probe_executions=sum(len(e['samples']) for p in table['machines'].values() for e in p['entries'].values()),
            supplemental_holdouts=validation_count,table_bytes=(output/'TABLE.json').stat().st_size))
        finish(output,kind='calibration',table_sha256=digest(output/'TABLE.json'),cases=len(cases))
    except BaseException as exc:
        write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc))); raise


def prepared_model(side, layout, model, table):
    prepared = list(prepare(side,layout,'U1' if model == 'D0' else model))
    if model == 'D0':
        prepared[6] = contract(prepared[0],table)
        prepared[8] = dict(prepared[8],contract=prepared[6])
        prepared[9] = dict(prepared[9],model=model,projection_sha256=object_digest(prepared[8]))
    return prepared


def check(prepared, result):
    if prepared[6]['model'] != 'D0': return check_result(prepared,result)
    c, _, _, base, b, timing, spec, *_ = prepared
    checked = audit_d0(c,base,b,timing,spec,result)
    if any(o['capacity_wait_cycles'] for o in result['operations'].values()): raise ValueError('Unexpected capacity waits')
    return checked


def input_identity(prepared):
    return dict(physical=prepared[7],projection=prepared[8],preflight=prepared[9])


def worker(output, side, layout, model, frozen_input, table_path):
    root = require_active_server(); _, reg = registration(); output.mkdir(); meter=Meter()
    with meter.phase('graph_binding_preparation'):
        table = read_json(table_path) if model == 'D0' else None
        prepared = prepared_model(side,layout,model,table)
    c, _, _, _, b, timing, spec, *_ = prepared
    if object_digest(input_identity(prepared)) != object_digest(read_json(frozen_input)): raise ValueError('Changed frozen input')
    sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'))
    with meter.phase('network_configuration'): config=export_booksim(c,output,reg['network_seed'])
    if model == 'D0':
        if (semantic_config(config) != spec['semantic_network_config'] or
                digest(config.parent.parent/'rc_topologies/network.anynet') != spec['topology_sha256']):
            raise ValueError('D0 calibration uses another physical network')
    child=usage(resource.RUSAGE_CHILDREN)
    with meter.phase('network_initialization'):
        native=OnlineBookSim(root/'build/booksim-online/online_booksim',config,output,flit_bytes=c.physical.flit_bytes)
        client = native if model == 'S' else IndependentSpatialNetwork(native,spec) if model == 'D0' else UniformMemoryNetwork(native,spec)
    try:
        with meter.phase('execution'): result=execute(b,timing,network=client,cycle_limit=reg['cycle_limit'])
        peaks=dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,native_peak_rss_kib=native_peak(native))
        with meter.phase('network_close_serialization'): client.close()
    finally: client.abort()
    child_cpu=usage(resource.RUSAGE_CHILDREN)-child
    with meter.phase('result_serialization'): write_json(output/'execution.json',result)
    with meter.phase('independent_audit'):
        checked=check(prepared,result); write_json(output/'AUDIT.json',checked)
        chain=critical_chain(b,result); write_json(output/'critical_chain.json',chain)
    raw=result.get('native_network_messages',result['network_messages'])
    write_json(output/'MEASURED.json',dict(side=side,layout=layout,model=model,
        application_cycles=result['application_cycles'],execution_sha256=object_digest(result),
        physical_input_sha256=prepared[9]['physical_input_sha256'],projection_sha256=prepared[9]['projection_sha256'],
        phases=meter.rows,native_total_cpu_seconds=child_cpu,**peaks,status=checked['status'],chain_cycles=chain['cycles'],
        logical_messages=len(result['network_messages']),native_messages=len(raw),native_flits=sum(len(m['flits']) for m in raw),
        native_link_events=sum(len(f['link_arrivals']) for m in raw for f in m['flits']),
        service_events=len(result['services']),phase_events=len(result['phases']),lifecycle_events=len(result['lifecycle']),
        affinity=sorted(os.sched_getaffinity(0)),load=os.getloadavg()))


def run(output, tests, calibration):
    from wafer_sim.analysis.independent_spatial_study import verify_calibration
    binary=gate(output,tests); reg,base_reg=registration()
    try:
        table,verified=verify_calibration(calibration)
        write_json(output/'CALIBRATION_VERIFIED.json',verified)
        write_json(output/'TABLE.json',table)
        for side in base_reg['sides']:
            for layout in base_reg['layouts']:
                for model in reg['models']:
                    prepared=prepared_model(side,layout,model,table)
                    write_json(output/f'inputs/{side}-{layout}-{model}.json',input_identity(prepared))
        # Calibration is frozen before any application starts. Children receive
        # only their own frozen input and this table, never accepted S evidence.
        for rep in range(base_reg['repetitions']):
            models=reg['models'][rep:]+reg['models'][:rep]
            for side in base_reg['sides']:
                for layout in base_reg['layouts']:
                    for model in models:
                        name=f'{side}-{layout}-{model}'
                        with (output/'worker.log').open('a') as log:
                            subprocess.run([sys.executable,'-m','wafer_sim.experiments.independent_spatial_service','--worker',
                                '--output',str(output/f'{name}-rep-{rep}'),'--side',str(side),'--layout',layout,'--model',model,
                                '--input',str(output/f'inputs/{name}.json'),'--table',str(output/'TABLE.json')],
                                check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
                        print(name,rep,flush=True)
        sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'))
        rows=[]
        accepted=read_json(REPO/'docs/results/spatial-scaling-001/SUMMARY.json')
        for side in base_reg['sides']:
            c, *_=prepare(side,'local','S')
            for layout in base_reg['layouts']:
                for model in reg['models']:
                    chosen=[]
                    for rep in range(base_reg['repetitions']):
                        d=output/f'{side}-{layout}-{model}-rep-{rep}'; row=read_json(d/'MEASURED.json')
                        row['directory']=d.name; rows.append(row); chosen.append(row)
                    if len({r['execution_sha256'] for r in chosen})!=1: raise ValueError('Unstable full executions')
                    if model!='D0':
                        old=next(r for r in accepted if (r['side'],r['layout'],r['model'])==(side,layout,model))
                        if chosen[0]['execution_sha256'] != old['execution_sha256']: raise ValueError('Frozen U1/S events changed')
                    d=output/f'{side}-{layout}-{model}-rep-0'; meter=Meter()
                    with meter.phase('native_command_replay'): replay(c,binary,d,d/'replay',base_reg['network_seed'])
                    write_json(d/'REPLAY_COST.json',meter.rows)
        write_json(output/'SUMMARY.json',rows)
        finish(output,kind='applications',cells=27,executions=len(rows),native_replays=27,
            calibration_root=str(calibration),calibration_manifest_sha256=digest(calibration/'COMPLETE.json'),
            table_sha256=digest(output/'TABLE.json'))
    except BaseException as exc:
        write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc))); raise


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--tests',type=Path)
    p.add_argument('--calibrate',action='store_true');p.add_argument('--calibration',type=Path)
    p.add_argument('--worker',action='store_true');p.add_argument('--side',type=int);p.add_argument('--layout')
    p.add_argument('--model');p.add_argument('--input',type=Path);p.add_argument('--table',type=Path)
    a=p.parse_args()
    if a.worker: worker(a.output,a.side,a.layout,a.model,a.input,a.table)
    elif a.calibrate: calibrate(a.output,a.tests)
    else: run(a.output,a.tests,a.calibration)
