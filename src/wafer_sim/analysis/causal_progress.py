"""R2.1 saved prediction/progress readback; no candidate is replaced by re-solving."""
from pathlib import Path
from wafer_sim.analysis.causal_transition import compare_cycles, check_saved_prediction, LedgerVerifier, PROGRESS_FIELDS
from wafer_sim.io import digest, read_json, write_json


def registration(repo, r1):
    reg = read_json(repo/'configs/causal_progress.json')
    g1 = read_json(repo/'configs/causal_closure.json')
    if (digest(repo/'configs/causal_closure.json') != reg['g1_registration_sha256']
            or digest(repo/'src/wafer_sim/adapters/causal_merge.py') != reg['g1_predictor_sha256']
            or digest(r1/'COMPLETE.json') != reg['r1_campaign_manifest_sha256']):
        raise ValueError('Changed accepted registration/reference identity')
    manifest = read_json(r1/'COMPLETE.json')
    if not manifest['complete'] or not manifest['passed'] or (r1/'FAILED.json').exists():
        raise ValueError('Incomplete accepted R1 campaign')
    g1_root = Path(read_json(r1/'STARTED.json')['g1_campaign'])
    if digest(g1_root/'COMPLETE.json') != reg['g1_campaign_manifest_sha256']:
        raise ValueError('Changed accepted G1 campaign')
    if [c['name'] for c in g1['cases']] != reg['cases']:
        raise ValueError('Changed frozen case inventory')
    return reg, g1, manifest


class BothLedgers:
    def __init__(self, *targets):
        self.targets = targets

    def write(self, row):
        for target in self.targets:
            target.write(row)


def check_case(directory, r1, case, g1, old_manifest, replay=False):
    from contextlib import ExitStack
    contract = dict(g1['contract'], capacity_flits=case.get('capacity_flits', g1['contract']['capacity_flits']))
    inp = dict(contract=contract, messages=case['messages'], cycle_limit=g1['cycle_limit'])
    if read_json(directory/'INPUT.json') != inp:
        raise ValueError('Changed R2.1 input')
    old_directory = r1/case['name']
    for name in ('INPUT.json', 'PREDICTION.json', 'STATE_DIGESTS.jsonl'):
        path = old_directory/name
        if digest(path) != old_manifest['artifacts_sha256'][str(path.relative_to(r1))]:
            raise ValueError('Changed archived R1 case evidence')
    if read_json(old_directory/'INPUT.json') != inp:
        raise ValueError('Different R1/R2.1 input')
    # Restore the original saved candidate, never a fresh candidate replacement.
    saved = read_json(directory/'PREDICTION.json')
    check_saved_prediction(saved, read_json(old_directory/'PREDICTION.json'))
    with ExitStack() as stack:
        old_ledger = LedgerVerifier(stack.enter_context((old_directory/'STATE_DIGESTS.jsonl').open()))
        state_stream = stack.enter_context((directory/'STATE_DIGESTS.jsonl').open('r' if replay else 'w'))
        progress_stream = stack.enter_context((directory/'PROGRESS_DIGESTS.jsonl').open('r' if replay else 'w'))
        state_target = LedgerVerifier(state_stream) if replay else state_stream
        progress_target = LedgerVerifier(progress_stream) if replay else progress_stream
        reference, checked = compare_cycles(**inp, stream=BothLedgers(state_target, old_ledger),
                                             progress_stream=progress_target)
        old_ledger.finish()
        if replay:
            state_target.finish()
            progress_target.finish()
    check_saved_prediction(saved, reference)
    if (digest(directory/'PREDICTION.json') != digest(old_directory/'PREDICTION.json')
            or digest(directory/'STATE_DIGESTS.jsonl') != digest(old_directory/'STATE_DIGESTS.jsonl')):
        raise ValueError('Full result/default boundary ledger bytes differ from accepted R1')
    checked.update(name=case['name'], flits=sum(m['flits'] for m in case['messages']),
        service_boundaries=len(saved['service']), credit_returns=len(saved['credit_returns']),
        allocations=len(saved['allocations']), final_cycle=saved['final_cycle'],
        predicted_finishes=[m['finish'] for m in saved['messages']],
        progress_boundaries_checked=checked['boundaries_checked'],
        progress_fields_checked=checked['boundaries_checked']*len(case['messages'])*len(PROGRESS_FIELDS),
        progress_ledger_sha256=digest(directory/'PROGRESS_DIGESTS.jsonl'),
        default_ledger_sha256=digest(directory/'STATE_DIGESTS.jsonl'),
        input_sha256=digest(directory/'INPUT.json'), prediction_sha256=digest(directory/'PREDICTION.json'),
        archived_prediction_sha256=digest(old_directory/'PREDICTION.json'),
        full_output_byte_equal=True, default_boundaries_byte_equal=True)
    return checked


