"""Saved-data source-order/merge diagnosis and one component-only hypothesis.

The probe gates a source until D1 fluid serialization ends, not native injection
queue drainage. It is intentionally not an application backend or a FIFO fit.
"""
import argparse
from collections import Counter,defaultdict
from fractions import Fraction
import heapq
from math import ceil
from pathlib import Path
import subprocess

from wafer_sim.adapters.shared_spatial_service import max_min_rates
from wafer_sim.io import digest,object_digest,read_json,write_json


def ordered_probe(messages,capacities):
    """Same D1 paths/rates/propagation, one serializing head per source.

    Input extraction rejects use of native clocks/routes. Source eligibility is
    original ready; the surrogate source release is fluid service end. Do not
    call it a prediction of generated/first-injection boundaries.
    """
    fields=('id','token','source','destination','ready','bytes','work_packets','propagation_cycles','resources','path')
    jobs={m['id']:{k:m[k] for k in fields} for m in messages}
    arrivals=sorted((m['ready'],m['id']) for m in jobs.values())
    caps={k:Fraction(*v) if isinstance(v,list) else Fraction(v) for k,v in capacities.items()}
    waiting=defaultdict(list);heads={};active={};tails=[];out=[];now=0;rates={}
    def activate():
        for source in sorted(waiting):
            if source not in heads and waiting[source]:
                _,identity=heapq.heappop(waiting[source]);m=dict(jobs[identity],source_service_begin=now)
                active[identity]=dict(message=m,remaining=Fraction(m['work_packets']))
                heads[source]=identity
    while arrivals or active or tails or any(waiting.values()):
        boundaries=([arrivals[0][0]] if arrivals else [])+([tails[0][0]] if tails else [])+[
            now+ceil(v['remaining']/rates[i]) for i,v in active.items()]
        if not boundaries:raise ValueError('Blocked source-order probe')
        step=min(boundaries)
        for i,v in active.items():v['remaining']=max(Fraction(),v['remaining']-rates[i]*(step-now))
        now=step
        while arrivals and arrivals[0][0]==now:
            ready,identity=arrivals.pop(0);heapq.heappush(waiting[jobs[identity]['source']],(ready,identity))
        for identity in sorted([i for i,v in active.items() if v['remaining']==0]):
            m=active.pop(identity)['message'];del heads[m['source']]
            m['service_finish']=now;heapq.heappush(tails,(now+m['propagation_cycles'],identity,m))
        activate()
        paths={i:tuple(v['message']['resources']) for i,v in active.items()}
        used={r for p in paths.values() for r in p}
        rates=max_min_rates(paths,{r:caps[r] for r in used}) if paths else {}
        while tails and tails[0][0]==now:
            finish,_,m=heapq.heappop(tails);out.append(dict(m,finish=finish))
    return sorted(out,key=lambda m:m['id'])


def source_queue_rows(messages):
    groups=defaultdict(list);rows=[]
    for m in messages:groups[m['source']].append(m)
    for source,group in sorted(groups.items()):
        previous=None
        for m in sorted(group,key=lambda m:(m['generated'],m['id'])):
            expected=max(m['ready'],previous['last_inject']+1) if previous else m['ready']
            rows.append(dict(source=source,token=m['token'],id=m['id'],ready=m['ready'],generated=m['generated'],
                first_inject=m['first_inject'],last_inject=m['last_inject'],finish=m['finish'],
                source_wait=m['generated']-m['ready'],previous_token=previous['token'] if previous else None,
                expected_generated=expected,selection_boundary_matches=expected==m['generated'],
                previous_unreceived_flits_at_selection=sum(f['ejected']+1>m['generated'] for f in previous['flits'])
                    if previous and 'flits' in previous else None))
            previous=m
    return rows


def merge_rows(messages):
    # Select an actually common directed edge whose incoming identities differ.
    paths=[m['flits'][0]['router_path'] for m in messages]
    common=set(zip(paths[0],paths[0][1:]))
    for p in paths[1:]:common &= set(zip(p,p[1:]))
    edges=[]
    for a,b in sorted(common):
        inputs={p[p.index(a)-1] for p in paths if p.index(a)>0}
        if len(inputs)>1:edges.append((a,b))
    result=[]
    for a,b in edges:
        arrivals=[];per_message=[]
        for m in messages:
            events=[];input_times=[];incoming=set()
            for f in m['flits']:
                hops=f['link_arrivals']
                selected=[i for i,e in enumerate(hops) if (e['source'],e['destination'])==(a,b)]
                if len(selected)!=1:raise ValueError('Ambiguous saved common output')
                i=selected[0]
                if i==0:raise ValueError('No upstream identity at common output')
                upstream=hops[i-1]['source'];incoming.add(upstream);input_times.append(hops[i-1]['cycle'])
                events.append(hops[i]['cycle']);arrivals.append(dict(cycle=hops[i]['cycle'],input=upstream,token=m['token']))
            per_message.append(dict(token=m['token'],incoming_routers=sorted(incoming),
                first_input_arrival=min(input_times),last_input_arrival=max(input_times),
                first_output_sink_arrival=min(events),last_output_sink_arrival=max(events)))
        begin=max(m['first_output_sink_arrival'] for m in per_message)
        end=min(m['last_output_sink_arrival'] for m in per_message)+1
        selected=[e for e in arrivals if begin<=e['cycle']<end] if end>begin else []
        result.append(dict(edge=[a,b],messages=per_message,overlap_window=[begin,end] if end>begin else None,
            output_arrivals=len(selected),input_counts=dict(Counter(str(e['input']) for e in selected)),
            message_counts=dict(Counter(e['token'] for e in selected)),
            scope='Sink-arrival window counts, not an arbitration/credit intervention or queue-occupancy trace'))
    return result


