"""Independent first-divergence comparison with the unchanged legacy G1.

Tracing is confined to this offline verifier. The ordinary engine never imports
this module and never reads reference events. Candidate output is saved before
the verifier starts; the streamed shadow checks intermediate state separately.
"""
from copy import deepcopy
import hashlib
import inspect
import json
import sys
from wafer_sim.adapters.causal_merge import simulate as legacy
from wafer_sim.execution.causal import initialize, step_one_cycle, result


def first_difference(expected, actual, path='state'):
    if type(expected) is not type(actual):
        return dict(field=path, expected=expected, actual=actual)
    if isinstance(expected, dict):
        if expected.keys() != actual.keys():
            return dict(field=path+'.keys', expected=list(expected), actual=list(actual))
        for key in expected:
            mismatch = first_difference(expected[key], actual[key], path+'.'+str(key))
            if mismatch:
                return mismatch
    elif isinstance(expected, list):
        if len(expected) != len(actual):
            return dict(field=path+'.length', expected=len(expected), actual=len(actual))
        for i, (left, right) in enumerate(zip(expected, actual)):
            mismatch = first_difference(left, right, f'{path}[{i}]')
            if mismatch:
                return mismatch
    elif expected != actual:
        return dict(field=path, expected=expected, actual=actual)
    return None


class StateDivergence(ValueError):
    def __init__(self, cycle, mismatch):
        self.record = dict(cycle=cycle, **mismatch)
        super().__init__('First causal state difference: '+json.dumps(self.record, sort_keys=True))


def legacy_snapshot(local, scheduled, next_sequence, final=False):
    """Independent projection of reference locals, not State.snapshot().

    The verifier observes schedule call order solely for checking sequence IDs.
    No observed event enters the candidate event queue or service decisions.
    """
    now = local['final_cycle'] if final else local['now']
    demand, work = local['demand'], local['work']
    active = {f for r in local['states'] for q in r['queues'] for f in q}
    active.update(e['flit'] for events in local['future'].values() for e in events if 'flit' in e)
    events = []
    for when, rows in sorted(local['future'].items()):
        ids = scheduled.get(when, [])
        if len(ids) != len(rows):
            raise ValueError('Reference schedule identity coverage changed')
        events.append([when, [[seq, row] for seq, row in zip(ids, rows)]])
    return deepcopy(dict(schema=1, cycle=now, complete=final,
        cycle_limit=local['cycle_limit'], contract=local['c'], demand=demand,
        sources=[dict(credit=local['source_credits'][i], issuing=list(local['issuing'][i]),
            pending=[list(p) for p in local['todo'][i]], stall_cycles=local['source_stalls'][i]) for i in range(3)],
        routers=[dict(queues=[list(q) for q in s['queues']], owner=s['owner'],
            sw_ready=s['sw_ready'], credit=s['credit'], vc_pointer=s['vc_pointer'],
            sw_pointer=s['sw_pointer'], credit_stall_cycles=local['router_stalls'][r],
            queue_peaks=local['queue_peaks'][r]) for r, s in enumerate(local['states'])],
        events=events, next_event_sequence=next_sequence, generated=local['generated'],
        next_flit=local['next_flit'], live_work=[[f, work[f]] for f in sorted(active)],
        remaining=[[m['flits']-len(local['injections'].get(m['id'], ())),
                    m['flits']-len(local['ejections'].get(m['id'], ()))] for m in demand],
        message_progress=[dict(injected=len(local['injections'].get(m['id'], ())),
            ejected=len(local['ejections'].get(m['id'], ()))) for m in demand],
        evidence_counts={key: len(local[key]) for key in
                         ('service', 'inputs', 'credits', 'credit_sends', 'allocations')}))


