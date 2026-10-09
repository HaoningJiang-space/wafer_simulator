"""Independent D1 component/work readback and fixed accuracy-cost decisions."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import statistics
import subprocess

from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.shared_spatial_service import audit_network
from wafer_sim.analysis.memory_abstraction_study import csv_file
from wafer_sim.analysis.independent_spatial_study import decisions
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.shared_spatial_service import (
    REPO, registration, component_cases, prepared_model, check, input_identity, verify_d0_rule)
from wafer_sim.experiments.spatial_scaling import prepare
from wafer_sim.experiments.isolated_response import semantic_config
from wafer_sim.experiments.d1_provenance import verify_saved_sources, backend_identity
from wafer_sim.io import read_json,write_json,digest,object_digest
from wafer_sim.remote import require_active_server


def verify_manifest(root):
    root=Path(root);done,start=read_json(root/'COMPLETE.json'),read_json(root/'STARTED.json')
    reg,base=registration()
    if not done['complete'] or (root/'FAILED.json').exists():raise ValueError('Incomplete D1 study')
    if start['registration']!=reg or start['base_registration']!=base:raise ValueError('Changed D1 registration')
    for name,sha in done['artifacts_sha256'].items():
        if digest(root/name)!=sha:raise ValueError('Changed D1 artifact '+name)
    source_changes=verify_saved_sources(REPO,start)
    receipt=start['tests']
    if not receipt['passed'] or digest(receipt['tests_log'])!=receipt['tests_log_sha256']:raise ValueError('Invalid D1 semantic receipt')
    return done,dict(start,readback_source_changes=source_changes)


def verify_components(root):
    root=Path(root);done,start=verify_manifest(root);reg,base=registration()
    if done['kind']!='D1_components':raise ValueError('Expected independent D1 components')
    cases=component_cases()
    if cases!=read_json(root/'CASES.json') or verify_d0_rule()!=read_json(root/'D0_RULE_VERIFIED.json'):
        raise ValueError('Changed component design or D0 service rule')
    c,_,_,_,binding,*_=prepare(reg['component_side'],'local','U1')
    rows=read_json(root/'SUMMARY.json');comparisons=[];count=0
    if len(rows)!=len(cases)*reg['component_repetitions']*2:raise ValueError('Incomplete component matrix')
    for case in cases:
        by_model={}
        for model in ('D1','S'):
            samples=[r for r in rows if r['name']==case['name'] and r['model']==model]
            if len(samples)!=reg['component_repetitions']:raise ValueError('Missing component repeat')
            hashes=set()
            for row in samples:
                directory=root/row['directory'];record=read_json(directory/'NETWORK_RESULT.json')
                if not record['complete'] or (model=='S' and not record['final']['drained']):raise ValueError('Incomplete component network')
                inp=read_json(directory/'INPUT.json')
                expected=[]
                for i,m in enumerate(case['messages']):expected.append(dict(**m,token=f'component-{i}',
                    source=c.endpoints[m['source_memory']],destination=c.endpoints[m['destination_memory']]))
                if object_digest(inp)!=object_digest(dict(case=case,machine=asdict(c.physical),messages=expected)):
                    raise ValueError('Changed component input')
                messages=sorted(record['messages'],key=lambda m:m['id'])
                if len(messages)!=len(expected):raise ValueError('Missing component message')
                for m,e in zip(messages,expected):
                    if any(m[k]!=e[k] for k in e) or m['data']!='component':raise ValueError('Changed component communication')
                if model=='S':
                    checked=audit_messages(c.target.network,messages)
                    conf=directory/'rapidchiplet/booksim2/src/rc_configs/network.conf'
                    if record['identity']['binary_sha256']!=start['binary_sha256'] or record['identity']['config_sha256']!=digest(conf):
                        raise ValueError('Changed component native identity')
                    reference_semantics=read_json(REPO/'docs/results/independent-spatial-service-001/calibration/TABLE.json')['semantic_network_config']
                    if semantic_config(conf)!=reference_semantics:raise ValueError('Changed native component policy')
                else:checked=audit_network(c.target.network,dict(network_messages=messages,
                    **{k:v for k,v in record.items() if k not in ('complete','messages')}))
                if checked!=read_json(directory/'AUDIT.json'):raise ValueError('Component audit readback differs')
                sha=object_digest(messages);hashes.add(sha)
                if sha!=row['message_sha256'] or row['durations']!=[m['finish']-m['ready'] for m in messages]:
                    raise ValueError('Component measurement differs')
                if read_json(directory/'MEASURED.json')!={k:v for k,v in row.items() if k not in ('directory','repetition')}:
                    raise ValueError('Changed component summary')
                count+=1
            if len(hashes)!=1:raise ValueError('Unstable component messages')
            by_model[model]=messages
        for d1,s in zip(by_model['D1'],by_model['S']):
            duration=d1['finish']-d1['ready'];ref=s['finish']-s['ready'];solo=2*d1['work_packets']+d1['propagation_cycles']
            if case['kind']=='single' and duration!=ref:raise ValueError('Unvalidated single-flow service')
            if case['kind'] in ('two-disjoint','two-reverse') and duration!=solo:raise ValueError('D1 falsely shares disjoint resources')
            comparisons.append(dict(name=case['name'],kind=case['kind'],token=d1['token'],ready=d1['ready'],bytes=d1['bytes'],
                D1_cycles=duration,S_cycles=ref,error_cycles=duration-ref,error_percent=100*(duration/ref-1),
                independent_D1_cycles=solo,D1_sharing_excess_cycles=duration-solo,
                predicted_path=d1['path'],native_paths=[dict(routers=list(p),flits=n) for p,n in Counter(tuple(f['router_path']) for f in s['flits']).items()]))
    return dict(passed=True,cases=len(cases),full_component_readbacks=count,solo_cases=sum(c['kind']=='single' for c in cases),
        artifact_hashes_checked=len(done['artifacts_sha256']),manifest_sha256=digest(root/'COMPLETE.json'),
        rule=read_json(root/'D0_RULE_VERIFIED.json'),cost=read_json(root/'COST.json'),comparisons=comparisons,
        readback_source_changes=start['readback_source_changes'],source_commit=start['source_commit'],new_component_executions=0)


def summarize_cost(chosen):
    cost=dict(side=chosen[0]['side'],layout=chosen[0]['layout'],model=chosen[0]['model'],samples=len(chosen))
    for phase in chosen[0]['phases']:
        name=phase['phase'];values=[next(p['wall_seconds'] for p in r['phases'] if p['phase']==name) for r in chosen]
        cost.update({name+'_median_seconds':statistics.median(values),name+'_min_seconds':min(values),name+'_max_seconds':max(values)})
    for name in ('process_wall_seconds','native_total_cpu_seconds','native_peak_rss_kib','python_lifetime_peak_rss_kib',
            'python_full_worker_peak_rss_kib','result_bytes'):
        cost[name+'_median']=statistics.median(r[name] for r in chosen)
    cost['execution_python_cpu_seconds_median']=statistics.median(next(p['python_cpu_seconds'] for p in r['phases'] if p['phase']=='execution') for r in chosen)
    cost.update(logical_messages=chosen[0]['logical_messages'],native_flits=chosen[0]['native_flits'],flow_epochs=chosen[0]['flow_epochs'])
    return cost


def analyze(root,output):
    require_active_server();root=Path(root)
    if not output.is_absolute() or output.exists():raise ValueError('Fresh absolute analysis output required')
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']):raise ValueError('Clean analysis source required')
    done,start=verify_manifest(root);reg,base=registration()
    if done['kind']!='D1_applications':raise ValueError('Expected complete applications')
    component_root=Path(done['components_root']);components=verify_components(component_root)
    if done['components_manifest_sha256']!=digest(component_root/'COMPLETE.json') or components!=read_json(root/'COMPONENTS_VERIFIED.json'):
        raise ValueError('Changed independent component evidence')
    samples=read_json(root/'SUMMARY.json');accepted=read_json(REPO/'docs/results/independent-spatial-service-001/SUMMARY.json')
    if len(samples)!=81 or done['executions']!=81:raise ValueError('Incomplete application matrix')
    rows=[];costs=[];pairs=[];choices=[];service_errors=[];routes=[];work=defaultdict(set);count=0
    for side in base['sides']:
        for layout in base['layouts']:
            results={};chains={};physical=set()
            for model in reg['models']:
                prepared=prepared_model(side,layout,model);binding=prepared[4]
                if object_digest(input_identity(prepared))!=object_digest(read_json(root/f'inputs/{side}-{layout}-{model}.json')):
                    raise ValueError('Changed machine/work/model input')
                chosen=[r for r in samples if (r['side'],r['layout'],r['model'])==(side,layout,model)]
                if len(chosen)!=base['repetitions']:raise ValueError('Missing application repeat')
                hashes=set()
                for sample in chosen:
                    directory=root/sample['directory'];result=read_json(directory/'execution.json')
                    if read_json(directory/'MEASURED.json')!={k:v for k,v in sample.items() if k not in ('directory','process_wall_seconds')}:
                        raise ValueError('Measurement summary differs')
                    if read_json(directory/'PROCESS.json')['wall_seconds']!=sample['process_wall_seconds']:raise ValueError('Changed complete-worker cost')
                    checked=check(prepared,result);chain=critical_chain(binding,result)
                    for key,value in backend_identity(model,prepared[6],result).items():
                        if sample[key]!=value:raise ValueError('Changed explicit machine/policy/backend identity')
                    if sample['backend_contract_sha256']!=object_digest(prepared[6]):raise ValueError('Changed backend contract')
                    if checked!=read_json(directory/'AUDIT.json') or object_digest(chain)!=object_digest(read_json(directory/'critical_chain.json')):
                        raise ValueError('Completion/critical-chain audit differs')
                    sha=object_digest(result);hashes.add(sha)
                    if sha!=sample['execution_sha256'] or result['application_cycles']!=sample['application_cycles']:
                        raise ValueError('Changed application execution')
                    if sample['physical_input_sha256']!=prepared[9]['physical_input_sha256'] or sample['projection_sha256']!=prepared[9]['projection_sha256']:
                        raise ValueError('Changed input digest')
                    if checked['status']!=sample['status']:raise ValueError('Changed checked status')
                    if model!='D1':
                        old=next(r for r in accepted if (r['side'],r['layout'],r['model'])==(side,layout,model))
                        if sha!=old['execution_sha256']:raise ValueError('Frozen D0/S events differ')
                    else:
                        flow=read_json(directory/'flow_network.json')
                        if not flow['complete'] or object_digest(flow['messages'])!=object_digest(result['network_messages']) or flow['flow_epochs']!=result['flow_epochs']:
                            raise ValueError('Closed fluid state differs from execution')
                    work[side].add(object_digest(dict(messages=len(result['network_messages']),bytes=sum(m['bytes'] for m in result['network_messages']),
                        work=dict(sum((Counter({e['unit']:e['amount']}) for e in result['services']),Counter())))))
                    physical.add(sample['physical_input_sha256']);count+=1
                if len(hashes)!=1:raise ValueError('Unstable repeat events')
                if model!='D1':
                    replay=read_json(root/f'{side}-{layout}-{model}-rep-0/replay/REPLAY.json')
                    if not replay['passed'] or replay['binary_sha256']!=start['binary_sha256']:raise ValueError('Native replay failed')
                results[model]=result;chains[model]=chain
                rows.append(dict(side=side,layout=layout,model=model,application_cycles=result['application_cycles'],
                    capacity_wait_sum_cycles=sum(o['capacity_wait_cycles'] for o in result['operations'].values()),
                    **{k:chain['cycles'].get(k,0) for k in ('compute','memory','network','capacity')}))
                costs.append(summarize_cost(chosen))
            if len(physical)!=1:raise ValueError('Different model physical input')
            lookup={model:{m['token']:m for m in result['network_messages']} for model,result in results.items()}
            if any(set(v)!=set(lookup['S']) for v in lookup.values()):raise ValueError('Unmatched communication across models')
            critical={s['token'] for s in chains['S']['segments'] if s['category']=='network'}
            for token,s in lookup['S'].items():
                d=lookup['D1'][token];same=sum(f['router_path']==d['path'] for f in s['flits'])
                routes.append(dict(side=side,layout=layout,token=token,bytes=d['bytes'],S_flits=len(s['flits']),
                    S_flits_matching_D1_path=same,all_S_paths_match_D1=same==len(s['flits']),
                    D1_hops=len(d['path'])-1,S_mean_hops=sum(len(f['router_path'])-1 for f in s['flits'])/len(s['flits']),
                    on_S_critical_chain=token in critical))
                if token in critical:
                    for model in reg['models']:
                        m=lookup[model][token];duration=m['finish']-m['ready'];ref=s['finish']-s['ready']
                        service_errors.append(dict(side=side,layout=layout,model=model,token=token,bytes=m['bytes'],ready=m['ready'],
                            duration_cycles=duration,reference_duration_cycles=ref,service_error_cycles=duration-ref,
                            service_error_percent=100*(duration/ref-1),ready_error_cycles=m['ready']-s['ready']))
        decision=decisions([r for r in rows if r['side']==side],reg['models'],base['tie_tolerance_cycles'],base['gap_error_budget_cycles'])
        pairs.extend(dict(side=side,**p) for p in decision['pairs']);choices.extend(dict(side=side,**p) for p in decision['choices'])
    if any(len(v)!=1 for v in work.values()):raise ValueError('Logical work differs')
    for row in rows:
        ref=next(r['application_cycles'] for r in rows if (r['side'],r['layout'],r['model'])==(row['side'],row['layout'],'S'))
        row.update(reference_cycles=ref,error_cycles=row['application_cycles']-ref,error_percent=100*(row['application_cycles']/ref-1))
        row['within_application_budget']=abs(row['error_percent'])<=base['application_error_budget_percent']
    accuracy={m:dict(mape_percent=statistics.mean(abs(r['error_percent']) for r in rows if r['model']==m),
        worst_error_percent=max(abs(r['error_percent']) for r in rows if r['model']==m),
        application_budget_passes=sum(r['within_application_budget'] for r in rows if r['model']==m)) for m in reg['models']}
    route_summary=[dict(side=side,layout=layout,messages=len(a),all_path_matches=sum(r['all_S_paths_match_D1'] for r in a),
        reference_flits=sum(r['S_flits'] for r in a),reference_flits_matching=sum(r['S_flits_matching_D1_path'] for r in a))
        for side in base['sides'] for layout in base['layouts'] for a in [[r for r in routes if r['side']==side and r['layout']==layout]]]
    output.mkdir();csv_file(output/'application.csv',rows);csv_file(output/'costs.csv',costs);csv_file(output/'design_gaps.csv',pairs)
    csv_file(output/'critical_service_errors.csv',service_errors);csv_file(output/'route_summary.csv',route_summary)
    csv_file(output/'components.csv',[{k:v for k,v in r.items() if k not in ('predicted_path','native_paths')} for r in components['comparisons']])
    # Per-message path diagnostics remain on the server, separate from inputs.
    write_json(output/'path_diagnostics.json',routes)
    write_json(output/'SUMMARY.json',dict(rows=rows,costs=costs,pairs=pairs,choices=choices,accuracy=accuracy,
        components=components,route_summary=route_summary,campaign_cost=read_json(root/'COST.json'),
        calibration_cost=read_json(REPO/'docs/results/independent-spatial-service-001/calibration/COST.json')))
    plot(output,rows,costs)
    write_json(output/'VERIFIED.json',dict(passed=True,source_commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        run_manifest_sha256=digest(root/'COMPLETE.json'),component_manifest_sha256=digest(component_root/'COMPLETE.json'),
        full_execution_readbacks=count,full_component_readbacks=components['full_component_readbacks'],native_replays=18,
        artifact_hashes_checked=len(done['artifacts_sha256']),component_artifact_hashes_checked=components['artifact_hashes_checked'],
        frozen_D0_S_event_hashes_equal=True,D1_native_processes=0,D1_flit_events=0,
        artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(dict(passed=True,executions=count,accuracy=accuracy,
        primary_pairs=[p for p in pairs if p['first']=='clustered_local' and p['second']=='remote_balanced']),flush=True)


def plot(output,rows,costs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype':'none','font.size':10})
    fig,axes=plt.subplots(1,3,figsize=(12,3.6))
    for ax,layout in zip(axes,('local','clustered_local','remote_balanced')):
        for model in ('D0','D1','S'):
            a=[r for r in rows if r['layout']==layout and r['model']==model]
            ax.plot([r['side'] for r in a],[r['application_cycles'] for r in a],'o-',label=model)
        ax.set_title(layout.replace('_',' '));ax.set_xlabel('Array side');ax.set_ylabel('Application cycles');ax.set_xticks([4,6,7])
    axes[0].legend();fig.tight_layout();fig.savefig(output/'application.svg');fig.savefig(output/'application.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(9,3.6))
    for model in ('D0','D1','S'):
        gaps=[next(r['application_cycles'] for r in rows if (r['side'],r['model'],r['layout'])==(s,model,'clustered_local'))-
              next(r['application_cycles'] for r in rows if (r['side'],r['model'],r['layout'])==(s,model,'remote_balanced')) for s in (4,6,7)]
        axes[0].plot([4,6,7],gaps,'o-',label=model)
        times=[statistics.median(c['process_wall_seconds_median'] for c in costs if c['side']==s and c['model']==model) for s in (4,6,7)]
        axes[1].plot([4,6,7],times,'o-',label=model)
    axes[0].axhspan(-100,100,color='gray',alpha=.2);axes[0].set_ylabel('A minus B (cycles)')
    axes[1].set_ylabel('Whole fresh worker seconds');axes[1].set_yscale('log')
    for ax in axes:ax.set_xlabel('Array side');ax.set_xticks([4,6,7]);ax.legend()
    fig.tight_layout();fig.savefig(output/'tradeoff_cost.svg');fig.savefig(output/'tradeoff_cost.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();analyze(a.root,a.output)
