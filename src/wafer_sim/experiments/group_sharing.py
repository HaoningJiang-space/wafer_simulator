"""Frozen models, independent complete groups in one physical network."""
import argparse
import csv
from dataclasses import asdict
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from wafer_sim.adapters.wow import rank_mapping
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.adapters.transformer_groups import place_groups
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.memory_boundary import reserve_endpoint_storage
from wafer_sim.execution.plan import ExecutionPolicy
from wafer_sim.experiments.memory_boundary import worker
from wafer_sim.experiments.boundary_design import _remote
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.workloads.transformer import build_block


def prepare(d):
    export = read_json(d['network_json']); wc = d['workload']; config = d['experiment']
    cm = {k: wc[k] for k in ('region_capacity_bytes', 'compute_rates', 'memory_bytes_per_cycle')}
    cm['scope'] = 'Common analytical compute/memory; not calibrated to WoW'
    target, timing, contract = build_wow_target(export, cm, config['flit_bytes'])
    block = build_block(**wc['block'])
    ordered = rank_mapping(export['endpoints'], 16, 'row_major')
    endpoints = {'A': ordered[:8], 'B': ordered[8:]}
    selected = {g: endpoints[g] for g in d['groups']}
    work, placement = place_groups(block, selected)
    binding = bind(work, target, placement, execution_policy=ExecutionPolicy(**config['execution_policy']))
    cfg = d['boundary']
    binding = reserve_endpoint_storage(binding, cfg['flit_bytes'], cfg['tx_slots'], cfg['rx_slots'])
    identity = dict(logical_workload=asdict(work), mapping=asdict(placement),
        target=asdict(target), timing=asdict(timing), resource_contract=contract,
        group_endpoints=selected, execution_policy=config['execution_policy'],
        boundary_contract=cfg, usable_memory={k: asdict(v) for k,v in binding.memory.items()},
        memory_quantum_bytes=d['memory_quantum_bytes'])
    return binding, timing, export, identity


def check_frozen(repo, revision):
    paths = ['src/wafer_sim/'+p for p in ('architecture','adapters','execution','workloads')]+['third_party','patches']
    differences = subprocess.check_output(['git','diff','--name-status',revision,'HEAD','--',*paths],cwd=repo,text=True).splitlines()
    allowed = {'A\tsrc/wafer_sim/workloads/groups.py', 'A\tsrc/wafer_sim/adapters/transformer_groups.py'}
    if set(differences) - allowed:
        raise ValueError('Frozen model changed: '+str(differences))
    return dict(reference=revision, preexisting_model_files_unchanged=True, additions=differences)


def strip_namespace(value, group='A'):
    """Only used for exact same-work compatibility with the frozen single group."""
    if isinstance(value, str): return value.replace(group+'/', '')
    if isinstance(value, tuple): return tuple(strip_namespace(v, group) for v in value)
    if isinstance(value, list): return [strip_namespace(v, group) for v in value]
    if isinstance(value, dict): return {strip_namespace(k, group): strip_namespace(v, group) for k,v in value.items()}
    return value


