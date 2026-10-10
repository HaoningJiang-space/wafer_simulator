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
