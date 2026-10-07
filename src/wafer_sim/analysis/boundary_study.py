"""Independent accepted-run readback and paired boundary-model comparison."""
from collections import defaultdict
from statistics import median
from pathlib import Path

from wafer_sim.io import read_json,digest,object_digest,write_json
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.memory_boundary import audit_occupancy
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.adapters.memory_boundary import fuse_movements


def movement_rows(result,source_map):
    if result.get('boundary'):
        return {f"{m['token'].rsplit('/phase/',1)[0]}/phase/{source_map[m['token'].rsplit('/phase/',1)[0]][str(m['token'].rsplit('/phase/',1)[1])]['transfer']}":dict(
            source=m['source'],destination=m['destination'],bytes=m['bytes'],ready=m['ready'],
            first_supply=min(p['supplied'] for p in m['packets']),last_supply=max(p['supplied'] for p in m['packets']),
            first_receive=min(p['received'] for p in m['packets']),last_receive=max(p['received'] for p in m['packets']),
            commit=m['finish']) for m in result['boundary']['moves']}
    phases={(p['operation'],p['phase']):p for p in result['phases']}
    rows={}
    for m in result['network_messages']:
        op,index=m['token'].rsplit('/phase/',1);index=int(index)
        rows[m['token']]=dict(source=m['source'],destination=m['destination'],bytes=m['bytes'],
            ready=phases[op,index-1]['ready'],first_supply=m['ready'],last_supply=m['ready'],
            first_receive=m['first_eject']+1,last_receive=m['finish'],commit=phases[op,index+1]['finish'])
    return rows


def replay(directory,descriptor,exported,output):
    """Replay recorded endpoint commands without memory controller or DAG executor."""
    from wafer_sim.experiments.memory_boundary import client
    output=Path(output);output.mkdir(exist_ok=False)
    native=client(descriptor,exported,output)
    entries=[__import__('json').loads(s) for s in (directory/'online_protocol.jsonl').read_text().splitlines()]
    checked=0
    try:
        for i,event in enumerate(entries):
            if 'request' not in event:continue
            request=event['request'];expected=entries[i+1]['reply']
            observed=native._request(request)
            if observed!=expected:raise ValueError('Independent endpoint-command replay diverged')
            checked+=1
            if request['command']=='close':
                native.process.stdin.close()
                if native.process.wait(timeout=60):raise ValueError('Replay native failed')
    finally:native.abort()
    record=dict(passed=True,commands=checked,scope='same native binary, recorded supply/commit commands; no Python execution controller',
                protocol_sha256=digest(directory/'online_protocol.jsonl'),binary_sha256=native.identity['binary_sha256'])
    write_json(output/'REPLAY.json',record)
    return record


