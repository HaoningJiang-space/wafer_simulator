"""Component readback, paired decisions and measured D0/U1/S costs."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
import statistics
import subprocess

from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.memory_abstraction_study import csv_file
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.independent_spatial_service import (
    REPO, registration, component_cases, component_metrics, prepared_model, input_identity, check)
from wafer_sim.experiments.isolated_response import semantic_config
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server


def verify_manifest(root):
    done, start = read_json(root/'COMPLETE.json'),read_json(root/'STARTED.json')
    if not done['complete'] or (root/'FAILED.json').exists(): raise ValueError('Incomplete study')
    reg,base = registration()
    if start['registration'] != reg or start['base_registration'] != base: raise ValueError('Changed controls')
    for name,sha in done['artifacts_sha256'].items():
        if digest(root/name) != sha: raise ValueError('Changed artifact '+name)
    for name,sha in start['source_hashes'].items():
        if digest(REPO/name) != sha: raise ValueError('Changed source '+name)
    receipt=start['tests_receipt']
    if not receipt['passed'] or digest(receipt['tests_log']) != receipt['tests_log_sha256']:
        raise ValueError('Invalid semantic receipt')
    return done,start


def verify_calibration(root):
    """Read every singleton capture, including ready-clock holdouts."""
    root=Path(root); done,start=verify_manifest(root)
    if done['kind'] != 'calibration': raise ValueError('Expected component calibration')
    table=read_json(root/'TABLE.json'); machines,cases=component_cases(); reg,_=registration()
    if table['binary_sha256'] != start['binary_sha256'] or digest(root/'TABLE.json') != done['table_sha256']:
        raise ValueError('Changed component/native identity')
    if table['schema'] != 'isolated-spatial-service-v1' or not table['validated'] or table['scope'] != reg['scope']:
        raise ValueError('Invalid component table contract')
    if set(table['machines']) != set(machines) or object_digest(cases) != object_digest(read_json(root/'CASES.json')):
        raise ValueError('Calibration coverage differs from machine/input plans')
    count=0;holdouts=0
    for mid,c in machines.items():
        part=table['machines'][mid]
        if object_digest(part['machine']) != object_digest(asdict(c.physical)): raise ValueError('Changed physical machine')
        expected={case['key'] for case in cases if case['machine_sha256']==mid}
        if set(part['entries']) != expected: raise ValueError('Missing/extra component entry')
    for case in cases:
        c=machines[case['machine_sha256']];part=table['machines'][case['machine_sha256']]
        entry=part['entries'][case['key']]
        expected_ready=list(reg['calibration_ready_cycles'])
        if case['supplemental']: expected_ready.append(reg['validation_ready_cycle']);holdouts+=1
        if [s['ready'] for s in entry['samples']] != expected_ready: raise ValueError('Missing ready-clock validation')
        metrics={k:v for k,v in entry.items() if k!='samples'}
        for sample in entry['samples']:
            d=root/sample['directory'];record=read_json(d/'online_network.json')
            if (digest(d/'online_network.json') != sample['record_sha256'] or not record['complete'] or
                    not record['final']['drained'] or len(record['messages']) != 1): raise ValueError('Invalid isolated record')
            inp=read_json(d/'INPUT.json')
            if inp != dict(case=case,ready=sample['ready']): raise ValueError('Changed probe input')
            m=record['messages'][0]
            if (m['ready']!=sample['ready'] or m['source']!=case['source'] or m['destination']!=case['destination'] or
                    m['bytes']!=case['bytes'] or m['source_memory']!=case['source_memory'] or
                    m['destination_memory']!=case['destination_memory'] or m['token']!='component' or m['data']!='component'):
                raise ValueError('Probe differs from registered transfer')
            checked=audit_messages(c.target.network,[m])
            if checked != read_json(d/'AUDIT.json') or component_metrics(m) != metrics or read_json(d/'METRICS.json') != metrics:
                raise ValueError('Independent component readback differs')
            conf=d/'rapidchiplet/booksim2/src/rc_configs/network.conf'
            if (record['identity']['binary_sha256']!=table['binary_sha256'] or record['identity']['config_sha256']!=digest(conf) or
                    semantic_config(conf)!=table['semantic_network_config'] or
                    digest(conf.parent.parent/'rc_topologies/network.anynet')!=part['topology_sha256']):
                raise ValueError('Changed physical network/policy')
            count+=1
    cost=read_json(root/'COST.json')
    if cost['probe_executions']!=count or cost['component_cases']!=len(cases) or cost['supplemental_holdouts']!=holdouts:
        raise ValueError('Component cost/coverage count differs')
    return table,dict(passed=True,component_cases=len(cases),full_probe_readbacks=count,
        supplemental_holdouts=holdouts,artifact_hashes_checked=len(done['artifacts_sha256']),
        table_sha256=digest(root/'TABLE.json'),calibration_manifest_sha256=digest(root/'COMPLETE.json'),
        calibration_root=str(root),cost=cost)


def decisions(rows, models, tolerance, budget):
    lookup={(r['model'],r['layout']):r['application_cycles'] for r in rows}
    layouts=sorted({r['layout'] for r in rows}); best_s=min(lookup['S',p] for p in layouts)
    relation=lambda gap:'tie' if abs(gap)<=tolerance else 'first' if gap<0 else 'second'
    pairs=[];choices=[]
    for model in models:
        best=min(lookup[model,p] for p in layouts)
        candidates=[p for p in layouts if lookup[model,p]<=best+tolerance]
        regrets=[lookup['S',p]-best_s for p in candidates]
        choices.append(dict(model=model,candidates=candidates,reference_regret_min_cycles=min(regrets),reference_regret_max_cycles=max(regrets)))
        for a,b in combinations(layouts,2):
            gap=lookup[model,a]-lookup[model,b];ref=lookup['S',a]-lookup['S',b]
            pairs.append(dict(model=model,first=a,second=b,gap_cycles=gap,reference_gap_cycles=ref,
                gap_error_cycles=gap-ref,within_gap_budget=abs(gap-ref)<=budget,
                predicted_relation=relation(gap),reference_relation=relation(ref),selection_disagreement=relation(gap)!=relation(ref)))
    return dict(pairs=pairs,choices=choices)


def analyze(root, output):
    require_active_server()
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']): raise ValueError('Clean analysis source required')
    done,start=verify_manifest(root);reg,base=registration()
    if done['kind'] != 'applications': raise ValueError('Expected application study')
    calibration=Path(done['calibration_root']);table,component_checked=verify_calibration(calibration)
    if (digest(calibration/'COMPLETE.json') != done['calibration_manifest_sha256'] or
            object_digest(table)!=object_digest(read_json(root/'TABLE.json')) or digest(root/'TABLE.json')!=done['table_sha256']):
        raise ValueError('Applications use another component table')
    samples=read_json(root/'SUMMARY.json')
    if len(samples)!=81 or done['executions']!=81: raise ValueError('Missing full executions')
    accepted=read_json(REPO/'docs/results/spatial-scaling-001/SUMMARY.json')
    rows=[];costs=[];pairs=[];choices=[];critical=[];checked_count=0;work_hashes=defaultdict(set)
    for side in base['sides']:
        for layout in base['layouts']:
            physical_hashes=set()
            for model in reg['models']:
                prepared=prepared_model(side,layout,model,table);c,_,_,_,binding,_,spec,*_=prepared
                saved=read_json(root/f'inputs/{side}-{layout}-{model}.json')
                if object_digest(saved)!=object_digest(input_identity(prepared)): raise ValueError('Changed frozen input')
                chosen=[s for s in samples if (s['side'],s['layout'],s['model'])==(side,layout,model)]
                if len(chosen)!=base['repetitions']: raise ValueError('Missing repetitions')
                hashes=set()
                for sample in chosen:
                    d=root/sample['directory'];result=read_json(d/'execution.json')
                    if read_json(d/'MEASURED.json')!={k:v for k,v in sample.items() if k!='directory'}: raise ValueError('Changed measurement')
                    checked=check(prepared,result);chain=critical_chain(binding,result)
                    if checked!=read_json(d/'AUDIT.json') or object_digest(chain)!=object_digest(read_json(d/'critical_chain.json')):
                        raise ValueError('Completion/chain readback differs')
                    sha=object_digest(result);hashes.add(sha)
                    if sha!=sample['execution_sha256'] or result['application_cycles']!=sample['application_cycles']:
                        raise ValueError('Result/summary mismatch')
                    if (sample['physical_input_sha256']!=prepared[9]['physical_input_sha256'] or
                            sample['projection_sha256']!=prepared[9]['projection_sha256'] or checked['status']!=sample['status']):
                        raise ValueError('Changed input/status identity')
                    if model!='D0':
                        old=next(s for s in accepted if (s['side'],s['layout'],s['model'])==(side,layout,model))
                        if sha!=old['execution_sha256']: raise ValueError('Frozen U1/S event mismatch')
                    work_hashes[side].add(object_digest(dict(messages=len(result['network_messages']),
                        bytes=sum(m['bytes'] for m in result['network_messages']),
                        work=dict(sum((Counter({e['unit']:e['amount']}) for e in result['services']),Counter())))))
                    physical_hashes.add(sample['physical_input_sha256']);checked_count+=1
                if len(hashes)!=1: raise ValueError('Unstable repeat events')
                d=root/f'{side}-{layout}-{model}-rep-0';replayed=read_json(d/'replay/REPLAY.json')
                if not replayed['passed'] or replayed['binary_sha256']!=start['binary_sha256']: raise ValueError('Native replay mismatch')
                row=dict(side=side,layout=layout,model=model,application_cycles=result['application_cycles'],
                    capacity_wait_sum_cycles=sum(o['capacity_wait_cycles'] for o in result['operations'].values()),
                    **{k:chain['cycles'].get(k,0) for k in ('compute','memory','network','capacity')})
                rows.append(row)
                cost=dict(side=side,layout=layout,model=model,samples=len(chosen))
                for phase in chosen[0]['phases']:
                    name=phase['phase'];values=[next(p['wall_seconds'] for p in s['phases'] if p['phase']==name) for s in chosen]
                    cost.update({name+'_median_seconds':statistics.median(values),name+'_min_seconds':min(values),name+'_max_seconds':max(values)})
                for field in ('native_total_cpu_seconds','native_peak_rss_kib','python_lifetime_peak_rss_kib'):
                    cost[field+'_median']=statistics.median(s[field] for s in chosen)
                cost['logical_messages']=chosen[0]['logical_messages'];cost['native_flits']=chosen[0]['native_flits']
                costs.append(cost)
                tokens={s['token'] for s in chain['segments'] if s['category']=='network'}
                for m in result['network_messages']:
                    if m['token'] in tokens:
                        critical.append(dict(side=side,layout=layout,model=model,token=m['token'],bytes=m['bytes'],
                            source_memory=m['source_memory'],destination_memory=m['destination_memory'],ready=m['ready'],
                            finish=m['finish'],duration=m['finish']-m['ready']))
            if len(physical_hashes)!=1: raise ValueError('Different model physical inputs')
        decision=decisions([r for r in rows if r['side']==side],reg['models'],base['tie_tolerance_cycles'],base['gap_error_budget_cycles'])
        pairs.extend(dict(side=side,**p) for p in decision['pairs']);choices.extend(dict(side=side,**p) for p in decision['choices'])
    # Work scales by array size; compare models/layouts within each size below.
    for side in base['sides']:
        subset=[s for s in samples if s['side']==side]
        if len({s['logical_messages'] for s in subset})!=1: raise ValueError('Logical message count differs')
    if any(len(values)!=1 for values in work_hashes.values()): raise ValueError('Logical work differs within a registered size')
    for r in rows:
        ref=next(v['application_cycles'] for v in rows if v['side']==r['side'] and v['layout']==r['layout'] and v['model']=='S')
        r.update(reference_cycles=ref,error_cycles=r['application_cycles']-ref,error_percent=100*(r['application_cycles']/ref-1))
        r['within_application_budget']=abs(r['error_percent'])<=base['application_error_budget_percent']
    accuracy={m:dict(mape_percent=statistics.mean(abs(r['error_percent']) for r in rows if r['model']==m),
        worst_error_percent=max(abs(r['error_percent']) for r in rows if r['model']==m)) for m in reg['models']}
    output.mkdir();csv_file(output/'application.csv',rows);csv_file(output/'design_gaps.csv',pairs);csv_file(output/'costs.csv',costs)
    csv_file(output/'critical_messages.csv',critical)
    component_rows=[]
    _,cases=component_cases()
    for case in cases:
        if case['supplemental']:
            e=table['machines'][case['machine_sha256']]['entries'][case['key']]
            component_rows.append(dict(bytes=case['bytes'],c2c_hops=int(case['destination_memory'].split('-')[1]),
                duration_cycles=e['duration_cycles'],injection_span=e['injection_span'],first_inject_wait=e['first_inject_wait']))
    csv_file(output/'components.csv',component_rows)
    write_json(output/'SUMMARY.json',dict(rows=rows,costs=costs,pairs=pairs,choices=choices,accuracy=accuracy,
        component_verification=component_checked,calibration_cost=read_json(calibration/'COST.json')))
    plot(output,rows,costs)
    write_json(output/'VERIFIED.json',dict(passed=True,full_execution_readbacks=checked_count,native_replays=27,
        artifact_hashes_checked=len(done['artifacts_sha256']),component_verification=component_checked,
        source_commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        run_manifest_sha256=digest(root/'COMPLETE.json'),frozen_U1_S_event_hashes_equal=True,
        artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(dict(passed=True,executions=checked_count,accuracy=accuracy,
        primary_pairs=[p for p in pairs if p['first']=='clustered_local' and p['second']=='remote_balanced']),flush=True)


def plot(output,rows,costs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype':'none','font.size':10})
    fig,axes=plt.subplots(1,3,figsize=(12,3.6))
    for ax,layout in zip(axes,('local','clustered_local','remote_balanced')):
        for model in ('U1','D0','S'):
            a=[r for r in rows if r['layout']==layout and r['model']==model]
            ax.plot([r['side'] for r in a],[r['application_cycles'] for r in a],'o-',label=model)
        ax.set_title(layout.replace('_',' '));ax.set_xlabel('Array side');ax.set_ylabel('Application cycles');ax.set_xticks([4,6,7])
    axes[0].legend();fig.tight_layout();fig.savefig(output/'application.svg');plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9,3.6))
    for model in ('U1','D0','S'):
        gaps=[next(r['application_cycles'] for r in rows if (r['side'],r['model'],r['layout'])==(s,model,'clustered_local'))-
              next(r['application_cycles'] for r in rows if (r['side'],r['model'],r['layout'])==(s,model,'remote_balanced')) for s in (4,6,7)]
        axes[0].plot([4,6,7],gaps,'o-',label=model)
        times=[statistics.median(c['execution_median_seconds'] for c in costs if c['side']==s and c['model']==model) for s in (4,6,7)]
        axes[1].plot([4,6,7],times,'o-',label=model)
    axes[0].axhspan(-100,100,color='gray',alpha=.2);axes[0].set_ylabel('A minus B (cycles)')
    axes[1].set_ylabel('Median execution seconds');axes[1].set_yscale('log')
    for ax in axes: ax.set_xlabel('Array side');ax.set_xticks([4,6,7]);ax.legend()
    fig.tight_layout();fig.savefig(output/'tradeoff_cost.svg');plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();analyze(a.root,a.output)
