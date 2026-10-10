"""Independent legacy-state and persisted-evidence checks for the R3 migration."""
from copy import deepcopy
import inspect
import json
import sys
from wafer_sim.adapters.causal_merge import simulate as legacy
from wafer_sim.analysis.causal_transition import legacy_snapshot, legacy_progress, first_difference, StateDivergence
from wafer_sim.analysis.causal_evidence import expand_record
from wafer_sim.analysis.causal_evidence_study import expected_summary


def json_value(value):
    """JSON's specified integer-map-key projection, for persisted state checks."""
    return json.loads(json.dumps(value))


def reference_snapshots(contract, messages, cycle_limit, cycles):
    """Observe unchanged G1, including exact insertion sequence, at wanted clocks."""
    if sys.gettrace() is not None:
        raise ValueError('Existing trace hook')
    lines, first = inspect.getsourcelines(legacy)
    matches = [first+i for i, line in enumerate(lines) if line.strip() == 'for event in future.pop(now, []):']
    if len(matches) != 1:
        raise ValueError('Unrecognized pinned G1 boundary')
    wanted, observed, scheduled = set(cycles), {}, {}
    next_sequence, last_cycle = 0, -1

    def capture(local, final=False):
        now = local['final_cycle'] if final else local['now']
        if now in wanted:
            observed[now] = dict(state=legacy_snapshot(local, scheduled, next_sequence, final),
                                 progress=legacy_progress(local))
            wanted.remove(now)

    def trace(frame, event, arg):
        nonlocal next_sequence, last_cycle
        if frame.f_code.co_filename == legacy.__code__.co_filename and frame.f_code.co_name == 'schedule':
            if event == 'return':
                scheduled.setdefault(frame.f_locals['when'], []).append(next_sequence)
                next_sequence += 1
            return trace
        if frame.f_code is not legacy.__code__:
            return None
        if event == 'line' and frame.f_lineno == matches[0] and frame.f_locals['now'] != last_cycle:
            last_cycle = frame.f_locals['now']
            capture(frame.f_locals)
            scheduled.pop(last_cycle, None)
        elif event == 'return' and arg is not None:
            capture(frame.f_locals, True)
        return trace

    sys.settrace(trace)
    try:
        prediction = legacy(contract, messages, cycle_limit)
    finally:
        sys.settrace(None)
    if wanted:
        raise ValueError('Missing independent macro boundary')
    return prediction, observed


def check_accuracy(record, metrics, reference, boundaries):
    expanded = expand_record(record)
    mismatch = first_difference(reference, expanded, 'expanded_prediction')
    if mismatch:
        raise StateDivergence(reference['final_cycle'], mismatch)
    if record['summary'] != expected_summary(reference):
        raise ValueError('Completion/count summary differs from original events')
    checks = metrics['checkpoints']
    if (len(checks) != 2*metrics['macros'] or len(metrics['batches']) != metrics['macros']
            or [row['role'] for row in checks] != ['entry', 'exit']*metrics['macros']):
        raise ValueError('Missing/duplicate macro checkpoint inventory')
    seen = set()
    for row in checks:
        clock = row['state']['cycle']; identity = row['role'], clock
        if identity in seen:
            raise ValueError('Repeated macro boundary identity')
        seen.add(identity)
        expected = boundaries.get(clock)
        actual = {k: row[k] for k in ('state', 'progress')}
        mismatch = first_difference(json_value(expected), json_value(actual))
        if mismatch:
            raise StateDivergence(clock, mismatch)
    if (metrics['physical_cycle_updates']+metrics['skipped_cycles'] != reference['final_cycle']
            or metrics['logical_cycles'] != reference['final_cycle']
            or sum(b['end']-b['start'] for b in metrics['batches']) != metrics['skipped_cycles']):
        raise ValueError('Incorrect physical/logical progress')
    for index, batch in enumerate(metrics['batches']):
        entry, exit = checks[2*index:2*index+2]
        if (batch['end']-batch['start'] != 2*batch['repetitions']
                or min(batch['source_remaining_after'], batch['receiver_remaining_after']) < 1
                or batch['period'] != 2 or batch['flit_stride'] != 1 or batch['sequence_stride'] != 11
                or entry['state']['cycle'] != batch['start'] or exit['state']['cycle'] != batch['end']
                or exit['state']['next_event_sequence']-entry['state']['next_event_sequence'] != 11*batch['repetitions']):
            raise ValueError('Incorrect macro sequence/tail boundary')
    return dict(passed=True, exact_complete_prediction=True, exact_boundary_states=True,
        checkpoints_checked=len(checks), flits=sum(len(m['flits']) for m in reference['messages']),
        service_boundaries=len(reference['service']), credit_returns=len(reference['credit_returns']),
        allocations=len(reference['allocations']), final_cycle=reference['final_cycle'],
        physical_cycle_updates=metrics['physical_cycle_updates'], skipped_cycles=metrics['skipped_cycles'],
        macros=metrics['macros'])
