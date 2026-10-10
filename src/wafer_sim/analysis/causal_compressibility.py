"""Inspect recurring causal state without changing the pinned G1 transitions."""
import hashlib
import inspect
import json
import sys
from wafer_sim.adapters.causal_merge import simulate


def encoded(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'))


def sha(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


class BoundaryObserver:
    """Read frame state once per cycle; never advance or mutate the solver."""
    def __init__(self):
        lines, first = inspect.getsourcelines(simulate)
        matches=[first+i for i,line in enumerate(lines) if line.strip()=='for event in future.pop(now, []):']
        if len(matches)!=1: raise ValueError('Unrecognized G1 boundary')
        self.line=matches[0];self.rows=[];self.first_flits={};self.last_cycle=-1

    def trace(self, frame, event, arg):
        if frame.f_code is not simulate.__code__: return None
        if event=='line' and frame.f_lineno==self.line and frame.f_locals['now']!=self.last_cycle:
            self.capture(frame.f_locals)
        return self.trace

    def capture(self, local):
        now=local['now'];self.last_cycle=now
        demand=local['demand'];work=local['work'];generated=local['generated']
        for mid in generated:
            if mid not in self.first_flits:
                self.first_flits[mid]=min(f for f,w in work.items() if w['message']==mid)
        injected=[len(local['injections'].get(m['id'],())) for m in demand]
        ejected=[len(local['ejections'].get(m['id'],())) for m in demand]
        active=set()
        def token(f):
            active.add(f)
            mid=work[f]['message']
            return [mid,f-self.first_flits[mid]-injected[mid]]
        states=[]
        for s in local['states']:
            states.append(dict(queues=[[token(f) for f in q] for q in s['queues']],
                owner=s['owner'],sw_ready_in=None if s['sw_ready'] is None else max(0,s['sw_ready']-now),
                credit=s['credit'],vc_pointer=s['vc_pointer'],sw_pointer=s['sw_pointer']))
        issuing=[]
        for queue in local['issuing']:
            if queue:
                if queue[-1]-queue[0]+1!=len(queue) or work[queue[0]]['message']!=work[queue[-1]]['message']:
                    raise ValueError('Non-homogeneous source suffix')
                issuing.append(token(queue[0]))
            else: issuing.append(None)
        future=[]
        for when,events in sorted(local['future'].items()):
            if when<now: raise ValueError('Overdue unprocessed event')
            normalized=[]
            for event in events:
                row=dict(event)
                if 'flit' in row: row['flit']=token(row['flit'])
                normalized.append(row)
            # Preserve same-clock insertion order, not only the multiset.
            future.append([when-now,normalized])
        remaining=[[m['flits']-injected[m['id']],m['flits']-ejected[m['id']]] for m in demand]
        live_work=[]
        for f in sorted(active,key=token):
            metadata=json.loads(encoded(work[f]));metadata.pop('id')
            for field in ('injected','ejected','injection_router_arrival'):
                if field in metadata: metadata[field]-=now
            for arrival in metadata['link_arrivals']: arrival['cycle']-=now
            live_work.append([token(f),metadata])
        kernel=dict(routers=states,source_credits=list(local['source_credits']),issuing=issuing,
            todo=[[[max(0,ready-now),mid] for ready,mid in queue] for queue in local['todo']],
            future=future,completed=[left[1]==0 for left in remaining],next_flit=local['next_flit'],
            epochs=[[mid,generated[mid],self.first_flits[mid]] for mid in sorted(generated)],live_work=live_work)
        cursors={name:len(local[name]) for name in ('service','inputs','credits','credit_sends','allocations')}
        progress=(injected+ejected+list(local['source_stalls'])+list(local['router_stalls'])+
            [cursors[name] for name in cursors]+[v for q in local['queue_peaks'] for v in q])
        self.rows.append(dict(cycle=now,kernel=kernel,remaining=remaining,anchors=injected,
            ejected=ejected,cursors=cursors,progress=progress,
            cycle_budget=local['cycle_limit']-now,
            steady_epoch=len(generated)==len(demand) and not any(local['todo'])))


def observe(contract, messages, limit):
    if sys.gettrace() is not None: raise ValueError('Existing Python trace hook')
    observer=BoundaryObserver()
    sys.settrace(observer.trace)
    try: result=simulate(contract,messages,limit)
    finally: sys.settrace(None)
    if len(observer.rows)!=result['final_cycle']: raise ValueError('Missing cycle boundaries')
    return result,observer


def period_output(result,observer,start,end):
    """Ordered emitted boundaries; normalize clocks and per-message flit IDs."""
    if not hasattr(observer,'work_index'):
        observer.work_index={f['id']:f for m in result['messages'] for f in m['flits']}
        observer.sorted_flits={(m['id'],field):sorted(m['flits'],key=lambda f:(f[field],f['id']))
            for m in result['messages'] for field in ('injected','ejected')}
    work=observer.work_index
    def token(f):
        mid=work[f]['message']
        return [mid,f-observer.first_flits[mid]-start['anchors'][mid]]
    output={}
    for key,cursor in [('service','service'),('input_arrivals','inputs'),('credit_returns','credits'),
                       ('credit_sends','credit_sends'),('allocations','allocations')]:
        rows=[]
        for event in result[key][start['cursors'][cursor]:end['cursors'][cursor]]:
            row=dict(event);row['cycle']-=start['cycle']
            if 'flit' in row: row['flit']=token(row['flit'])
            if 'heads' in row: row['heads']=[token(f) if f>=0 else None for f in row['heads']]
            rows.append(row)
        output[key]=rows
    output['injections']=[];output['ejections']=[]
    for message in result['messages']:
        mid=message['id']
        for field,key,left,right in [('injected','injections',start['anchors'][mid],end['anchors'][mid]),
                                     ('ejected','ejections',start['ejected'][mid],end['ejected'][mid])]:
            flits=observer.sorted_flits[(mid,field)]
            output[key].append([[token(f['id']),f[field]-start['cycle']] for f in flits[left:right]])
    return encoded(output)


def intervals_union(intervals):
    merged=[]
    for start,end in sorted(intervals):
        if merged and start<=merged[-1][1]: merged[-1][1]=max(end,merged[-1][1])
        else: merged.append([start,end])
    return merged


def audit_patterns(result,observer,minimum=3):
    """Find repeated *parametric* states and verify every observed period output.

    Pending homogeneous suffix lengths and destination remaining counts stay
    explicit. They are bounds, not equal state. This is an observed opportunity,
    not a proof that an unexecuted batch is correct.
    """
    rows=observer.rows;last={};chains={};finished=[];strict=set();strict_repeats=0;busy=set()
    service_cycles={e['cycle'] for e in result['service']}
    # Summarize ordered router/input service separately from full-state repeats.
    output_trace=[(e['cycle'],e['router'],e.get('input',-1)) for e in result['service'] if e['kind']=='sw_commit']
    for row in rows:
        key=encoded(row['kernel']);strict_key=encoded([row['kernel'],row['remaining']])
        if strict_key in strict: strict_repeats+=1
        strict.add(strict_key)
        if row['cycle'] in service_cycles: busy.add(row['cycle'])
        prior=last.get(key);last[key]=row
        if not row['steady_epoch'] or prior is None or not prior['steady_epoch']: continue
        period=row['cycle']-prior['cycle'];delta=[b-a for a,b in zip(prior['progress'],row['progress'])]
        output=period_output(result,observer,prior,row)
        chain=chains.get(key)
        if chain and chain['end']==prior['cycle'] and chain['period']==period and chain['delta']==delta and chain['_output']==output:
            chain['end']=row['cycle'];chain['repetitions']+=1
        else:
            if chain: finished.append(chain)
            chain=dict(start=prior['cycle'],end=row['cycle'],period=period,repetitions=1,delta=delta,
                kernel_sha256=hashlib.sha256(key.encode()).hexdigest(),output_sha256=hashlib.sha256(output.encode()).hexdigest(),
                _output=output,remaining_at_start=prior['remaining'],remaining_at_end=row['remaining'])
            chains[key]=chain
        chain['remaining_at_end']=row['remaining']
    finished.extend(chains.values())
    eligible=[]
    for chain in finished:
        if chain['repetitions']<minimum: continue
        n=len(chain['remaining_at_end']);consumption=chain['delta'][:2*n]
        if not any(consumption): continue  # Never advertise idle repetition.
        limits=[]
        for mid,left in enumerate(chain['remaining_at_end']):
            for pos in range(2):
                step=consumption[mid+pos*n]
                if step>0: limits.append(max(0,(left[pos]-1)//step))
        tail_bound=min(limits) if limits else 0
        chain['additional_periods_before_tail_or_timeout_bound']=min(tail_bound,(rows[chain['end']]['cycle_budget']-1)//chain['period'])
        chain['busy_service_cycles']=sum(chain['start']<=t<chain['end'] for t in busy)
        chain.pop('_output');eligible.append(chain)
    coverage=intervals_union([(c['start'],c['end']) for c in eligible])
    busy_covered=sum(any(a<=t<b for a,b in coverage) for t in busy)
    representatives=[]
    for c in sorted(eligible,key=lambda c:c['end']-c['start'],reverse=True):
        if any(r['start']<=c['start'] and c['end']<=r['end'] and r['period']==c['period'] for r in representatives): continue
        representatives.append(c)
    return dict(processed_cycles=result['processed_cycles'],strict_normalized_state_repeats=strict_repeats,
        parametric_pattern_chains=len(eligible),observed_coverage=coverage,
        observed_covered_cycles=sum(b-a for a,b in coverage),busy_service_cycles=len(busy),
        busy_service_cycles_covered=busy_covered,representative_chains=representatives[:12],
        output_trace_sha256=sha(output_trace),skipped_cycles=0,compression_implemented=False,
        interpretation='Repeated complete causal kernels with explicit finite-work bounds; observed periods verified, no batching proof or speedup')
