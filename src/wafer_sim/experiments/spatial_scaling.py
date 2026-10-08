"""Registered complete-work weak scaling; frozen models, fresh processes."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys

from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine, export_booksim
from wafer_sim.adapters.scaling_layout import place_scaled, capacity_bound
from wafer_sim.adapters.memory_abstraction import project
from wafer_sim.adapters.uniform_memory_network import UniformMemoryNetwork
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.architecture.wafer_machine import from_config, validate
from wafer_sim.analysis.memory_abstraction import audit
from wafer_sim.analysis.wafer_machine import audit_machine
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.memory_abstraction import REPO, FROZEN
from wafer_sim.experiments.wafer_machine import replay
from wafer_sim.experiments.transfer_granularity import Meter, native_peak, usage
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server
from wafer_sim.workloads.memory_machine import build


def prepare(side, layout, model):
    registration = read_json(REPO/'configs/spatial_scaling.json')
    cfg = read_json(REPO/registration['machine']); cfg['array'] = [side, side]
    c = compile_machine(from_config(cfg))
    work, meta = build(side*side, **registration['per_worker'])
    p = place_scaled(meta, side, layout); base, tx = bind_machine(work, c, p)
    bound = capacity_bound(base)
    b, timing, contract = project(c, base, model)
    capacity_bound(b)
    loads = Counter(); distance_bytes = 0; dram_bytes = 0
    stores = {s.id: s for s in c.physical.stores}
    for t in tx:
        src, dst = stores[t['source']], stores[t['destination']]
        dram = src if src.kind == 'dram' else dst if dst.kind == 'dram' else None
        if dram is None: continue
        loads[dram.controller] += t['bytes']
        local = dst if src.kind == 'dram' else src
        a = int(local.tile[1:]); z = int(dram.tile[1:])
        distance_bytes += t['bytes']*(abs(a//side-z//side)+abs(a%side-z%side))
        dram_bytes += t['bytes']
    identity = dict(machine=asdict(c.physical), workload=asdict(work), placement=asdict(p),
        plans={k: asdict(v) for k, v in base.plans.items()}, capacities={k: asdict(v) for k, v in base.memory.items()})
    projection = dict(contract=contract, homes=dict(b.homes), timing=asdict(timing),
        plans={k: asdict(v) for k, v in b.plans.items()}, capacities={k: asdict(v) for k, v in b.memory.items()})
    preflight = dict(side=side, layout=layout, model=model, workers=side*side,
        compute_macs=meta['macs'], geometry=validate(c.physical), capacity_bound=bound,
        controller_payload_bytes=dict(loads), max_controller_payload_bytes=max(loads.values()),
        mean_c2c_distance_for_dram=distance_bytes/dram_bytes,
        physical_input_sha256=object_digest(identity), projection_sha256=object_digest(projection),
        resource_totals=dict(compute_macs_per_cycle=side*side*dict(c.physical.compute_rates)['mac'],
            bank_bytes_per_cycle=sum(s.bytes_per_cycle for s in c.physical.stores if s.kind == 'dram'),
            hb_bytes_per_cycle_per_direction=sum(l.bytes_per_cycle for l in c.physical.connections if l.kind == 'hb'),
            central_horizontal_cut_bytes_per_cycle_per_direction=side*c.physical.flit_bytes))
    return c, work, p, base, b, timing, contract, identity, projection, preflight


def check_result(prepared, result):
    c, work, p, base, b, timing, contract, _, _, preflight = prepared
    checked = audit(c, base, b, timing, contract, result)
    if any(o['capacity_wait_cycles'] for o in result['operations'].values()):
        raise ValueError('Unexpected capacity bottleneck despite conservative all-operation bound')
    if contract['model'] == 'S': checked['physical'] = audit_machine(work, p, c, b, result)
    if preflight['side'] == 4 and contract['model'] == 'S' and preflight['layout'] in {'local', 'remote_balanced'}:
        old = 'near' if preflight['layout'] == 'local' else 'opposite'
        accepted = next(r for r in read_json(REPO/'docs/results/wafer-machine-001/SUMMARY.json') if r['data_placement'] == old)
        if object_digest(result) != accepted['execution_sha256']: raise ValueError('Migration changed accepted S events')
    return checked


def worker(output, side, layout, model, frozen_input):
    root = require_active_server(); reg = read_json(REPO/'configs/spatial_scaling.json')
    output.mkdir(exist_ok=False); meter = Meter()
    with meter.phase('graph_binding_preparation'): prepared = prepare(side, layout, model)
    c, work, p, base, b, timing, contract, identity, projection, preflight = prepared
    if object_digest(dict(physical=identity, projection=projection, preflight=preflight)) != digest_input(frozen_input):
        raise ValueError('Preflight input changed')
    sys.path.insert(0, str(REPO/'third_party/nw-design-for-wsi'))
    with meter.phase('network_configuration'): config = export_booksim(c, output, reg['network_seed'])
    child = usage(resource.RUSAGE_CHILDREN)
    with meter.phase('network_initialization'):
        native = OnlineBookSim(root/'build/booksim-online/online_booksim', config, output, flit_bytes=c.physical.flit_bytes)
        client = native if model == 'S' else UniformMemoryNetwork(native, contract)
    try:
        with meter.phase('execution'): result = execute(b, timing, network=client, cycle_limit=reg['cycle_limit'])
        peaks = dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                     native_peak_rss_kib=native_peak(native))
        with meter.phase('network_close_serialization'): client.close()
    finally: client.abort()
    native_cpu = usage(resource.RUSAGE_CHILDREN)-child
    with meter.phase('result_serialization'): write_json(output/'execution.json', result)
    with meter.phase('independent_audit'):
        checked = check_result(prepared, result)
        write_json(output/'AUDIT.json', checked)
        chain = critical_chain(b, result); write_json(output/'critical_chain.json', chain)
    messages = result.get('native_network_messages', result['network_messages'])
    row = dict(side=side, layout=layout, model=model, application_cycles=result['application_cycles'],
        execution_sha256=object_digest(result), physical_input_sha256=preflight['physical_input_sha256'],
        projection_sha256=preflight['projection_sha256'], compute_macs=preflight['compute_macs'],
        phases=meter.rows, native_total_cpu_seconds=native_cpu, **peaks, chain_cycles=chain['cycles'],
        logical_messages=len(result['network_messages']), native_messages=len(messages),
        native_flits=sum(len(m['flits']) for m in messages),
        native_link_events=sum(len(f['link_arrivals']) for m in messages for f in m['flits']),
        service_events=len(result['services']), phase_events=len(result['phases']),
        lifecycle_events=len(result['lifecycle']), status=checked['status'],
        load=os.getloadavg(), affinity=sorted(os.sched_getaffinity(0)))
    write_json(output/'MEASURED.json', row)


def digest_input(path): return object_digest(read_json(path))


def run(output, tests):
    root = require_active_server(); reg = read_json(REPO/'configs/spatial_scaling.json')
    if not output.is_absolute(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain']): raise ValueError('Clean source required')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = read_json(tests)
    if (not receipt['passed'] or receipt['source_commit'] != commit or 'test_spatial_scaling' not in receipt['modules']
            or digest(receipt['tests_log']) != receipt['tests_log_sha256']): raise ValueError('Same-source passing tests required')
    frozen = FROZEN+['src/wafer_sim/adapters/memory_abstraction.py', 'src/wafer_sim/adapters/uniform_memory_network.py']
    if subprocess.check_output(['git','-C',str(REPO),'diff',reg['frozen_model_commit'],'--name-only','--',*frozen]):
        raise ValueError('Frozen physical or model semantics changed')
    binary = root/'build/booksim-online/online_booksim'
    accepted = read_json(REPO/'docs/results/wafer-machine-001/STARTED.json')['binary_sha256']
    if digest(binary) != accepted: raise ValueError('Use the byte-identical accepted native binary')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:])
    output.mkdir(exist_ok=False); (output/'inputs').mkdir()
    write_json(output/'STARTED.json', dict(source_commit=commit, registration=reg, tests_receipt=receipt,
        binary_sha256=accepted, frozen_paths=frozen, host=platform.node(), python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        affinity=sorted(os.sched_getaffinity(0)), load=os.getloadavg(),
        source_hashes={str(p.relative_to(REPO)):digest(p) for p in [*sorted((REPO/'src').rglob('*.py')),
            REPO/'configs/spatial_scaling.json',REPO/reg['machine'],REPO/'docs/SPATIAL_SCALING_PROTOCOL.md']}))
    try:
        for side in reg['sides']:
            for layout in reg['layouts']:
                for model in reg['models']:
                    *_, identity, projection, preflight = prepare(side, layout, model)
                    write_json(output/f'inputs/{side}-{layout}-{model}.json', dict(physical=identity,projection=projection,preflight=preflight))
        for rep in range(reg['repetitions']):
            models = reg['models'][rep:]+reg['models'][:rep]
            for side in reg['sides']:
                for layout in reg['layouts']:
                    for model in models:
                        name = f'{side}-{layout}-{model}'
                        with (output/'worker.log').open('a') as log:
                            subprocess.run([sys.executable,'-m','wafer_sim.experiments.spatial_scaling','--worker',
                                '--output',str(output/f'{name}-rep-{rep}'),'--side',str(side),'--layout',layout,'--model',model,
                                '--input',str(output/f'inputs/{name}.json')],check=True,stdout=log,stderr=subprocess.STDOUT,timeout=900)
                        print(name,rep,flush=True)
        sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'))
        for side in reg['sides']:
            c, *_ = prepare(side,'local','S')
            for layout in reg['layouts']:
                for model in reg['models']:
                    d=output/f'{side}-{layout}-{model}-rep-0'; meter=Meter()
                    with meter.phase('native_command_replay'): replay(c,binary,d,d/'replay',reg['network_seed'])
                    write_json(d/'REPLAY_COST.json',meter.rows)
        rows=[]
        for path in sorted(output.glob('*-rep-*/MEASURED.json')):
            row=read_json(path); row['directory']=str(path.parent.relative_to(output)); rows.append(row)
        if len(rows)!=81: raise ValueError('Incomplete registered matrix')
        for side in reg['sides']:
            for layout in reg['layouts']:
                a=[r for r in rows if r['side']==side and r['layout']==layout]
                if len({r['physical_input_sha256'] for r in a})!=1: raise ValueError('Changed same-machine input')
                for model in reg['models']:
                    if len({r['execution_sha256'] for r in a if r['model']==model})!=1: raise ValueError('Unstable repeated events')
        write_json(output/'SUMMARY.json',rows)
        write_json(output/'COMPLETE.json',dict(complete=True,source_commit=commit,cells=27,executions=81,native_replays=27,
            artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    except BaseException as exc:
        write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc)));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--tests',type=Path)
    p.add_argument('--worker',action='store_true');p.add_argument('--side',type=int)
    p.add_argument('--layout');p.add_argument('--model');p.add_argument('--input',type=Path)
    args=p.parse_args()
    if args.worker:worker(args.output,args.side,args.layout,args.model,args.input)
    else:run(args.output,args.tests)
