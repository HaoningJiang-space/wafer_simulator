"""Compare independent G1 predictions with raw Native evidence, no lowering."""
from collections import Counter
import json
from wafer_sim.architecture.causal_merge import validate, PORTS, FORWARD


def read_observation(path):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if (not rows or rows[0].get('kind')!='begin' or rows[0].get('schema')!=3 or
            rows[-1].get('kind')!='end' or not rows[-1].get('complete') or
            rows[-1]['rows_before_end']!=len(rows)-1):
        raise ValueError('Incomplete causal observation')
    return rows


def compare(contract, prediction, native, observations):
    c=validate(contract)
    if not prediction['complete'] or not prediction['drained'] or not native['complete'] or not native['final']['drained']:
        raise ValueError('Incomplete network evidence')
    if prediction['native_boundary_inputs']: raise ValueError('Native boundary leakage')
    contract_rows=[r for r in observations if r['kind']=='contract']
    contracts={r['router']:r for r in contract_rows}
    if len(contracts)!=len(contract_rows): raise ValueError('Repeated observed contract')
    visited={e['router'] for e in prediction['service']}
    if set(contracts)!=visited: raise ValueError('Missing/duplicate observed contract')
    for router,r in contracts.items():
        expected=dict(input_count=len(PORTS[router]),output=FORWARD[router],crossbar_delay=c['crossbar_delay'],
            channel_latency=c['endpoint_link_latency'] if router==3 else c['router_link_latency'],
            downstream_capacity=c['capacity_flits'],vc_busy_when_full=False,output_buffer_limit=-1,
            routing_delay=0,vc_alloc_delay=1,sw_alloc_delay=1)
        if any(r[k]!=v for k,v in expected.items()): raise ValueError('Different Native service contract')
    errors=[]; checked=Counter()
    def eq(kind,key,a,b):
        checked[kind]+=1
        if a!=b: errors.append(dict(kind=kind,identity=key,expected=a,native=b))
    messages={r['id']:r for r in native['messages']}
    if len(messages)!=len(native['messages']): raise ValueError('Repeated Native message')
    if set(messages)!={r['id'] for r in prediction['messages']}: raise ValueError('Different message inventory')
    message_fields=('source','destination','ready','generated','first_inject','last_inject','first_eject','last_eject','finish')
    flit_fields=('message','source','destination','generated','injected','ejected','hops','router_path','injection_router_arrival','link_arrivals')
    total_flits=0
    for p in prediction['messages']:
        n=messages[p['id']]
        for k in message_fields: eq('message_fields',f"{p['id']}/{k}",p[k],n[k])
        nf={f['id']:f for f in n['flits']}; pf={f['id']:f for f in p['flits']}
        if len(nf)!=len(n['flits']): raise ValueError('Repeated Native flit')
        if set(nf)!=set(pf): raise ValueError('Different generated flit inventory')
        total_flits+=len(pf)
        for fid,f in pf.items():
            for k in flit_fields: eq('flit_fields',f'{fid}/{k}',f[k],nf[fid][k])
    eq('drain_clock','final',prediction['final_cycle'],native['final']['cycle'])
    # Each comparison target is independently indexed from raw observation;
    # a stored derived boundary/summary is not an authoritative target.
    kinds=('vc_commit','sw_commit','output_send')
    expected={(e['kind'],e['router'],e['flit']):e for e in prediction['service']}
    actual={}
    for r in observations:
        if r['kind'] in kinds:
            key=(r['kind'],r['router'],r['flit'])
            if key in actual: raise ValueError('Repeated local service evidence')
            actual[key]=r
    if set(expected)!=set(actual): raise ValueError('Missing/unmatched local service')
    for key,p in expected.items():
        n=actual[key];eq('service_clocks',str(key),p['cycle'],n['cycle'])
        if p['kind']!='output_send': eq('service_input_identity',str(key),p['input'],n['input'])
    def credit_counts(rows, fields):
        return Counter({})+Counter(tuple(r[k] for k in fields) for r in rows for _ in range(r['amount']))
    p_returns=credit_counts(prediction['credit_returns'],('target','number','cycle'))
    nr=[dict(target='router',number=r['router'],cycle=r['cycle'],amount=r['amount']) for r in observations if r['kind']=='credit_return']
    nr += [dict(target='endpoint',number=r['endpoint'],cycle=r['cycle'],amount=r['amount']) for r in observations if r['kind']=='endpoint_credit']
    n_returns=credit_counts(nr,('target','number','cycle'))
    eq('credit_return_sequence','all',sorted(p_returns.items()),sorted(n_returns.items()))
    p_sends=credit_counts(prediction['credit_sends'],('router','input','cycle'))
    n_sends=credit_counts([r for r in observations if r['kind']=='credit_send'],('router','input','cycle'))
    eq('credit_send_sequence','all',sorted(p_sends.items()),sorted(n_sends.items()))
    points={(p['router'],p['cycle']):p for p in prediction['allocations']}
    required_calls=set()
    for key,p in points.items():
        if any(f>=0 and i!=p['owner'] for i,f in enumerate(p['heads'])): required_calls.add((*key,'vc'))
        if p['owner'] is not None: required_calls.add((*key,'sw'))
    for kind in ('allocate_pre','allocate_post'):
        calls=[(r['router'],r['cycle'],r['stage']) for r in observations if r['kind']==kind]
        if len(calls)!=len(set(calls)): raise ValueError('Repeated allocation snapshot')
        eq('allocation_call_inventory',kind,sorted(required_calls),sorted(calls))
    for r in observations:
        if r['kind'] not in ('allocate_pre','allocate_post'):continue
        key=(r['router'],r['cycle']);stage=r['stage'];p=points.get(key)
        if p is None: errors.append(dict(kind='missing_predicted_allocation',identity=key));continue
        if r['input_count']!=len(PORTS[r['router']]) or any(i['other_output_requests'] for i in r['inputs']):
            raise ValueError('Unsupported cross-output allocation')
        requests=p[stage+'_requests'];pointer=p[stage+'_pointer']
        grant=min(requests,key=lambda i:(i-pointer)%r['input_count']) if requests else -1
        if r['kind']=='allocate_pre':
            eq('allocation_requests',str((key,stage)),requests,[i['input'] for i in r['inputs'] if i['requested']])
            eq('allocation_pointer',str((key,stage)),pointer,r['grant_pointer'])
            eq('vc_owner',str((key,stage)),p['owner'],None if r['vc_owner']<0 else r['vc_owner'])
            eq('credit_balance',str((key,stage)),p['credit_slots'],r['credit_slots'])
            for inp in r['inputs']:
                i=inp['input'];eq('fifo_occupancy',str((key,i,stage)),p['occupancy'][i],inp['occupancy'])
                eq('fifo_head',str((key,i,stage)),p['heads'][i],inp['head_flit'])
                peer=PORTS[r['router']][i];kind,number=peer.split('/')
                if inp['upstream_router']!=(int(number) if kind=='router' else -1) or inp['upstream_endpoint']!=(int(number) if kind=='endpoint' else -1):
                    raise ValueError('Wrong observed physical attachment')
        else:
            eq('allocation_grant',str((key,stage)),grant,r['grant_input'])
            eq('allocation_next_pointer',str((key,stage)),(grant+1)%r['input_count'] if grant>=0 else pointer,r['grant_pointer'])
    return dict(passed=not errors,mismatches=len(errors),first_discrepancies=errors[:12],checks=dict(checked),
        messages=len(messages),flits=total_flits,local_services=len(expected),native_boundary_inputs=False,
        credit_returns=sum(p_returns.values()),credit_sends=sum(p_sends.values()),
        source_stall_cycles=prediction['source_stall_cycles'],router_credit_stall_cycles=prediction['router_credit_stall_cycles'],
        predicted_finishes=[p['finish'] for p in prediction['messages']],
        native_finishes=[messages[p['id']]['finish'] for p in prediction['messages']],
        scope='Independent four-router causal closure, no compression/application claim')


