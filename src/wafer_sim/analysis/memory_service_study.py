"""Readback of a factorial policy intervention, not overlap-only attribution."""
from collections import defaultdict
from pathlib import Path

from wafer_sim.analysis.boundary_study import analyze as analyze_boundary
from wafer_sim.io import read_json, object_digest


def analyze(root):
    root=Path(root);result=analyze_boundary(root)
    reg=result['acceptance']['registration']['isolation'];by_shape=defaultdict(list)
    contracts={c['name']:c['memory_quantum_bytes'] for c in reg['contracts']}
    seen=set();reference_identity={}
    for launch in read_json(root/'LAUNCHES.json'):
        case=launch['case'];shape=launch['shape'];contract=launch['contract'];mode=launch['mode']
        if case!=shape+'__'+contract or shape not in reg['cases'] or mode not in reg['modes']:
            raise ValueError('Unregistered cell')
        directory=Path(launch['worker']);observed=read_json(directory/'execution.json')
        if observed['policy'].get('memory_quantum_bytes')!=contracts[contract]:
            raise ValueError('Memory policy differs from registration')
        identity=read_json(directory/'INPUT.json');identity.pop('memory_quantum_bytes',None)
        h=object_digest(identity)
        if shape in reference_identity and reference_identity[shape]!=h:
            raise ValueError('Different work/hardware across memory contracts')
        reference_identity[shape]=h
        key=shape,contract,mode,launch['repeat']
        if key in seen:raise ValueError('Duplicate execution')
        seen.add(key)
        if contract=='request_atomic':
            old=read_json(Path(reg['accepted_run'])/shape/(mode+'-0')/'execution.json')
            if object_digest(observed)!=object_digest(old):raise ValueError('Compatibility event mismatch')
    expected={(s,c,m,r) for s in reg['cases'] for c in contracts for m in reg['modes'] for r in range(reg['repetitions'])}
    if seen!=expected:raise ValueError('Incomplete matrix')
    for group in ('rows','messages','costs','source_windows'):
        for row in result[group]:
            row['shape'],row['memory_contract']=row['case'].split('__')
    interactions=[]
    for shape in reg['cases']:
        rows={(r['memory_contract'],r['mode']):r for r in result['rows'] if r['shape']==shape}
        if len({(r['memory_bytes'],r['logical_network_bytes'],r['network_flits']) for r in rows.values()})!=1:
            raise ValueError('Logical work changed across policies')
        def t(c,m):return rows[c,m]['application_cycles']
        ga=t('request_atomic','pipeline')-t('request_atomic','serial')
        gb=t('burst_256','pipeline')-t('burst_256','serial')
        interactions.append(dict(shape=shape,atomic_boundary_gap=ga,burst_boundary_gap=gb,
            interaction_cycles=gb-ga,
            atomic_feedback=t('request_atomic','bounded')-t('request_atomic','pipeline'),
            burst_feedback=t('burst_256','bounded')-t('burst_256','pipeline'),
            serial_policy_change=t('burst_256','serial')-t('request_atomic','serial'),
            pipeline_policy_change=t('burst_256','pipeline')-t('request_atomic','pipeline'),
            bounded_policy_change=t('burst_256','bounded')-t('request_atomic','bounded')))
    result['interactions']=interactions
    result['acceptance']['matrix_complete']=True
    result['acceptance']['exact_accepted_events']=read_json(root/'COMPATIBILITY.json')
    result['scope']='Fixed declared WoW network; memory-policy sensitivity and boundary-model interaction, not pure overlap effect or calibrated hardware accuracy'
    return result