def run(output, tests, cpus=None):
    _remote(); repo=Path(__file__).resolve().parents[3]; runtime=repo.parent
    output=Path(output); tests=Path(tests)
    if not output.is_absolute(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo): raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    receipt=read_json(tests)
    if not receipt['passed'] or receipt['source_commit']!=commit or digest(receipt['tests_log'])!=receipt['tests_log_sha256']:
        raise ValueError('Same-source semantic tests required')
    reg=read_json(repo/'configs/group_sharing.json'); frozen=check_frozen(repo, reg['frozen_commit'])
    prior=Path(reg['accepted_run']); accepted=read_json(prior/'COMPLETE.json'); start=read_json(prior/'STARTED.json')
    if not accepted['all_registered_work_complete']: raise ValueError('Incomplete accepted baseline')
    for f,h in accepted['artifacts_sha256'].items():
        if digest(prior/f)!=h: raise ValueError('Accepted evidence changed: '+f)
    binaries={n:digest(runtime/p) for n,p in dict(boundary='build/booksim-boundary/endpoint_booksim',
        accepted_online='build/booksim-online/online_booksim',standalone='build/booksim/rapidchiplet/booksim2/src/booksim').items()}
    if binaries!=start['binaries']: raise ValueError('Frozen native binary changed')
    cpus=sorted(os.sched_getaffinity(0))[-2:] if cpus is None else cpus
    if len(set(cpus))!=2 or not set(cpus)<=os.sched_getaffinity(0): raise ValueError('Two allowed CPUs required')
    output.mkdir(exist_ok=False)
    write_json(output/'STARTED.json',dict(source_commit=commit, registration=reg, frozen_models=frozen,
        accepted_manifest_sha256=digest(prior/'COMPLETE.json'), binaries=binaries,
        tests_receipt=read_json(tests), tests_sha256=digest(tests), host=platform.node(), python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()), packages=subprocess.check_output(
            [sys.executable,'-m','pip','freeze'],text=True).splitlines(), affinity=cpus, load=os.getloadavg(),
        source_hashes={str(p.relative_to(repo)):digest(p) for p in [*sorted((repo/'src').rglob('*.py')),
            repo/'configs/group_sharing.json',repo/'docs/GROUP_SHARING_PROTOCOL.md']},
        build_source=start['build_source'],build_manifest_sha256=start['build_manifest_sha256']))
    launches=[]; compatibility={}
    try:
        # Save every placement and control before the first application run.
        for scenario,groups in reg['scenarios'].items():
            for placement in reg['placements']:
                case=scenario+'__'+placement; base=output/case; base.mkdir()
                d=read_json(prior/('s64__burst_256__'+placement)/'INPUT_CONFIG.json'); d['groups']=groups
                write_json(base/'INPUT_CONFIG.json',d)
                b,_,e,identity=prepare(d); locations={v['node']:v for v in e['endpoints']}
                write_json(base/'MANIFEST.json',dict(input_identity=object_digest(identity),
                    workload_identity=object_digest(identity['logical_workload']), groups=groups,
                    group_endpoints=identity['group_endpoints'], group_locations={g:[locations[n] for n in ns]
                        for g,ns in identity['group_endpoints'].items()}, resources=e['resources'],
                    network_sha256=digest(d['network_json']), operations=len(b.graph.operations),
                    target=identity['resource_contract'], memory_quantum_bytes=d['memory_quantum_bytes'],
                    boundary=d['boundary'], visibility='whole_object',
                    models=reg['modes'], network_instances=1, time_zero_release=True))
        for scenario in reg['scenarios']:
            for repeat in range(reg['repetitions']):
                offset=repeat%len(reg['modes']); modes=reg['modes'][offset:]+reg['modes'][:offset]
                places=reg['placements'][repeat%2:]+reg['placements'][:repeat%2]
                for mode in modes:
                    for placement in places:
                        case=scenario+'__'+placement; base=output/case; dest=base/f'{mode}-{repeat}'
                        before=os.getloadavg(); t0=time.perf_counter()
                        with (base/f'{mode}-{repeat}.log').open('w') as log:
                            p=subprocess.run([sys.executable,'-m','wafer_sim.experiments.group_sharing',str(dest),
                                '--worker',str(base/'INPUT_CONFIG.json'),'--mode',mode,'--cpus',','.join(map(str,cpus))],
                                cwd=repo,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                        if p.returncode: raise RuntimeError('Worker failed: '+str(dest))
                        measured=read_json(dest/'MEASURED.json')
                        if measured['input_identity']!=read_json(base/'MANIFEST.json')['input_identity']:
                            raise ValueError('Declared input changed')
                        if scenario=='A':
                            old=prior/('s64__burst_256__'+placement)/(mode+'-0')
                            result=strip_namespace(read_json(dest/'execution.json'))
                            if object_digest(result)!=read_json(old/'MEASURED.json')['execution_identity']:
                                raise ValueError('Namespace-normalized full-event compatibility failed: '+case+'/'+mode)
                            old_input=read_json(old/'INPUT.json'); new_input=read_json(dest/'INPUT.json')
                            for field in ('logical_workload','mapping','target','timing','usable_memory'):
                                if strip_namespace(new_input[field])!=old_input[field]:
                                    raise ValueError('Single-group input compatibility failed: '+field)
                            compatibility[case+'/'+mode]=dict(full_events_equal=True,
                                normalization='remove A/ from logical identities only; no timestamps removed',
                                normalized_execution_sha256=object_digest(result))
                        launches.append(dict(case=case,scenario=scenario,placement=placement,mode=mode,repeat=repeat,
                            worker=str(dest),worker_wall_seconds=time.perf_counter()-t0,
                            load_before=before,load_after=os.getloadavg()))
                        write_json(output/'LAUNCHES.json',launches)
                        print(case,mode,repeat,measured['application_cycles'],flush=True)
        for scenario in reg['scenarios']:
            for placement in reg['placements']:
                for mode in reg['modes']:
                    rows=[read_json(Path(l['worker'])/'MEASURED.json') for l in launches
                        if (l['scenario'],l['placement'],l['mode'])==(scenario,placement,mode)]
                    if len(rows)!=reg['repetitions'] or len({r['execution_identity'] for r in rows})!=1:
                        raise ValueError('Missing/divergent repetition')
        write_json(output/'COMPATIBILITY.json',compatibility)
        write_json(output/'COMPLETE.json',dict(all_registered_work_complete=True,source_commit=commit,
            artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    except BaseException as error:
        write_json(output/'FAILED.json',dict(type=type(error).__name__,message=str(error))); raise


def analyze_run(root, output):
    _remote(); root=Path(root); output=Path(output)
    if not output.is_absolute(): raise ValueError('Fresh absolute output required')
    output.mkdir(exist_ok=False)
    check_frozen(Path(__file__).resolve().parents[3], read_json(root/'STARTED.json')['registration']['frozen_commit'])
    from wafer_sim.analysis.group_sharing import analyze, plot
    from wafer_sim.analysis.boundary_study import replay
    result=analyze(root); replays=[]
    for launch in read_json(root/'LAUNCHES.json'):
        if launch['repeat']: continue
        directory=Path(launch['worker']); d=read_json(directory.parent/'INPUT_CONFIG.json')
        _,_,exported,_=prepare(d)
        replays.append(dict(case=launch['case'],mode=launch['mode'],**replay(directory,d,exported,
            output/('replay-'+launch['case']+'-'+launch['mode']))))
    result['acceptance']['native_command_replays']=replays
    for key in ('rows','decision_table','group_interference','shared_resources','paired_messages','costs'):
        rows=result[key]
        with (output/(key+'.csv')).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write_json(output/'SUMMARY.json',{k:result[k] for k in ('rows','decision_table','group_interference','shared_resources')})
    write_json(output/'ACCEPTANCE.json',result['acceptance']); plot(result,output)
    write_json(output/'ANALYZED.json',dict(passed=True,input_manifest_sha256=digest(root/'COMPLETE.json'),
        analysis_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(result['decision_table'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('output',type=Path)
    p.add_argument('--tests'); p.add_argument('--analyze'); p.add_argument('--worker')
    p.add_argument('--mode',choices=['serial','bounded']); p.add_argument('--cpus')
    args=p.parse_args(); _remote(); cpus=[int(c) for c in args.cpus.split(',')] if args.cpus else None
    if args.worker: worker(args.worker,args.mode,args.output,cpus,prepare_case=prepare)
    elif args.analyze: analyze_run(args.analyze,args.output)
    else: run(args.output,args.tests,cpus)


if __name__=='__main__': main()