def critical_sharing(messages,critical):
    edges=set()
    for m in messages:
        if m['token'] in critical:
            for f in m['flits']:
                edges.update((e['source'],e['destination']) for e in f['link_arrivals'])
    events=defaultdict(list)
    for m in messages:
        for f in m['flits']:
            for i,e in enumerate(f['link_arrivals']):
                edge=e['source'],e['destination']
                if edge in edges:
                    incoming=f"router/{f['link_arrivals'][i-1]['source']}" if i else f"endpoint/{m['source']}"
                    events[edge].append((e['cycle'],incoming,m['token']))
    out=[]
    for token in sorted(critical):
        windows=[]
        for edge,rows in events.items():
            target=[t for t,_,name in rows if name==token]
            if not target:continue
            begin,end=min(target),max(target)+1
            selected=[(incoming,name) for t,incoming,name in rows if begin<=t<end]
            peers=Counter(name for _,name in selected if name!=token)
            windows.append(dict(token=token,edge=list(edge),window=[begin,end],target_flits=len(target),
                other_flits=sum(peers.values()),peer_counts=dict(peers),input_counts=dict(Counter(i for i,_ in selected))))
        if windows:out.append(max(windows,key=lambda w:(w['other_flits'],w['edge'])))
    return out


def authenticated(root,manifest,name,checked):
    path=root/name
    if digest(path)!=manifest['artifacts_sha256'][name]:raise ValueError('Changed saved artifact '+name)
    checked.add((str(root),name));return read_json(path)