def analyze(root, output):
    repo = Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists():
        raise ValueError('Fresh absolute readback required')
    manifest = read_json(root/'COMPLETE.json')
    start = read_json(root/'STARTED.json')
    if (not manifest['complete'] or not manifest['passed'] or (root/'FAILED.json').exists()
            or manifest['source_commit'] != start['source_commit']):
        raise ValueError('Incomplete R2.1 campaign')
    for name, expected in manifest['artifacts_sha256'].items():
        if digest(root/name) != expected:
            raise ValueError('Changed R2.1 artifact: '+name)
    for name, expected in start['source_hashes'].items():
        if digest(repo/name) != expected:
            raise ValueError('Changed R2.1 source: '+name)
    if (digest(root/'ENVIRONMENT.json') != start['environment_sha256']
            or digest(root/'TESTS.json') != start['tests_sha256']):
        raise ValueError('Changed environment/test identity')
    tests = read_json(root/'TESTS.json')
    if (not tests['passed'] or tests['source_commit'] != start['source_commit']
            or tests['tests_log_sha256'] != digest(root/'tests.log')):
        raise ValueError('Changed R2.1 test receipt/log')
    r1 = Path(start['r1_campaign'])
    reg, g1, old_manifest = registration(repo, r1)
    if start['r1_manifest_sha256'] != reg['r1_campaign_manifest_sha256']:
        raise ValueError('Changed R1 identity in start receipt')
    summary = read_json(root/'RESULTS.json')
    if (not summary['passed'] or summary['cases'] != len(reg['cases'])
            or [r['name'] for r in summary['rows']] != reg['cases']):
        raise ValueError('Missing/duplicate R2.1 case inventory')
    for case, stored in zip(g1['cases'], summary['rows']):
        directory = root/case['name']
        checked = check_case(directory, r1, case, g1, old_manifest, replay=True)
        if checked != stored or checked != read_json(directory/'CHECKED.json'):
            raise ValueError('R2.1 summary differs from independent readback')
        print('readback', case['name'], checked['progress_boundaries_checked'], flush=True)
    if (summary['native_executions'] != 0 or summary['application_executions'] != 0
            or summary['compression_enabled'] is not False or summary['evidence_mode'] != 'full'):
        raise ValueError('Invalid R2.1 scope')
    output.mkdir()
    write_json(output/'RESULTS.json', summary)
    write_json(output/'VERIFIED.json', dict(passed=True, cases=len(reg['cases']),
        artifacts_checked=len(manifest['artifacts_sha256']),
        boundaries_checked=sum(r['boundaries_checked'] for r in summary['rows']),
        progress_fields_checked=sum(r['progress_fields_checked'] for r in summary['rows']),
        flits=sum(r['flits'] for r in summary['rows']),
        source_commit=start['source_commit'], campaign_manifest_sha256=digest(root/'COMPLETE.json'),
        result_sha256=digest(output/'RESULTS.json'), full_output_byte_equal=True,
        default_boundaries_byte_equal=True, native_executions=0, application_executions=0))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    analyze(args.root, args.output)