def compare_cycles(contract, messages, cycle_limit=200000, *, stream=None, perturb=None):
    """Run reference and independent shadow, comparing every pre-cycle boundary.

    Optional perturb is a fault-injection hook used only by tests. A mismatch
    stops immediately with the cycle/field and expected/actual values. The final
    drained boundary is checked too, including the last reverse credit.
    """
    if sys.gettrace() is not None:
        raise ValueError('Existing Python trace hook')
    lines, first = inspect.getsourcelines(legacy)
    matches = [first+i for i, line in enumerate(lines)
               if line.strip() == 'for event in future.pop(now, []):']
    if len(matches) != 1:
        raise ValueError('Unrecognized pinned G1 boundary')
    boundary_line = matches[0]
    shadow = initialize(contract, messages, cycle_limit)
    scheduled = {}
    next_sequence = 0
    boundaries = 0
    last_cycle = -1
    chain = hashlib.sha256()

    def check(local, final=False):
        nonlocal boundaries
        if perturb:
            perturb(shadow)
        expected = legacy_snapshot(local, scheduled, next_sequence, final)
        actual = shadow.snapshot().to_record()
        mismatch = first_difference(expected, actual)
        if mismatch:
            raise StateDivergence(expected['cycle'], mismatch)
        encoded = json.dumps(expected, sort_keys=True, separators=(',', ':')).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        row = dict(cycle=expected['cycle'], expected_sha256=digest, actual_sha256=digest,
                   complete=final)
        packed = json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n'
        chain.update(packed.encode())
        if stream:
            stream.write(packed)
        boundaries += 1

    def trace(frame, event, arg):
        nonlocal next_sequence, last_cycle
        if (frame.f_code.co_filename == legacy.__code__.co_filename
                and frame.f_code.co_name == 'schedule'):
            if event == 'return':
                scheduled.setdefault(frame.f_locals['when'], []).append(next_sequence)
                next_sequence += 1
            return trace
        if frame.f_code is not legacy.__code__:
            return None
        if (event == 'line' and frame.f_lineno == boundary_line
                and frame.f_locals['now'] != last_cycle):
            last_cycle = frame.f_locals['now']
            check(frame.f_locals)
            scheduled.pop(frame.f_locals['now'], None)
            step_one_cycle(shadow)
        elif event == 'return' and arg is not None:
            check(frame.f_locals, True)
        return trace

    sys.settrace(trace)
    try:
        reference = legacy(contract, messages, cycle_limit)
    finally:
        sys.settrace(None)
    candidate = result(shadow)
    mismatch = first_difference(reference, candidate, 'result')
    if mismatch:
        raise StateDivergence(shadow.now, mismatch)
    if boundaries != reference['final_cycle']+1:
        raise ValueError('Missing cycle/final boundary coverage')
    return reference, dict(passed=True, boundaries_checked=boundaries,
        cycles_checked=reference['final_cycle'], final_boundary_checked=True,
        state_chain_sha256=chain.hexdigest(), first_discrepancy=None,
        native_boundary_inputs=False)


class LedgerVerifier:
    """Check stored lines against independently recomputed boundary digests."""
    def __init__(self, stream):
        self.stream = stream

    def write(self, expected):
        if self.stream.readline() != expected:
            raise ValueError('Saved boundary ledger differs from independent states')

    def finish(self):
        if self.stream.read():
            raise ValueError('Extra/duplicate boundary ledger rows')


def check_saved_prediction(saved, reference):
    mismatch = first_difference(reference, saved, 'saved_prediction')
    if mismatch:
        raise StateDivergence(reference['final_cycle'], mismatch)


