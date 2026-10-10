"""Independent G2.1 checks against unmodified G1, after candidate execution."""
import sys
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.analysis.causal_compressibility import BoundaryObserver
from wafer_sim.io import object_digest


def reference_boundaries(contract,messages,limit,cycles):
    if sys.gettrace() is not None:raise ValueError('Existing trace hook')
    observer=BoundaryObserver();wanted=set(cycles)
    def trace(frame,event,arg):
        if frame.f_code is not simulate.__code__:return None
        if event=='line' and frame.f_lineno==observer.line:
            now=frame.f_locals['now']
            if now in wanted:
                observer.capture(frame.f_locals);wanted.remove(now)
        return trace
    sys.settrace(trace)
    try:result=simulate(contract,messages,limit)
    finally:sys.settrace(None)
    if wanted:raise ValueError('Missing reference macro boundary')
    return result,{r['cycle']:r for r in observer.rows}


def check_checkpoints(checkpoints,reference):
    seen=set()
    for row in checkpoints:
        if row['role'] not in ('entry','exit'):raise ValueError('Unknown macro checkpoint')
        state=row['state'];identity=(row['role'],state['cycle'])
        if identity in seen:raise ValueError('Repeated macro checkpoint')
        seen.add(identity)
        if state!=reference.get(state['cycle']):raise ValueError('Macro boundary state differs at '+str(identity))
    if len(checkpoints)%2 or [r['role'] for r in checkpoints]!=['entry','exit']*(len(checkpoints)//2):
        raise ValueError('Incomplete macro boundary pair')


def check_run(run,reference,boundaries):
    expanded=run.expand()
    if expanded!=reference:raise ValueError('Expanded complete prediction differs from G1')
    metrics=run.metrics();check_checkpoints(metrics['checkpoints'],boundaries)
    if len(metrics['checkpoints'])!=2*metrics['macros']:raise ValueError('Missing macro end-state verification')
    if metrics['physical_cycle_updates']+metrics['skipped_cycles']!=reference['final_cycle']:
        raise ValueError('Incorrect physical/logical progress')
    if sum(b['end']-b['start'] for b in metrics['batches'])!=metrics['skipped_cycles']:
        raise ValueError('Incorrect macro coverage')
    for b in metrics['batches']:
        if b['end']-b['start']!=2*b['repetitions'] or min(b['source_remaining_after'],b['receiver_remaining_after'])<1:
            raise ValueError('Macro crossed tail boundary')
    return dict(passed=True,prediction_sha256=object_digest(expanded),exact_complete_prediction=True,
        checkpoints_checked=len(metrics['checkpoints']),flits=len(reference['messages'][0]['flits']),
        service_boundaries=len(reference['service']),credit_returns=len(reference['credit_returns']),
        allocations=len(reference['allocations']),final_cycle=reference['final_cycle'],
        physical_cycle_updates=metrics['physical_cycle_updates'],skipped_cycles=metrics['skipped_cycles'],macros=metrics['macros'])


def compact_reference(reference):
    message=reference['messages'][0].copy();message['flits']=len(message['flits'])
    counts={key:len(reference[key]) for key in ('service','input_arrivals','credit_returns','credit_sends','allocations')}
    counts.update(retired=message['flits'],injections=message['flits'],ejections=message['flits'])
    return dict(complete=reference['complete'],drained=True,final_cycle=reference['final_cycle'],messages=[message],event_counts=counts,
        source_stall_cycles=reference['source_stall_cycles'],router_credit_stall_cycles=reference['router_credit_stall_cycles'],
        queue_peaks=reference['queue_peaks'],native_boundary_inputs=False)


def process_fields(text):
    """GNU time full-process counters, separate from prediction timers."""
    result={}
    for line in text.splitlines():
        if 'User time (seconds):' in line:result['user_seconds']=float(line.rsplit(':',1)[1])
        elif 'System time (seconds):' in line:result['system_seconds']=float(line.rsplit(':',1)[1])
        elif 'Maximum resident set size (kbytes):' in line:result['peak_rss_kib']=int(line.rsplit(':',1)[1])
        elif 'Elapsed (wall clock) time' in line:
            value=line.split('):',1)[1].strip();seconds=0.
            for part in value.split(':'):seconds=seconds*60+float(part)
            result['elapsed_seconds']=seconds
        elif 'Exit status:' in line:result['exit_status']=int(line.rsplit(':',1)[1])
    if set(result)!={'user_seconds','system_seconds','peak_rss_kib','elapsed_seconds','exit_status'} or result['exit_status']!=0:
        raise ValueError('Incomplete/failed GNU time receipt')
    return result


class PersistedRun:
    def __init__(self,record):self.record=record
    def expand(self):
        from wafer_sim.adapters.causal_macro import expand_record
        return expand_record(self.record)
    def metrics(self):return self.record['metrics']


def analyze(root,output):
    """Authenticate saved candidate, reproduce original G1, recheck every gate."""
    from pathlib import Path
    import hashlib
    import statistics
    import subprocess
    from wafer_sim.adapters.causal_macro import derived_source,expand_record
    from wafer_sim.io import read_json,write_json,digest
    repo=Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists():raise ValueError('Fresh absolute readback required')
    manifest=read_json(root/'COMPLETE.json');start=read_json(root/'STARTED.json')
    if not manifest['complete'] or not manifest['accuracy_passed'] or (root/'FAILED.json').exists():raise ValueError('Incomplete G2.1 experiment')
    for name,expected in manifest['artifacts_sha256'].items():
        if digest(root/name)!=expected:raise ValueError('Changed G2.1 artifact: '+name)
    for name,expected in start['source_hashes'].items():
        if digest(repo/name)!=expected:raise ValueError('Changed G2.1 source: '+name)
    if (digest(root/'DERIVED_CORE.py')!=start['derived_source_sha256'] or
            hashlib.sha256(derived_source().encode()).hexdigest()!=start['derived_source_sha256']):raise ValueError('Different mechanical core derivation')
    if digest(root/'ENVIRONMENT.json')!=start['environment_sha256']:raise ValueError('Changed environment receipt')
    reg=read_json(repo/'configs/causal_macro_single.json');g1=read_json(repo/'configs/causal_closure.json')
    summary=read_json(root/'RESULTS.json');rows=[]
    expected_cases=[(n,0) for n in reg['accuracy_flits']]+[(1025,reg['delayed_ready'])]
    if [(r['flits'],r['ready']) for r in summary['accuracy']]!=expected_cases:raise ValueError('Missing/duplicate G2.1 accuracy case')
    for stored in summary['accuracy']:
        n,ready=stored['flits'],stored['ready'];directory=root/f'accuracy-{n}-{ready}'
        expected=dict(contract=g1['contract'],messages=[dict(source=0,destination=3,flits=n,ready=ready)],cycle_limit=reg['cycle_limit'])
        if read_json(directory/'INPUT.json')!=expected:raise ValueError('Changed accuracy demand/contract')
        record=read_json(directory/'MACRO_RECORD.json');candidate=PersistedRun(record)
        cycles=[r['state']['cycle'] for r in candidate.metrics()['checkpoints']]
        reference,boundaries=reference_boundaries(expected['contract'],expected['messages'],expected['cycle_limit'],cycles)
        if reference!=read_json(directory/'G1_REFERENCE.json') or boundaries!={int(k):v for k,v in read_json(directory/'G1_BOUNDARIES.json').items()}:
            raise ValueError('Saved G1 reference/boundaries differ from independent regeneration')
        checked=check_run(candidate,reference,boundaries)
        if record['compact']!=compact_reference(reference):raise ValueError('Compact logical summary differs')
        checked.update(flits=n,ready=ready,macro_disabled_exact=True,compact_sha256=object_digest(record['compact']))
        if checked!=stored or checked!=read_json(directory/'CHECKED.json'):raise ValueError('Accuracy receipt differs from evidence')
        rows.append(checked)
    costs=[];identities=set();cost_summary=[]
    for stored in summary['cost']:
        identity=(stored['flits'],stored['repetition'],stored['mode'])
        if identity in identities:raise ValueError('Repeated cost worker identity')
        identities.add(identity);n,repetition,mode=identity;directory=root/f'cost-{n}-{repetition}-{mode}'
        worker=read_json(directory/'WORKER.json')
        if {k:v for k,v in stored.items() if k not in ('flits','repetition','worker_wall_seconds','process_sha256','process_record_sha256','process')}!=worker:
            raise ValueError('Cost summary differs from worker')
        if digest(directory/'PROCESS.time')!=stored['process_sha256'] or read_json(directory/'CHECKED.json')!=stored:
            raise ValueError('Cost process receipt differs')
        process=read_json(directory/'PROCESS.json')
        if (digest(directory/'PROCESS.json')!=stored['process_record_sha256'] or process['timed_out'] or process['exit_status']!=0 or
                process['finished_counter']-process['started_counter']!=stored['worker_wall_seconds'] or
                process['gnu_time']!=process_fields((directory/'PROCESS.time').read_text()) or process['gnu_time']!=stored['process'] or
                process['worker_sha256']!=digest(directory/'WORKER.json') or process['input_sha256']!=digest(directory/'INPUT.json')):
            raise ValueError('Cost fields differ from raw process receipt')
        expected=dict(contract=g1['contract'],messages=[dict(source=0,destination=3,flits=n,ready=0)],cycle_limit=reg['cycle_limit'])
        if read_json(directory/'INPUT.json')!=expected:raise ValueError('Changed cost demand/contract')
        costs.append(stored)
    required={(n,r,m) for n in reg['benchmark_flits'] for r in range(reg['repetitions']) for m in reg['cost_modes']}
    if identities!=required:raise ValueError('Incomplete cost coverage')
    for n in reg['benchmark_flits']:
        selected=[r for r in costs if r['flits']==n]
        if len({object_digest(r['compact']) for r in selected})!=1:raise ValueError('Unequal cost-mode logical output')
        independent=simulate(g1['contract'],[dict(source=0,destination=3,flits=n,ready=0)],reg['cycle_limit'])
        expected_compact=compact_reference(independent)
        if selected[0]['compact']!=expected_compact:raise ValueError('Cost result differs from fresh independent G1')
        for measured in selected:
            if measured['mode']=='macro_compact':
                path=root/f"cost-{n}-{measured['repetition']}-macro_compact"/'COMPACT_EVIDENCE.json'
                if digest(path)!=measured['evidence_sha256'] or path.stat().st_size!=measured['evidence_bytes'] or expand_record(read_json(path))!=independent:
                    raise ValueError('Production compact evidence differs from independent G1')
        by_mode={m:[r for r in selected if r['mode']==m] for m in reg['cost_modes']}
        aggregate={m:dict(prediction_seconds_median=statistics.median(r['prediction_seconds'] for r in records),
            worker_wall_seconds_median=statistics.median(r['worker_wall_seconds'] for r in records),
            worker_wall_seconds_range=[min(r['worker_wall_seconds'] for r in records),max(r['worker_wall_seconds'] for r in records)],
            process_peak_rss_kib_median=statistics.median(r['process']['peak_rss_kib'] for r in records),
            worker_cpu_seconds_median=statistics.median(r['process']['user_seconds']+r['process']['system_seconds'] for r in records),
            gnu_worker_elapsed_seconds_median=statistics.median(r['process']['elapsed_seconds'] for r in records),
            prediction_cpu_seconds_median=statistics.median(r['prediction_cpu_seconds'] for r in records),
            physical_cycle_updates=records[0]['metrics']['physical_cycle_updates'],skipped_cycles=records[0]['metrics']['skipped_cycles'])
            for m,records in by_mode.items()}
        cost_summary.append(dict(flits=n,modes=aggregate,
            same_core_prediction_speedup=aggregate['macro_off']['prediction_seconds_median']/aggregate['macro_on']['prediction_seconds_median'],
            same_core_worker_speedup=aggregate['macro_off']['worker_wall_seconds_median']/aggregate['macro_on']['worker_wall_seconds_median'],
            original_g1_worker_speedup=aggregate['g1']['worker_wall_seconds_median']/aggregate['macro_on']['worker_wall_seconds_median']))
    output.mkdir();write_json(output/'RESULTS.json',dict(accuracy=rows,cost_summary=cost_summary,accuracy_passed=True,
        scope='G2.1 one source-0 primary-contract message only; same-core counters cost separate from full evidence',native_executions=0,application_executions=0))
    write_json(output/'VERIFIED.json',dict(readback_passed=True,accuracy_passed=True,source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        campaign_manifest_sha256=digest(root/'COMPLETE.json'),artifacts_checked=len(manifest['artifacts_sha256']),
        result_sha256=digest(output/'RESULTS.json'),accuracy_cases=len(rows),cost_workers=len(costs),native_executions=0,application_executions=0))


if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();analyze(args.campaign,args.output)
