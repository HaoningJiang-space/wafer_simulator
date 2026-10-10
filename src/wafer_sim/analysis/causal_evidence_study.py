"""R2.2 independent readback: saved candidates, original R1 and all boundaries."""
from copy import deepcopy
from pathlib import Path
from contextlib import ExitStack
import hashlib
import json
from wafer_sim.io import digest, read_json, write_json
from wafer_sim.execution.causal import initialize, step_one_cycle, result, compact_record, completion_summary
from wafer_sim.analysis.causal_evidence import expand_record
from wafer_sim.analysis.causal_transition import LedgerVerifier, check_saved_prediction, first_difference, StateDivergence, PROGRESS_FIELDS


def registration(repo, r1):
    reg = read_json(repo/'configs/causal_evidence.json')
    g1 = read_json(repo/'configs/causal_closure.json')
    if (digest(repo/'configs/causal_closure.json') != reg['g1_registration_sha256']
            or digest(repo/'src/wafer_sim/adapters/causal_merge.py') != reg['g1_predictor_sha256']
            or digest(r1/'COMPLETE.json') != reg['r1_campaign_manifest_sha256']
            or [c['name'] for c in g1['cases']] != reg['cases']):
        raise ValueError('Changed accepted R2.2 registration/reference')
    manifest = read_json(r1/'COMPLETE.json')
    if not manifest['passed'] or not manifest['complete'] or (r1/'FAILED.json').exists():
        raise ValueError('Incomplete R1 reference')
    return reg, g1, manifest


def expected_summary(full):
    """Derive independent completion/count fields from the original full events."""
    summary = {k: deepcopy(full[k]) for k in ('complete', 'drained', 'final_cycle',
        'source_stall_cycles', 'router_credit_stall_cycles', 'queue_peaks', 'native_boundary_inputs')}
    summary['messages'] = [dict(m, flits=len(m['flits'])) for m in full['messages']]
    summary['event_counts'] = {k: len(full[name]) for k, name in
        [('service', 'service'), ('inputs', 'input_arrivals'), ('credits', 'credit_returns'),
         ('credit_sends', 'credit_sends'), ('allocations', 'allocations')]}
    total = sum(len(m['flits']) for m in full['messages'])
    summary['event_counts'].update(injections=total, ejections=total, retired=total)
    return summary


def packed(row):
    return json.dumps(row, sort_keys=True, separators=(',', ':'))+'\n'


def check_case(directory, r1, case, g1, old_manifest, replay=False):
    contract = dict(g1['contract'], capacity_flits=case.get('capacity_flits', g1['contract']['capacity_flits']))
    inp = dict(contract=contract, messages=case['messages'], cycle_limit=g1['cycle_limit'])
    if read_json(directory/'INPUT.json') != inp:
        raise ValueError('Changed evidence-mode input')
    old = r1/case['name']
    for name in ('INPUT.json', 'PREDICTION.json', 'STATE_DIGESTS.jsonl'):
        if digest(old/name) != old_manifest['artifacts_sha256'][str((old/name).relative_to(r1))]:
            raise ValueError('Changed accepted R1 artifact')
    if read_json(old/'INPUT.json') != inp:
        raise ValueError('Different R1/R2.2 input')
    reference = read_json(old/'PREDICTION.json')
    summary = expected_summary(reference)
    saved_full = read_json(directory/'PREDICTION.json')
    saved_compact = read_json(directory/'COMPACT.json')
    saved_counters = read_json(directory/'COUNTERS.json')
    check_saved_prediction(saved_full, reference)
    check_saved_prediction(expand_record(saved_compact), reference)
    if (saved_compact['summary'] != summary or
            saved_counters != dict(summary, evidence_mode='counters', full_flit_audit=False)):
        raise ValueError('Saved completion counters differ from original events')
    states = [initialize(**inp, evidence=mode) for mode in ('full', 'compact', 'counters')]
    boundaries = 0
    progress_checks = 0
    chain = hashlib.sha256()
    with ExitStack() as stack:
        old_ledger = LedgerVerifier(stack.enter_context((old/'STATE_DIGESTS.jsonl').open()))
        stream = stack.enter_context((directory/'MODE_DIGESTS.jsonl').open('r' if replay else 'w'))
        target = LedgerVerifier(stream) if replay else stream
        while True:
            records = [s.snapshot().to_record() for s in states]
            progress = [s.progress_snapshot().to_record() for s in states]
            for index in (1, 2):
                mismatch = first_difference(records[0], records[index]) or first_difference(progress[0], progress[index])
                if mismatch:
                    raise StateDivergence(states[0].now, mismatch)
            state_digest = hashlib.sha256(packed(records[0]).strip().encode()).hexdigest()
            old_ledger.write(packed(dict(cycle=states[0].now, complete=states[0].complete,
                expected_sha256=state_digest, actual_sha256=state_digest)))
            row = packed(dict(cycle=states[0].now, complete=states[0].complete,
                state_sha256=[hashlib.sha256(packed(r).strip().encode()).hexdigest() for r in records],
                progress_sha256=[hashlib.sha256(packed(r).strip().encode()).hexdigest() for r in progress]))
            target.write(row); chain.update(row.encode())
            boundaries += 1; progress_checks += len(case['messages'])*len(PROGRESS_FIELDS)*2
            if states[0].complete:
                break
            for state in states:
                step_one_cycle(state)
        old_ledger.finish()
        if replay:
            target.finish()
    if boundaries != reference['final_cycle']+1:
        raise ValueError('Missing final drain boundary')
    check_saved_prediction(result(states[0]), saved_full)
    if (compact_record(states[1]) != saved_compact or result(states[2]) != saved_counters
            or any(completion_summary(s) != summary for s in states)):
        raise ValueError('Fresh-mode execution differs from saved candidates')
    if digest(directory/'PREDICTION.json') != digest(old/'PREDICTION.json'):
        raise ValueError('Full prediction bytes changed')
    return dict(name=case['name'], passed=True, boundaries_checked=boundaries,
        mode_pairs=2, semantic_scalar_comparisons=progress_checks,
        flits=sum(m['flits'] for m in case['messages']), final_cycle=reference['final_cycle'],
        full_output_byte_equal=True, archived_boundaries_identical=True,
        compact_expansion_equal=True, counters_semantics_equal=True,
        mode_ledger_sha256=digest(directory/'MODE_DIGESTS.jsonl'), mode_chain_sha256=chain.hexdigest(),
        input_sha256=digest(directory/'INPUT.json'), full_sha256=digest(directory/'PREDICTION.json'),
        compact_sha256=digest(directory/'COMPACT.json'), counters_sha256=digest(directory/'COUNTERS.json'))