def analyze(components,applications,acceptance,output):
    if not output.is_absolute() or output.exists():raise ValueError('Fresh absolute output required')
    accepted=read_json(acceptance);cmanifest=read_json(components/'COMPLETE.json');amanifest=read_json(applications/'COMPLETE.json')
    if digest(components/'COMPLETE.json')!=accepted['component_manifest_sha256'] or digest(applications/'COMPLETE.json')!=accepted['run_manifest_sha256']:
        raise ValueError('Reference differs from published acceptance')
    if not cmanifest['complete'] or not amanifest['complete'] or (components/'FAILED.json').exists() or (applications/'FAILED.json').exists():
        raise ValueError('Incomplete reference')
    checked=set();rows=authenticated(components,cmanifest,'SUMMARY.json',checked);component=[]
    names=('two-source-stagger-0','three-shared-stagger-0','three-shared-stagger-509','three-shared-stagger-3000')
    for name in names:
        records={}
        for model in ('S','D1'):
            samples=[r for r in rows if r['name']==name and r['model']==model]
            if len(samples)!=2:raise ValueError('Missing selected component repeat')
            for sample in samples:
                rec=authenticated(components,cmanifest,sample['directory']+'/NETWORK_RESULT.json',checked)
                inp=authenticated(components,cmanifest,sample['directory']+'/INPUT.json',checked)
                if not rec['complete'] or (model=='S' and not rec['final']['drained']):raise ValueError('Incomplete component')
                if object_digest(rec['messages'])!=sample['message_sha256']:raise ValueError('Component message identity changed')
                if len(rec['messages'])!=len(inp['messages']):raise ValueError('Missing component demand')
                for i,(m,e) in enumerate(zip(sorted(rec['messages'],key=lambda m:m['id']),inp['messages'])):
                    if m['id']!=i or any(m[k]!=v for k,v in e.items()):raise ValueError('Changed component demand')
                if sample['repetition']==0:records[model]=rec
        probe=ordered_probe(records['D1']['messages'],records['D1']['flow_resource_capacities'])
        queue=source_queue_rows(records['S']['messages'])
        errors=[]
        for native,d1,p in zip(sorted(records['S']['messages'],key=lambda m:m['id']),sorted(records['D1']['messages'],key=lambda m:m['id']),probe):
            errors.append(dict(token=native['token'],ready=native['ready'],S_generated=native['generated'],
                S_first_inject=native['first_inject'],S_last_inject=native['last_inject'],
                S_first_eject=native['first_eject'],S_last_eject=native['last_eject'],S_finish=native['finish'],
                D1_finish=d1['finish'],probe_finish=p['finish'],probe_source_service_begin=p['source_service_begin'],
                probe_service_finish=p['service_finish'],D1_error=d1['finish']-native['finish'],
                probe_error=p['finish']-native['finish'],source_boundary_error=p['source_service_begin']-native['generated'],
                source=native['source'],destination=native['destination'],
                all_native_paths_equal_D1=all(f['router_path']==d1['path'] for f in native['flits'])))
        component.append(dict(name=name,messages=errors,source_queue=queue,
            merges=merge_rows(records['S']['messages']) if name.startswith('three-shared') else [],
            hypothesis='one source head until D1 fluid service end; no rate/path change; not native queue-drain prediction'))
    apps=[];details=[]
    for side in (4,6,7):
        for layout in ('local','clustered_local','remote_balanced'):
            s=authenticated(applications,amanifest,f'{side}-{layout}-S-rep-0/execution.json',checked)
            d=authenticated(applications,amanifest,f'{side}-{layout}-D1-rep-0/execution.json',checked)
            chain=authenticated(applications,amanifest,f'{side}-{layout}-S-rep-0/critical_chain.json',checked)
            critical={x['token'] for x in chain['segments'] if x['category']=='network'}
            if not s['complete'] or not d['complete']:raise ValueError('Incomplete saved application')
            queue=source_queue_rows(s['network_messages'])
            pairs=[]
            for i,a in enumerate(d['network_messages']):
                for b in d['network_messages'][i+1:]:
                    if a['source']==b['source'] and max(a['ready'],b['ready'])<min(a['service_finish'],b['service_finish']):
                        pairs.append(dict(first=a['token'],second=b['token'],source=a['source'],on_S_critical=a['token'] in critical or b['token'] in critical))
            critical_queue=[m for m in queue if m['token'] in critical]
            sharing=critical_sharing(s['network_messages'],critical)
            delayed=[m for m in queue if m['source_wait']>0];c_delayed=[m for m in critical_queue if m['source_wait']>0]
            apps.append(dict(side=side,layout=layout,messages=len(queue),S_source_delayed=len(delayed),
                S_max_source_wait=max((m['source_wait'] for m in queue),default=0),
                S_selection_boundary_mismatches=sum(not m['selection_boundary_matches'] for m in queue),
                S_critical_messages=len(critical_queue),S_critical_source_delayed=len(c_delayed),
                S_critical_max_source_wait=max((m['source_wait'] for m in critical_queue),default=0),
                D1_same_source_active_pairs=len(pairs),D1_same_source_pairs_on_S_critical=sum(p['on_S_critical'] for p in pairs),
                S_critical_temporally_shared_outputs=sum(w['other_flits']>0 for w in sharing),
                S_critical_multi_input_shared_outputs=sum(w['other_flits']>0 and len(w['input_counts'])>1 for w in sharing),
                delayed_critical_tokens=[m['token'] for m in c_delayed]))
            details.append(dict(side=side,layout=layout,queue=queue,critical_tokens=sorted(critical),
                D1_active_source_pairs=pairs,critical_sharing_windows=sharing))
    output.mkdir();write_json(output/'DETAILS.json',details)
    write_json(output/'RESULTS.json',dict(components=component,applications=apps,
        new_native_executions=0,new_application_executions=0,new_component_only_probes=len(names),
        note='Probe finish agreement does not validate its source-release boundary. Credit/grant/VC eligibility are not recorded. Application observations use separate closed loops, not controlled inputs.'))
    repo=Path(__file__).resolve().parents[3]
    write_json(output/'CHECKED.json',dict(passed=True,source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        artifacts_checked=len(checked),selected_saved_component_records=16,saved_application_records=18,
        component_manifest_sha256=digest(components/'COMPLETE.json'),application_manifest_sha256=digest(applications/'COMPLETE.json'),
        source_hashes={str(p.relative_to(repo)):digest(p) for p in (Path(__file__).resolve(),repo/'src/wafer_sim/adapters/shared_spatial_service.py',repo/'third_party/nw-design-for-wsi/rapidchiplet/booksim2/src/trafficmanager.cpp')},
        artifacts_sha256={p.name:digest(p) for p in sorted(output.iterdir()) if p.is_file()}))
    print(dict(passed=True,components=[dict(name=x['name'],probe_errors=[m['probe_error'] for m in x['messages']]) for x in component],applications=apps),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('components',type=Path);p.add_argument('applications',type=Path)
    p.add_argument('acceptance',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    analyze(a.components,a.applications,a.acceptance,a.output)