def analyze(root, output):
    """Read saved R1 evidence without re-lowering or replacing its prediction."""
    from pathlib import Path
    from wafer_sim.io import digest, read_json, write_json
    repo = Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists():
        raise ValueError('Fresh absolute readback directory required')
    manifest = read_json(root/'COMPLETE.json')
    start = read_json(root/'STARTED.json')
    if not manifest['complete'] or not manifest['passed'] or (root/'FAILED.json').exists():
        raise ValueError('Incomplete R1 experiment')
    for name, expected in manifest['artifacts_sha256'].items():
        if digest(root/name) != expected:
            raise ValueError('Changed R1 artifact: '+name)
    for name, expected in start['source_hashes'].items():
        if digest(repo/name) != expected:
            raise ValueError('Changed R1 source: '+name)
    if digest(root/'ENVIRONMENT.json') != start['environment_sha256']:
        raise ValueError('Changed R1 environment receipt')
    reg = read_json(repo/'configs/causal_transition.json')
    g1 = read_json(repo/'configs/causal_closure.json')
    archive = Path(start['g1_campaign'])
    if (digest(archive/'COMPLETE.json') != start['g1_manifest_sha256']
            or start['g1_manifest_sha256'] != reg['g1_campaign_manifest_sha256']):
        raise ValueError('Changed accepted G1 manifest')
    archived = read_json(archive/'COMPLETE.json')
    summary = read_json(root/'RESULTS.json')
    if (summary['cases'] != len(reg['cases']) or not summary['passed']
            or [r['name'] for r in summary['rows']] != reg['cases']
            or [c['name'] for c in g1['cases']] != reg['cases']):
        raise ValueError('Missing/duplicate/changed R1 case coverage')
    rows = []
    for case, stored in zip(g1['cases'], summary['rows']):
        directory = root/case['name']
        contract = dict(g1['contract'], capacity_flits=case.get('capacity_flits', g1['contract']['capacity_flits']))
        expected = dict(contract=contract, messages=case['messages'], cycle_limit=g1['cycle_limit'])
        if read_json(directory/'INPUT.json') != expected:
            raise ValueError('Changed R1 case input')
        saved = read_json(directory/'PREDICTION.json')
        old_path = archive/case['name']/'PREDICTION.json'
        if digest(old_path) != archived['artifacts_sha256'][str(old_path.relative_to(archive))]:
            raise ValueError('Changed archived G1 prediction')
        check_saved_prediction(saved, read_json(old_path))
        with (directory/'STATE_DIGESTS.jsonl').open() as stream:
            ledger = LedgerVerifier(stream)
            reference, checked = compare_cycles(**expected, stream=ledger)
            ledger.finish()
        check_saved_prediction(saved, reference)
        checked.update(name=case['name'], flits=sum(m['flits'] for m in case['messages']),
            service_boundaries=len(saved['service']), credit_returns=len(saved['credit_returns']),
            allocations=len(saved['allocations']), final_cycle=saved['final_cycle'],
            predicted_finishes=[m['finish'] for m in saved['messages']],
            archived_prediction_sha256=digest(old_path), input_sha256=digest(directory/'INPUT.json'),
            prediction_sha256=digest(directory/'PREDICTION.json'), saved_output_exact=True)
        if checked != stored or checked != read_json(directory/'CHECKED.json'):
            raise ValueError('R1 summary differs from independently checked evidence')
        rows.append(checked)
        print('readback', case['name'], checked['boundaries_checked'], flush=True)
    if (summary['native_executions'] != 0 or summary['application_executions'] != 0
            or summary['compression_enabled'] is not False):
        raise ValueError('Invalid R1 execution scope')
    output.mkdir()
    write_json(output/'RESULTS.json', summary)
    write_json(output/'VERIFIED.json', dict(passed=True, cases=len(rows),
        artifacts_checked=len(manifest['artifacts_sha256']),
        boundaries_checked=sum(r['boundaries_checked'] for r in rows),
        flits=sum(r['flits'] for r in rows), service_boundaries=sum(r['service_boundaries'] for r in rows),
        credit_returns=sum(r['credit_returns'] for r in rows), allocations=sum(r['allocations'] for r in rows),
        source_commit=start['source_commit'], campaign_manifest_sha256=digest(root/'COMPLETE.json'),
        result_sha256=digest(output/'RESULTS.json'), native_executions=0, application_executions=0,
        compression_enabled=False))


if __name__ == '__main__':
    import argparse
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    analyze(args.root, args.output)