def analyze(root):
    from wafer_sim.experiments.memory_boundary import prepare
    root=Path(root);manifest=read_json(root/'COMPLETE.json');started=read_json(root/'STARTED.json')
    if not manifest['all_registered_work_complete']:raise ValueError('Incomplete registered experiment')
    for name,h in manifest['artifacts_sha256'].items():
        if digest(root/name)!=h:raise ValueError('Changed artifact: '+name)
    launches=read_json(root/'LAUNCHES.json');reg=started['registration']
    samples=defaultdict(list);events={};inputs={};checked=[]
    for launch in launches:
        directory=Path(launch['worker']);case,mode=launch['case'],launch['mode']
        descriptor=read_json(directory.parent/'INPUT_CONFIG.json')
        b,t,e,identity=prepare(descriptor)
        if mode!='serial':b,_=fuse_movements(b)
        r=read_json(directory/'execution.json');measured=read_json(directory/'MEASURED.json')
        if measured['input_identity']!=object_digest(identity) or measured['execution_identity']!=object_digest(r):
            raise ValueError('Changed work or execution identity')
        check=audit(b,t,r);chain=critical_chain(b,r)
        if chain!=read_json(directory/'critical_chain.json'):raise ValueError('Changed critical chain')
        checked.append(dict(case=case,mode=mode,repeat=launch['repeat'],audit=check))
        samples[case,mode].append(dict(**measured,worker_wall_seconds=launch['worker_wall_seconds']))
        if launch['repeat']==0:
            events[case,mode]=dict(result=r,moves=movement_rows(r,read_json(directory/'PHASE_MAP.json')),chain=chain)
            inputs[case,mode]=measured['input_identity']
    cases=list(dict.fromkeys(l['case'] for l in launches))
    rows=[];messages=[];costs=[];mechanisms=[]
    for case in cases:
        if len({inputs[case,m] for m in reg['modes']})!=1:raise ValueError('Model comparison changed input')
        reference=events[case,'bounded'];ref=reference['result'];rm=reference['moves']
        for mode in reg['modes']:
            entry=events[case,mode];r=entry['result'];moves=entry['moves']
            if set(moves)!=set(rm):raise ValueError('Changed logical movement set')
            errors=[]
            for token,m in moves.items():
                other=rm[token]
                if any(m[k]!=other[k] for k in ('source','destination','bytes')):raise ValueError('Changed movement work')
                duration=m['commit']-m['ready'];true=other['commit']-other['ready'];error=duration-true
                errors.append((abs(error),100*abs(error)/true))
                messages.append(dict(case=case,mode=mode,token=token,**m,service_cycles=duration,
                    reference_service_cycles=true,error_cycles=error,absolute_commit_shift=m['commit']-other['commit']))
            delta=r['application_cycles']-ref['application_cycles'];ape=100*abs(delta)/ref['application_cycles']
            occupancy=audit_occupancy(r['boundary']) if 'boundary' in r else None
            rows.append(dict(case=case,mode=mode,application_cycles=r['application_cycles'],error_cycles=delta,ape=ape,
                application_target_met=ape<=reg['application_tolerance_percent'] and abs(delta)<=reg['application_tolerance_cycles'],
                max_message_error_cycles=max(v[0] for v in errors),max_message_ape=max(v[1] for v in errors),
                message_target_met=all(x<=reg['message_tolerance_cycles'] and y<=reg['message_tolerance_percent'] for x,y in errors),
                occupancy=occupancy,capacity_feasible=None if mode=='serial' else not occupancy['rx_overflow_slots'],
                memory_bytes=sum(s['amount'] for s in r['services'] if s['category']=='memory'),
                memory_busy_cycles=sum(s['resource_released']-s['start'] for s in r['services'] if s['category']=='memory'),
                logical_network_bytes=sum(m['bytes'] for m in r['network_messages']),
                network_flits=sum(m['expected_flits'] for m in r['network_messages']),
                critical_chain_cycles=entry['chain']['cycles'],
                peak_total_reserved_bytes=max(samples[case,mode][0]['peak_total_reserved_bytes'].values())))
            group=samples[case,mode]
            for phase in group[0]['phases']:
                for metric in ('wall_seconds','python_cpu_seconds','exited_children_cpu_seconds'):
                    values=[next(p[metric] for p in x['phases'] if p['phase']==phase['phase']) for x in group]
                    costs.append(dict(case=case,mode=mode,phase=phase['phase'],metric=metric,
                        median=median(values),minimum=min(values),maximum=max(values),samples=len(values)))
            for metric in ('worker_wall_seconds','python_lifetime_peak_rss_kib','native_peak_rss_kib'):
                vals=[v[metric] for v in group];costs.append(dict(case=case,mode=mode,phase='whole_process',metric=metric,
                    median=median(vals),minimum=min(vals),maximum=max(vals),samples=len(vals)))
        if len({r['memory_bytes'] for r in rows if r['case']==case})!=1:raise ValueError('Memory work not conserved')
        if len({(r['logical_network_bytes'],r['network_flits']) for r in rows if r['case']==case})!=1:
            raise ValueError('Network work not conserved')
        detail=dict(case=case)
        native=ref['network_messages']
        edge_sets=[{(h['source'],h['destination']) for f in m['flits'] for h in f['link_arrivals']} for m in native]
        detail['shared_directed_links']=sorted(set().union(*(a&b for i,a in enumerate(edge_sets) for b in edge_sets[i+1:]))) if len(edge_sets)>1 else []
        if case in ('single','slow_source'):
            m=ref['boundary']['moves'][0];packet=m['packets'];width=ref['boundary']['flit_bytes']
            flights={p['received']-p['supplied'] for p in packet}
            # No competing source/sink clients during this move: independent
            # source serialization and destination FCFS recurrence must close.
            read_duration=packet[0]['supplied']-m['ready'];last=m['ready'];expected=[]
            if len(flights)!=1:raise ValueError('Isolated supplied-packet latency is not constant')
            flight=next(iter(flights))
            write_duration=packet[0]['committed']-packet[0]['received']
            for k,p in enumerate(packet):
                supply=m['ready']+(k+1)*read_duration
                arrival=supply+flight;last=max(arrival,last)+write_duration
                if (p['supplied'],p['received'],p['committed'])!=(supply,arrival,last):raise ValueError('Isolated service recurrence failed')
                expected.append(last)
            detail.update(recurrence_passed=True,read_packet_cycles=read_duration,
                          fixed_native_packet_flight=flight,write_packet_cycles=write_duration,last_commit=last)
        mechanisms.append(detail)
    return dict(rows=rows,messages=messages,costs=costs,mechanisms=mechanisms,
        acceptance=dict(passed=True,checked_artifact_count=len(manifest['artifacts_sha256']),
            complete_manifest_sha256=digest(root/'COMPLETE.json'),checked=checked,binaries=started['binaries'],
            source_commit=started['source_commit'],registration=reg),
        scope='Conditional streaming DMA design; same analytical memory/compute, not measured WoW accuracy')
