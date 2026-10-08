"""Design-difference prediction and explicit public validity states."""
from pathlib import Path

from wafer_sim.analysis.boundary_study import analyze as analyze_boundary, movement_rows
from wafer_sim.io import read_json, object_digest


def public_status(row):
    """Audit success does not imply capacity feasibility or hardware calibration."""
    feasible = row['capacity_feasible']
    return dict(execution_completed=True, semantic_audit_passed=True,
        capacity_status='unmodeled' if feasible is None else ('feasible' if feasible else 'violated'),
        reference_agreement='reference' if row['mode']=='bounded' else (
            'within_registered_targets' if row['application_target_met'] and row['message_target_met']
            else 'outside_registered_targets'),
        hardware_calibration_status='uncalibrated_local_resources')


def design_choice(gap, band):
    return 'approximately_equal' if abs(gap)<=band else ('ours_rotated' if gap>0 else 'baseline')


def decision_table(rows, registration):
    index={}
    for row in rows:
        key=row['shape'],row['contract'],row['placement'],row['mode']
        if key in index:raise ValueError('Duplicate design cell')
        index[key]=row
    expected={(s,q,p,m) for s in registration['cases'] for q in registration['contracts']
              for p in registration['placements'] for m in registration['modes']}
    if set(index)!=expected:raise ValueError('Incomplete design matrix')
    output=[]
    for shape in registration['cases']:
        for policy in registration['contracts']:
            ref=index[shape,policy,'baseline','bounded']['application_cycles']-index[shape,policy,'ours_rotated','bounded']['application_cycles']
            row=dict(shape=shape,memory_policy=policy,reference_gap_cycles=ref,
                reference_choice=design_choice(ref,registration['design_indifference_cycles']))
            for model in registration['modes']:
                b=index[shape,policy,'baseline',model];r=index[shape,policy,'ours_rotated',model]
                gap=b['application_cycles']-r['application_cycles']
                if gap-ref!=b['error_cycles']-r['error_cycles']:
                    raise ValueError('Gap-error identity violated')
                row.update({model+'_baseline_cycles':b['application_cycles'],
                    model+'_rotated_cycles':r['application_cycles'],model+'_gap_cycles':gap,
                    model+'_gap_error_cycles':gap-ref,
                    model+'_gap_target_met':abs(gap-ref)<=registration['gap_tolerance_cycles'],
                    model+'_raw_order_agrees':(gap>0)-(gap<0)==(ref>0)-(ref<0),
                    model+'_choice':design_choice(gap,registration['design_indifference_cycles']),
                    model+'_baseline_capacity':public_status(b)['capacity_status'],
                    model+'_rotated_capacity':public_status(r)['capacity_status']})
            output.append(row)
    return output


def pair_messages(rows, registration):
    """Pair logical identities across placements; durations are not causal shares."""
    index={(r['shape'],r['contract'],r['mode'],r['placement'],r['token']):r for r in rows}
    if len(index)!=len(rows):raise ValueError('Duplicate attribution message')
    output=[]
    for shape in registration['cases']:
        for policy in registration['contracts']:
            tokens={k[4] for k in index if k[:4]==(shape,policy,'bounded','baseline')}
            for mode in registration['modes']:
                for place in registration['placements']:
                    if {k[4] for k in index if k[:4]==(shape,policy,mode,place)}!=tokens:
                        raise ValueError('Missing logical messages across designs')
                for token in sorted(tokens):
                    b=index[shape,policy,mode,'baseline',token];r=index[shape,policy,mode,'ours_rotated',token]
                    rb=index[shape,policy,'bounded','baseline',token];rr=index[shape,policy,'bounded','ours_rotated',token]
                    if len({x['bytes'] for x in (b,r,rb,rr)})!=1:raise ValueError('Changed paired payload')
                    service=lambda x:x['commit']-x['ready']
                    out=dict(shape=shape,contract=policy,mode=mode,token=token,bytes=b['bytes'],
                        baseline_service=service(b),rotated_service=service(r),
                        reference_service_gap=service(rb)-service(rr),
                        service_gap_error=(service(b)-service(r))-(service(rb)-service(rr)),
                        any_observed_critical=any(x['on_observed_critical_chain'] for x in (b,r,rb,rr)))
                    for label,x in (('baseline',b),('rotated',r)):
                        out.update({label+'_'+k:x[k] for k in ('ready','commit','source_memory_queue',
                            'destination_memory_queue','source_memory_service','destination_memory_service','paths')})
                    output.append(out)
    return output