def analyze(root, output):
    repo = Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists():
        raise ValueError('Fresh absolute readback required')
    manifest = read_json(root/'COMPLETE.json'); start = read_json(root/'STARTED.json')
    if (not manifest['complete'] or not manifest['passed'] or (root/'FAILED.json').exists()
            or manifest['source_commit'] != start['source_commit']):
        raise ValueError('Incomplete evidence-mode campaign')
    for name, expected in manifest['artifacts_sha256'].items():
        if digest(root/name) != expected:
            raise ValueError('Changed saved artifact: '+name)
    for name, expected in start['source_hashes'].items():
        if digest(repo/name) != expected:
            raise ValueError('Changed execution/verification source: '+name)
    tests = read_json(root/'TESTS.json')
    if (not tests['passed'] or tests['source_commit'] != start['source_commit']
            or tests['tests_log_sha256'] != digest(root/'tests.log')
            or digest(root/'TESTS.json') != start['tests_sha256']
            or digest(root/'ENVIRONMENT.json') != start['environment_sha256']):
        raise ValueError('Changed test/environment receipt')
    r1 = Path(start['r1_campaign'])
    reg, g1, old_manifest = registration(repo, r1)
    summary = read_json(root/'RESULTS.json')
    if (summary['cases'] != len(reg['cases']) or not summary['passed']
            or [r['name'] for r in summary['rows']] != reg['cases']):
        raise ValueError('Changed/missing case inventory')
    for case, stored in zip(g1['cases'], summary['rows']):
        checked = check_case(root/case['name'], r1, case, g1, old_manifest, True)
        if checked != stored or checked != read_json(root/case['name']/'CHECKED.json'):
            raise ValueError('Summary differs from independent readback')
        print('readback', case['name'], checked['boundaries_checked'], flush=True)
    output.mkdir()
    write_json(output/'RESULTS.json', summary)
    write_json(output/'VERIFIED.json', dict(passed=True, cases=len(reg['cases']),
        artifacts_checked=len(manifest['artifacts_sha256']),
        boundaries_checked=sum(r['boundaries_checked'] for r in summary['rows']),
        flits=sum(r['flits'] for r in summary['rows']), source_commit=start['source_commit'],
        campaign_manifest_sha256=digest(root/'COMPLETE.json'), result_sha256=digest(output/'RESULTS.json'),
        native_executions=0, application_executions=0))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(); analyze(args.root, args.output)
