"""Independent readback: own-position solos, shared routes and model decisions."""
from collections import Counter, defaultdict
from pathlib import Path

from wafer_sim.analysis.boundary_study import analyze as boundary_analysis, movement_rows
from wafer_sim.analysis.boundary_design import decision_table, public_status
from wafer_sim.io import read_json, object_digest


def group_times(result, group):
    prefix=group+'/'
    outputs={k:v for k,v in result['output_ready'].items() if k.startswith(prefix) and k.endswith('/output:out')}
    if len(outputs)!=8: raise ValueError('Missing full TP8 outputs')
    operations={k:v for k,v in result['operations'].items() if k.startswith(prefix)}
    return dict(output_ready=max(outputs.values()),retired=max(v['retired'] for v in operations.values()))


def progress_changes(solo, joint, group):
    operations={op:dict(solo=r,joint=joint['operations'][op]) for op,r in solo['operations'].items()
        if r!=joint['operations'][op]}
    collectives={name:dict(solo=solo['operations'][group+'/'+name],joint=joint['operations'][group+'/'+name])
        for name in ('attention_sum','ffn_sum')}
    return dict(changed_operation_count=len(operations),changed_operations=operations,
                collective_progress=collectives)


def shared_paths(messages):
    """Actual link arrivals; overlapping time envelopes are not saturation."""
    links={'A':defaultdict(list),'B':defaultdict(list)}; routers={'A':set(),'B':set()}
    for message in messages:
        group=message['token'].split('/',1)[0]
        for flit in message['flits']:
            routers[group].update(flit['router_path'])
            for hop in flit['link_arrivals']:
                links[group][hop['source'],hop['destination']].append(hop['cycle'])
    shared=sorted(set(links['A']) & set(links['B'])); details=[]
    for edge in shared:
        a,b=links['A'][edge],links['B'][edge]
        details.append(dict(source=edge[0],destination=edge[1],a_flits=len(a),b_flits=len(b),
            a_first=min(a),a_last=max(a),b_first=min(b),b_last=max(b),
            arrival_envelopes_overlap=max(min(a),min(b))<=min(max(a),max(b))))
    return dict(shared_directed_links=len(shared),shared_routers=len(routers['A'] & routers['B']),
        a_directed_links=len(links['A']),b_directed_links=len(links['B']),
        shared_links_with_overlapping_arrival_envelopes=sum(d['arrival_envelopes_overlap'] for d in details),
        shared_link_details=details)


def message_observations(result, origins, chain, mode):
    critical={s.get('token') for s in chain['segments']}; rows={}
    for message in result['network_messages']:
        token=message['token']; op,phase=token.rsplit('/phase/',1)
        canonical=token if mode=='serial' else f"{op}/phase/{origins[op][phase]['transfer']}"
        read_token=f'{op}/phase/{int(phase)-1}'; write_token=f'{op}/phase/{int(phase)+1}'
        services=result['services']
        reads=[s for s in services if (s['token']==read_token if mode=='serial' else s['token'].startswith(token+'/read/'))]
        writes=[s for s in services if (s['token']==write_token if mode=='serial' else s['token'].startswith(token+'/write/'))]
        supply=message['ready'] if mode=='serial' else min(p['supplied'] for m in result['boundary']['moves']
            if m['token']==token for p in m['packets'])
        rows[canonical]=dict(paths=[dict(path=list(p),flits=n) for p,n in sorted(Counter(
            tuple(f['router_path']) for f in message['flits']).items())],
            source_memory_queue=sum(s['start']-s['ready'] for s in reads),
            destination_memory_queue=sum(s['start']-s['ready'] for s in writes),
            first_flit_injection_wait=message['first_inject']-supply,
            on_observed_critical_chain=bool(critical.intersection((token,read_token,write_token) if mode=='serial' else (token,))))
    return rows