def analyze(root):
    root=Path(root);result=analyze_boundary(root)
    reg=result['acceptance']['registration']['design_study']
    launches=read_json(root/'LAUNCHES.json');seen=set();metadata={};logical={};local_resources=None;attribution=[]
    for launch in launches:
        shape,policy,placement=launch['shape'],launch['contract'],launch['placement']
        mode,repeat=launch['mode'],launch['repeat'];case=launch['case'];directory=Path(launch['worker'])
        if case!='__'.join((shape,policy,placement)) or directory.resolve()!=(root/case/f'{mode}-{repeat}').resolve():
            raise ValueError('Worker outside declared cell')
        key=shape,policy,placement,mode,repeat
        if key in seen:raise ValueError('Repeated launch')
        seen.add(key);metadata[case]=dict(shape=shape,contract=policy,placement=placement)
        identity=read_json(directory/'INPUT.json')
        quantum=None if policy=='request_atomic' else 256
        if identity.get('memory_quantum_bytes')!=quantum or identity['boundary_contract']['placement']!=placement:
            raise ValueError('Changed target service policy or placement label')
        local=object_digest(identity['resource_contract']['compute_memory_parameters'])
        if local_resources is not None and local_resources!=local:raise ValueError('Changed local resource budget')
        local_resources=local
        digest=object_digest({k:identity[k] for k in ('logical_workload','tensors','operators','collectives','execution_policy')})
        if shape in logical and logical[shape]!=digest:raise ValueError('Changed logical work across models/designs')
        logical[shape]=digest
        if repeat==0:
            recorded=read_json(directory/'execution.json')
            origins=read_json(directory/'PHASE_MAP.json')
            moves=movement_rows(recorded,origins)
            chain=read_json(directory/'critical_chain.json')
            critical={s.get('token') for s in chain['segments']}
            for msg in recorded['network_messages']:
                token=msg['token'];op,phase=token.rsplit('/phase/',1)
                canonical=token if mode=='serial' else f"{op}/phase/{origins[op][phase]['transfer']}"
                row=moves[canonical];services=recorded['services']
                if mode=='serial':
                    read_token=f'{op}/phase/{int(phase)-1}';write_token=f'{op}/phase/{int(phase)+1}'
                    read=[s for s in services if s['token']==read_token]
                    write=[s for s in services if s['token']==write_token]
                else:
                    read=[s for s in services if s['token'].startswith(token+'/read/')]
                    write=[s for s in services if s['token'].startswith(token+'/write/')]
                attribution.append(dict(case=case,**metadata[case],mode=mode,token=canonical,**row,
                    source_memory_queue=sum(s['start']-s['ready'] for s in read),
                    destination_memory_queue=sum(s['start']-s['ready'] for s in write),
                    source_memory_service=sum(s['resource_released']-s['start'] for s in read),
                    destination_memory_service=sum(s['resource_released']-s['start'] for s in write),
                    first_inject=msg['first_inject'],last_inject=msg['last_inject'],
                    paths=sorted({tuple(f['router_path']) for f in msg['flits']}),
                    on_observed_critical_chain=bool(critical.intersection(
                        (token,read_token,write_token) if mode=='serial' else (token,)))))
    expected={(s,q,p,m,r) for s in reg['cases'] for q in reg['contracts'] for p in reg['placements']
              for m in reg['modes'] for r in range(reg['repetitions'])}
    if seen!=expected:raise ValueError('Incomplete declared repetitions')
    for group in ('rows','messages','costs','source_windows'):
        for row in result[group]:row.update(metadata[row['case']])
    for row in result['rows']:row.update(public_status(row))
    result['decision_table']=decision_table(result['rows'],reg)
    result['attribution']=attribution
    result['paired_messages']=pair_messages(attribution,reg)
    result['acceptance']['matrix_complete']=True
    result['acceptance']['baseline_compatibility']=read_json(root/'COMPATIBILITY.json')
    return result