def analyze(root, output):
    """Fresh authenticated readback; regenerate predictions from external input."""
    from pathlib import Path
    import subprocess
    from wafer_sim.adapters.causal_merge import simulate
    from wafer_sim.io import read_json,write_json,digest,object_digest
    repo=Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute readback required')
    manifest=read_json(root/'COMPLETE.json')
    if not manifest['complete'] or (root/'FAILED.json').exists(): raise ValueError('Incomplete campaign')
    for name,expected in manifest['artifacts_sha256'].items():
        if digest(root/name)!=expected: raise ValueError('Changed campaign artifact: '+name)
    start=read_json(root/'STARTED.json')
    for name,expected in start['source_hashes'].items():
        if digest(repo/name)!=expected: raise ValueError('Changed predictor/observer/comparator source: '+name)
    reg=read_json(repo/'configs/causal_closure.json')
    if digest(repo/'configs/causal_closure.json')!=start['registration_sha256']: raise ValueError('Changed registered contract')
    summary=read_json(root/'SUMMARY.json');rows=[]
    if [r['name'] for r in summary['rows']]!=[c['name'] for c in reg['cases']]: raise ValueError('Missing/duplicated cases')
    for case,stored in zip(reg['cases'],summary['rows']):
        directory=root/case['name'];c=dict(reg['contract'],capacity_flits=case.get('capacity_flits',reg['contract']['capacity_flits']))
        expected_input=dict(contract=c,messages=case['messages'])
        if read_json(directory/'INPUT.json')!=expected_input: raise ValueError('Changed external demand/contract')
        prediction=simulate(c,case['messages'],reg['cycle_limit'])
        if object_digest(prediction)!=object_digest(read_json(directory/'PREDICTION.json')): raise ValueError('Stored prediction differs from independent regeneration')
        observed=read_json(directory/'observed/NETWORK_RESULT.json');reference=read_json(directory/'reference/NETWORK_RESULT.json')
        if (object_digest(reference['messages'])!=object_digest(observed['messages']) or reference['final']!=observed['final'] or
                digest(directory/'reference/online_protocol.jsonl')!=digest(directory/'observed/online_protocol.jsonl')):
            raise ValueError('Observer changed complete Native events/protocol')
        checked=compare(c,prediction,observed,read_observation(directory/'observed/OBSERVATION.jsonl'))
        checked.update(name=case['name'],capacity_flits=c['capacity_flits'],exact_observer_events=True,
                       input_sha256=digest(directory/'INPUT.json'),prediction_sha256=digest(directory/'PREDICTION.json'))
        if checked!=stored or checked!=read_json(directory/'CHECKED.json'): raise ValueError('Stored comparison differs from raw evidence')
        rows.append(checked)
    passed=all(r['passed'] for r in rows)
    if summary['g1_accuracy_passed']!=passed or manifest['accuracy_passed']!=passed: raise ValueError('Incorrect accuracy status')
    output.mkdir();write_json(output/'RESULTS.json',dict(rows=rows,g1_accuracy_passed=passed,native_executions=2*len(rows),
        application_executions=0,independent_prediction=True,compression_implemented=False))
    write_json(output/'VERIFIED.json',dict(readback_passed=True,g1_accuracy_passed=passed,
        source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        campaign_manifest_sha256=digest(root/'COMPLETE.json'),observation_source_commit=start['source_commit'],
        artifacts_checked=len(manifest['artifacts_sha256']),result_sha256=digest(output/'RESULTS.json')))


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();analyze(args.campaign,args.output)