def analyze(root):
    from wafer_sim.experiments.group_sharing import prepare
    root=Path(root); result=boundary_analysis(root,prepare_case=prepare)
    reg=result['acceptance']['registration']; launches=read_json(root/'LAUNCHES.json')
    expected={(s,p,m,n) for s in reg['scenarios'] for p in reg['placements'] for m in reg['modes'] for n in range(reg['repetitions'])}
    found=set(); events={}; metadata={}; inputs={}; hashes=defaultdict(set)
    for l in launches:
        key=l['scenario'],l['placement'],l['mode'],l['repeat']
        if key in found: raise ValueError('Duplicate launch')
        found.add(key); directory=Path(l['worker']); case=l['case']
        if case!=l['scenario']+'__'+l['placement'] or directory.resolve()!=(root/case/f"{l['mode']}-{l['repeat']}").resolve():
            raise ValueError('Worker outside registered cell')
        d=read_json(directory.parent/'INPUT_CONFIG.json')
        old=read_json(Path(reg['accepted_run'])/('s64__burst_256__'+l['placement'])/'INPUT_CONFIG.json')
        if d!={**old,'groups':reg['scenarios'][l['scenario']]}:
            raise ValueError('Changed solo/group target controls')
        measured=read_json(directory/'MEASURED.json'); hashes[key[:3]].add(measured['execution_identity'])
        identity=read_json(directory/'INPUT.json')
        if identity!=read_json(root/case/(reg['modes'][0]+'-0')/'INPUT.json'):
            raise ValueError('Model/repetition changed input')
        metadata[case]=dict(scenario=l['scenario'],placement=l['placement'])
        if l['repeat']==0:
            recorded=read_json(directory/'execution.json'); origins=read_json(directory/'PHASE_MAP.json')
            events[key[:3]]=dict(result=recorded,moves=movement_rows(recorded,origins),
                observations=message_observations(recorded,origins,read_json(directory/'critical_chain.json'),l['mode']))
            inputs[key[:2]]=identity
    if found!=expected or any(len(h)!=1 for h in hashes.values()): raise ValueError('Incomplete/divergent experiment')
    for placement in reg['placements']:
        joint=inputs['AB',placement]
        for group in ('A','B'):
            solo=inputs[group,placement]; prefix=group+'/'
            for field in ('data','operations'):
                projection=[r for r in joint['logical_workload'][field] if r['id'].startswith(prefix)]
                if projection!=solo['logical_workload'][field]: raise ValueError('Logical solo not exact joint projection')
            for field in ('compute','data'):
                if {k:v for k,v in joint['mapping'][field].items() if k.startswith(prefix)}!=solo['mapping'][field]:
                    raise ValueError('Solo changed physical position')
            for field in ('target','timing','usable_memory','boundary_contract','memory_quantum_bytes','execution_policy'):
                if joint[field]!=solo[field]: raise ValueError('Solo changed resource/policy contract')
        if set(joint['group_endpoints']['A']) & set(joint['group_endpoints']['B']): raise ValueError('Groups share local resources')
    for scenario in reg['scenarios']:
        if inputs[scenario,'baseline']['logical_workload']!=inputs[scenario,'ours_rotated']['logical_workload']:
            raise ValueError('Placement changed logical work')
    for row in result['rows']:
        row.update(metadata[row['case']]); row.update(public_status(row))
        if row['mode']=='bounded' and row['capacity_status']!='feasible': raise ValueError('Reference capacity violated')
    for row in result['costs']:
        row.update(metadata[row['case']])
        if row['metric']=='worker_wall_seconds':
            row['phase']='driver_launch_and_receipt_checks'
    # Reuse the accepted gap identity and close-design classification code.
    decision_rows=[dict(r,shape=r['scenario'],contract=reg['memory_policy']) for r in result['rows']]
    decisions=decision_table(decision_rows,dict(reg,cases=sorted(reg['scenarios'],key=lambda s:(len(s),s)),contracts=[reg['memory_policy']]))
    for row in decisions: row['scenario']=row.pop('shape')
    interference=[]; shared=[]; pairs=[]
    for placement in reg['placements']:
        for mode in reg['modes']:
            joint=events['AB',placement,mode]; jr=joint['result']
            totals=[]
            for group in ('A','B'):
                solo=events[group,placement,mode]; sr=solo['result']
                st=group_times(sr,group); jt=group_times(jr,group)
                interference.append(dict(placement=placement,mode=mode,group=group,
                    solo_output_ready=st['output_ready'],joint_output_ready=jt['output_ready'],
                    output_delay_cycles=jt['output_ready']-st['output_ready'],
                    solo_retired=st['retired'],joint_retired=jt['retired'],
                    retirement_delay_cycles=jt['retired']-st['retired'],
                    output_slowdown=jt['output_ready']/st['output_ready'],**progress_changes(sr,jr,group)))
                jm={k:v for k,v in joint['moves'].items() if k.startswith(group+'/')}
                if set(jm)!=set(solo['moves']): raise ValueError('Joint run changed logical messages')
                for token,s in solo['moves'].items():
                    j=jm[token]
                    if any(s[k]!=j[k] for k in ('source','destination','bytes')): raise ValueError('Changed transfer work')
                    observation={label+'_'+k:v for label,source in (('solo',solo),('joint',joint))
                        for k,v in source['observations'][token].items()}
                    pairs.append(dict(placement=placement,mode=mode,group=group,token=token,bytes=s['bytes'],
                        solo_ready=s['ready'],joint_ready=j['ready'],solo_commit=s['commit'],joint_commit=j['commit'],
                        absolute_commit_change=j['commit']-s['commit'],
                        solo_service=s['commit']-s['ready'],joint_service=j['commit']-j['ready'],
                        service_change=(j['commit']-j['ready'])-(s['commit']-s['ready']),
                        solo_supply_span=s['last_supply']-s['first_supply'],joint_supply_span=j['last_supply']-j['first_supply'],
                        solo_receive_tail=s['last_receive']-s['first_supply'],joint_receive_tail=j['last_receive']-j['first_supply'],
                        solo_commit_tail=s['commit']-s['last_receive'],joint_commit_tail=j['commit']-j['last_receive'],
                        path_counts_changed=solo['observations'][token]['paths']!=joint['observations'][token]['paths'],
                        **observation))
                totals.append(dict(bytes=sum(m['bytes'] for m in sr['network_messages']),
                    flits=sum(m['expected_flits'] for m in sr['network_messages']),
                    memory=sum(s['amount'] for s in sr['services'] if s['category']=='memory')))
            for field,observed in dict(bytes=sum(m['bytes'] for m in jr['network_messages']),
                flits=sum(m['expected_flits'] for m in jr['network_messages']),
                memory=sum(s['amount'] for s in jr['services'] if s['category']=='memory')).items():
                if observed!=sum(t[field] for t in totals): raise ValueError('Combined work not conserved: '+field)
            shared.append(dict(placement=placement,mode=mode,**shared_paths(jr['network_messages'])))
    result.update(decision_table=decisions,group_interference=interference,shared_resources=shared,paired_messages=pairs)
    result['acceptance'].update(full_repetitions_identical=True,exact_solo_projections=True,
        joint_work_conserved=True,baseline_compatibility=read_json(root/'COMPATIBILITY.json'),
        registered_cells=len(expected)//reg['repetitions'])
    return result


def plot(result, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=result['decision_table']; fig,ax=plt.subplots(figsize=(7,4),layout='constrained')
    for i,mode in enumerate(('serial','bounded')):
        ax.bar([j+(i-.5)*.3 for j in range(len(rows))],[r[mode+'_gap_cycles'] for r in rows],.3,label=mode)
    ax.axhspan(-100,100,color='grey',alpha=.15,label='100-cycle indifference band')
    ax.axhline(0,color='black',linewidth=.5); ax.set_ylabel('Baseline - Rotated (cycles)')
    ax.set_xticks(range(len(rows)),[r['scenario'] for r in rows]); ax.legend()
    fig.savefig(output/'design_gap.png',dpi=160); plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,place in zip(axes,('baseline','ours_rotated')):
        for i,mode in enumerate(('serial','bounded')):
            vals=[next(c for c in result['costs'] if c['scenario']==s and c['placement']==place and
                c['mode']==mode and c['phase']=='execution' and c['metric']=='wall_seconds') for s in ('A','B','AB')]
            ax.bar([j+(i-.5)*.3 for j in range(3)],[v['median'] for v in vals],.3,label=mode,
                yerr=[[v['median']-v['minimum'] for v in vals],[v['maximum']-v['median'] for v in vals]],capsize=2)
        ax.set_title(place); ax.set_xticks(range(3),['A','B','AB']); ax.set_ylabel('Execution seconds (median/range, 3 cold runs)'); ax.legend()
    fig.savefig(output/'execution_cost.png',dpi=160); plt.close(fig)
