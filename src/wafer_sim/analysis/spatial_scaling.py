"""Read back registered weak scaling; separate resource pressure from causality."""
import argparse
from collections import Counter
from pathlib import Path
import statistics
import subprocess

from wafer_sim.analysis.memory_abstraction import selection
from wafer_sim.analysis.memory_abstraction_study import csv_file
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.spatial_scaling import prepare, check_result, REPO
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server


def resource_kind(name):
    if name.startswith('sram-'): return 'sram'
    if name.startswith('dram-') or name == 'uniform/bank': return 'bank'
    if name.endswith('/channel'): return 'controller_channel'
    if name.endswith('/command'): return 'controller_command'
    if name.startswith('c') and name[1:].isdigit(): return 'compute'
    return 'external'


def pressure(compiled, result, chain):
    """Measured busy fractions and path work, not summed application delays."""
    app = result['application_cycles']; resources = []
    for name, row in result['resources'].items():
        resources.append(dict(resource=name, kind=resource_kind(name), **row,
                              busy_fraction=row['busy_cycles']/app))
    by_kind = {}
    for kind in sorted({r['kind'] for r in resources}):
        members = [r for r in resources if r['kind'] == kind]
        by_kind[kind] = dict(max_busy_fraction=max(r['busy_fraction'] for r in members),
            sum_queue_wait_cycles=sum(r['queue_wait_cycles'] for r in members),
            max_resource_queue_wait_cycles=max(r['queue_wait_cycles'] for r in members))
    memory_chain = Counter()
    for s in chain['segments']:
        if s['category'] == 'memory': memory_chain[resource_kind(s['resource'])] += s['duration']
    edges = {}
    for e in compiled.physical.connections:
        a, b = compiled.router_ids[e.source], compiled.router_ids[e.destination]
        edges[a, b] = edges[b, a] = e
    raw = result.get('native_network_messages', result['network_messages'])
    links, windows, kinds = Counter(), Counter(), Counter()
    for m in raw:
        for f in m['flits']:
            for e in f['link_arrivals']:
                key = e['source'], e['destination']; link = edges[key]
                links[key] += 1; kinds[link.kind] += 1
                # Arrival counts equal link transfers shifted by the fixed link
                # latency. A 256-cycle bin is activity, not queue saturation.
                windows[key, e['cycle']//256] += 1
    rows = [dict(link=edges[a,b].id, kind=edges[a,b].kind, source=a, destination=b,
                 flits=n, padded_bytes=n*compiled.physical.flit_bytes,
                 busy_fraction=n/app,
                 max_256cycle_activity=max(v for (edge,_),v in windows.items() if edge == (a,b))/256)
            for (a,b),n in sorted(links.items())]
    critical = {s['token'] for s in chain['segments'] if s['category'] == 'network'}
    messages = []
    for m in result['network_messages']:
        native = 'flits' in m
        paths = Counter(tuple(f['router_path']) for f in m.get('flits', []))
        messages.append(dict(token=m['token'], source_memory=m['source_memory'],
            destination_memory=m['destination_memory'], bytes=m['bytes'], ready=m['ready'],
            finish=m['finish'], duration=m['finish']-m['ready'], on_critical_chain=m['token'] in critical,
            injection_wait=m['first_inject']-m['ready'] if native else None,
            injection_span=m['last_inject']-m['first_inject'] if native else None,
            mean_physical_links=sum((len(p)-1)*n for p,n in paths.items())/sum(paths.values()) if native else None,
            routes=[dict(routers=list(p), flits=n) for p,n in sorted(paths.items())]))
    return dict(resource_summary=by_kind, memory_chain_by_resource=dict(memory_chain),
        native_kind_link_flits=dict(kinds), padded_byte_hops=sum(links.values())*compiled.physical.flit_bytes,
        max_injection_wait=max((m['first_inject']-m['ready'] for m in raw), default=0),
        resources=resources, links=rows, messages=messages)


def analyze(root, output):
    require_active_server()
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']): raise ValueError('Clean analysis required')
    done, start = read_json(root/'COMPLETE.json'), read_json(root/'STARTED.json')
    reg = start['registration']
    if not done['complete'] or (root/'FAILED.json').exists(): raise ValueError('Incomplete run')
    if reg != read_json(REPO/'configs/spatial_scaling.json'): raise ValueError('Changed registration')
    for name, sha in done['artifacts_sha256'].items():
        if digest(root/name) != sha: raise ValueError('Changed artifact '+name)
    for name, sha in start['source_hashes'].items():
        if digest(REPO/name) != sha: raise ValueError('Run semantics changed '+name)
    samples = read_json(root/'SUMMARY.json')
    if len(samples) != 81: raise ValueError('Missing full runs')
    output.mkdir(exist_ok=False)
    rows, costs, decisions, links, resources, messages, preflights = [], [], [], [], [], [], []
    checked_count = 0
    for side in reg['sides']:
        for layout in reg['layouts']:
            for model in reg['models']:
                prepared = prepare(side, layout, model)
                c, _, _, _, binding, _, _, identity, projection, preflight = prepared
                saved = read_json(root/f'inputs/{side}-{layout}-{model}.json')
                if object_digest(saved) != object_digest(dict(physical=identity,projection=projection,preflight=preflight)):
                    raise ValueError('Input readback differs')
                chosen = [r for r in samples if (r['side'],r['layout'],r['model']) == (side,layout,model)]
                if len(chosen) != reg['repetitions']: raise ValueError('Missing repeats')
                hashes = set()
                for sample in chosen:
                    d = root/sample['directory']; result = read_json(d/'execution.json')
                    if read_json(d/'MEASURED.json') != {k:v for k,v in sample.items() if k!='directory'}:
                        raise ValueError('Summary differs from measurement')
                    audit = check_result(prepared, result); chain = critical_chain(binding, result)
                    if audit != read_json(d/'AUDIT.json') or object_digest(chain) != object_digest(read_json(d/'critical_chain.json')):
                        raise ValueError('Fresh execution audit differs')
                    sha = object_digest(result); hashes.add(sha)
                    raw = result.get('native_network_messages', result['network_messages'])
                    events = dict(logical_messages=len(result['network_messages']), native_messages=len(raw),
                        native_flits=sum(len(m['flits']) for m in raw),
                        native_link_events=sum(len(f['link_arrivals']) for m in raw for f in m['flits']),
                        service_events=len(result['services']), phase_events=len(result['phases']),
                        lifecycle_events=len(result['lifecycle']))
                    if (sha != sample['execution_sha256'] or result['application_cycles'] != sample['application_cycles']
                            or audit['status'] != sample['status'] or sample['chain_cycles'] != chain['cycles']
                            or any(sample[k] != v for k,v in events.items())): raise ValueError('Event summary mismatch')
                    checked_count += 1
                if len(hashes) != 1: raise ValueError('Nondeterministic events')
                replay = read_json(root/f'{side}-{layout}-{model}-rep-0/replay/REPLAY.json')
                if not replay['passed'] or replay['binary_sha256'] != start['binary_sha256']:
                    raise ValueError('Missing matching native replay')
                key = dict(side=side,workers=side*side,layout=layout,model=model)
                detail = pressure(c, result, chain)
                for r in detail.pop('links'): links.append(dict(**key,**r))
                for r in detail.pop('resources'):
                    r.pop('work'); resources.append(dict(**key,**r))
                for r in detail.pop('messages'): messages.append(dict(**key,**r))
                app = result['application_cycles']
                rows.append(dict(**key, application_cycles=app, compute_macs=preflight['compute_macs'],
                    aggregate_macs_per_cycle=preflight['compute_macs']/app,
                    per_worker_macs_per_cycle=preflight['compute_macs']/app/(side*side),
                    compute_chain=chain['cycles'].get('compute',0), memory_chain=chain['cycles'].get('memory',0),
                    network_chain=chain['cycles'].get('network',0), capacity_chain=chain['cycles'].get('capacity',0),
                    capacity_wait_sum_cycles=sum(o['capacity_wait_cycles'] for o in result['operations'].values()),
                    mean_dram_c2c_distance=preflight['mean_c2c_distance_for_dram'],
                    max_controller_payload_bytes=preflight['max_controller_payload_bytes'], **events, **detail))
                preflights.append(dict(**key, **{k:v for k,v in preflight.items() if k not in key}))
                timing = [{p['phase']:p for p in r['phases']} for r in chosen]
                cost = dict(**key, samples=len(chosen))
                for phase in timing[0]:
                    values = [t[phase]['wall_seconds'] for t in timing]
                    cost.update({phase+'_median_seconds':statistics.median(values),phase+'_min_seconds':min(values),phase+'_max_seconds':max(values)})
                cost['execution_python_cpu_median_seconds'] = statistics.median(t['execution']['python_cpu_seconds'] for t in timing)
                for field in ('native_total_cpu_seconds','native_peak_rss_kib','python_lifetime_peak_rss_kib'):
                    cost[field+'_median'] = statistics.median(r[field] for r in chosen)
                cost['native_replay_seconds'] = read_json(root/f'{side}-{layout}-{model}-rep-0/REPLAY_COST.json')[0]['wall_seconds']
                costs.append(cost)
        decision = selection([r for r in rows if r['side']==side],reg['tie_tolerance_cycles'])
        for p in decision['pairs']: p['within_gap_budget'] = abs(p['gap_error_cycles']) <= reg['gap_error_budget_cycles']
        decisions.append(dict(side=side,**decision))
    for r in rows:
        ref = next(v['application_cycles'] for v in rows if v['side']==r['side'] and v['layout']==r['layout'] and v['model']=='S')
        base = next(v['application_cycles'] for v in rows if v['side']==4 and v['layout']==r['layout'] and v['model']==r['model'])
        r.update(reference_cycles=ref,error_cycles=r['application_cycles']-ref,error_percent=100*(r['application_cycles']/ref-1),
                 weak_scaling_time_ratio=r['application_cycles']/base)
    csv_file(output/'application.csv',[{k:v for k,v in r.items() if not isinstance(v,dict)} for r in rows])
    csv_file(output/'design_gaps.csv',[dict(side=d['side'],**p) for d in decisions for p in d['pairs']])
    csv_file(output/'costs.csv',costs); csv_file(output/'resources.csv',resources); csv_file(output/'physical_links.csv',links)
    csv_file(output/'messages.csv',[{k:v for k,v in m.items() if k!='routes'} for m in messages])
    write_json(output/'critical_routes.json',[m for m in messages if m['on_critical_chain']])
    write_json(output/'PREFLIGHT.json',preflights)
    write_json(output/'SUMMARY.json',dict(rows=rows,costs=costs,decisions=decisions))
    plot(output,rows,costs,decisions)
    write_json(output/'VERIFIED.json',dict(passed=True,run_source_commit=start['source_commit'],
        analysis_source_commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        run_manifest_sha256=digest(root/'COMPLETE.json'),artifacts_checked=len(done['artifacts_sha256']),
        full_execution_readbacks=checked_count,geometry_and_capacity_preflights=27,accepted_migration_hashes_equal=True,
        artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(dict(passed=True,full_readbacks=checked_count,cells=len(rows)),flush=True)


def plot(output,rows,costs,decisions):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    models=('U0','U1','S'); colors=('#D88928','#4C91B0','#263D57')
    layouts=('local','clustered_local','remote_balanced'); sizes=(4,6,7)
    plt.rcParams.update({'font.size':10,'svg.fonttype':'none'})
    fig,axes=plt.subplots(1,3,figsize=(12,3.8))
    for ax,layout in zip(axes,layouts):
        for model,color in zip(models,colors):
            a=[next(r for r in rows if (r['side'],r['layout'],r['model'])==(s,layout,model)) for s in sizes]
            ax.plot([s*s for s in sizes],[r['application_cycles'] for r in a],'o-',label=model,color=color)
        ax.set_title(layout.replace('_',' '));ax.set_xlabel('Compute tiles');ax.set_xticks([16,36,49]);ax.set_ylabel('Application cycles')
    axes[0].legend();fig.tight_layout();fig.savefig(output/'application.svg');fig.savefig(output/'application.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9,3.8))
    for model,color in zip(models,colors):
        gaps=[next(p['gap_cycles'] for p in d['pairs'] if p['model']==model and p['first']=='clustered_local' and p['second']=='remote_balanced') for d in decisions]
        axes[0].plot([16,36,49],gaps,'o-',label=model,color=color)
        times=[statistics.median(c['execution_median_seconds'] for c in costs if c['model']==model and c['side']==s) for s in sizes]
        axes[1].plot([16,36,49],times,'o-',label=model,color=color)
    axes[0].axhline(0,color='grey',linewidth=.8);axes[0].set_ylabel('A clustered − B balanced (cycles)')
    axes[1].set_ylabel('Execution seconds; median across layouts');axes[1].set_yscale('log')
    for ax in axes:ax.set_xlabel('Compute tiles');ax.set_xticks([16,36,49]);ax.legend()
    fig.tight_layout();fig.savefig(output/'tradeoff_cost.svg');fig.savefig(output/'tradeoff_cost.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();analyze(args.root,args.output)
