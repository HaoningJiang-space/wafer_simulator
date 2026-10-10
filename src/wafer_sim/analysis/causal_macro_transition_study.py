"""Independent R3 accuracy, exact state, raw worker-cost and reference readback."""
from pathlib import Path
import statistics
from wafer_sim.adapters.causal_macro import expand_record as expand_prototype
from wafer_sim.adapters.causal_merge import simulate
from wafer_sim.analysis.causal_macro_transition import reference_snapshots, check_accuracy
from wafer_sim.analysis.causal_evidence import expand_record
from wafer_sim.analysis.causal_evidence_study import expected_summary
from wafer_sim.analysis.causal_macro_single import process_fields
from wafer_sim.io import digest, read_json, write_json


def check_worker(directory, stored, inp, reference, environment, reg):
    worker = read_json(directory/'WORKER.json'); process = read_json(directory/'PROCESS.json')
    mode = stored['mode']
    command = ['taskset', '-c', ','.join(map(str, reg['affinity'])), '/usr/bin/time', '-v', '-o',
        str(directory/'PROCESS.time'), environment['executable'], '-m',
        'wafer_sim.experiments.causal_macro_transition', str(directory/'WORKER.json'),
        '--worker-input', str(directory/'INPUT.json'), '--mode', mode]
    if (read_json(directory/'INPUT.json') != inp or process['command'] != command
            or process['exit_status'] != 0 or process['timed_out'] is not False
            or process['input_sha256'] != digest(directory/'INPUT.json')
            or process['worker_sha256'] != digest(directory/'WORKER.json')
            or process['gnu_time'] != process_fields((directory/'PROCESS.time').read_text())
            or process['finished_counter'] <= process['started_counter']):
        raise ValueError('Cost process/input identity differs')
    measured = dict(worker, flits=stored['flits'], repetition=stored['repetition'],
        worker_wall_seconds=process['finished_counter']-process['started_counter'],
        process=process['gnu_time'], process_record_sha256=digest(directory/'PROCESS.json'))
    if measured != stored or measured != read_json(directory/'CHECKED.json'):
        raise ValueError('Measured cost summary differs from raw worker/process records')
    if worker['mode'] != mode or not worker['complete'] or worker['compact'] != expected_summary(reference):
        raise ValueError('Cost worker changes completion semantics')
    metrics = worker['metrics']
    if (metrics['logical_cycles'] != reference['final_cycle']
            or metrics['physical_cycle_updates']+metrics['skipped_cycles'] != reference['final_cycle']
            or metrics['next_event_sequence'] != 11*stored['flits']
            or metrics['expanded_during_execution'] is not False
            or metrics['evidence_mode'] != ('compact' if mode == 'macro_compact' else 'counters')
            or mode == 'macro_off' and (metrics['skipped_cycles'] or metrics['macros'])
            or worker['prediction_seconds'] <= 0 or worker['prediction_cpu_seconds'] <= 0):
        raise ValueError('Invalid same-core cycle/cost receipt')
    if mode == 'macro_compact':
        path = directory/'COMPACT_EVIDENCE.json'
        if (worker['evidence_sha256'] != digest(path) or worker['evidence_bytes'] != path.stat().st_size
                or expand_record(read_json(path)) != reference):
            raise ValueError('Saved compact cost evidence differs from original G1')
    elif (directory/'COMPACT_EVIDENCE.json').exists():
        raise ValueError('Counters-only worker mislabeled reconstructable evidence')
    return measured


def analyze(root, output):
    repo = Path(__file__).resolve().parents[3]
    if not output.is_absolute() or output.exists():
        raise ValueError('Fresh absolute R3 readback required')
    manifest = read_json(root/'COMPLETE.json'); start = read_json(root/'STARTED.json')
    if (not manifest['complete'] or not manifest['accuracy_passed'] or (root/'FAILED.json').exists()
            or manifest['source_commit'] != start['source_commit']):
        raise ValueError('Incomplete R3 campaign')
    for name, expected in manifest['artifacts_sha256'].items():
        if digest(root/name) != expected:
            raise ValueError('Changed R3 artifact: '+name)
    for name, expected in start['source_hashes'].items():
        if digest(repo/name) != expected:
            raise ValueError('Changed R3 source: '+name)
    tests = read_json(root/'TESTS.json'); environment = read_json(root/'ENVIRONMENT.json')
    if (not tests['passed'] or tests['source_commit'] != start['source_commit']
            or tests['tests_log_sha256'] != digest(root/'tests.log')
            or digest(root/'TESTS.json') != start['tests_sha256']
            or digest(root/'ENVIRONMENT.json') != start['environment_sha256']
            or tests['executable_sha256'] != environment['executable_sha256']):
        raise ValueError('Changed test/environment identity')
    reg = read_json(repo/'configs/causal_macro_transition.json'); g1 = read_json(repo/'configs/causal_closure.json')
    g2_root = Path(start['g2_campaign'])
    if (digest(repo/'configs/causal_closure.json') != reg['g1_registration_sha256']
            or digest(repo/'src/wafer_sim/adapters/causal_merge.py') != reg['g1_predictor_sha256']
            or digest(g2_root/'COMPLETE.json') != reg['g2_campaign_manifest_sha256']
            or start['g2_manifest_sha256'] != reg['g2_campaign_manifest_sha256']):
        raise ValueError('Changed accepted G1/G2.1 reference')
    old = read_json(g2_root/'COMPLETE.json'); summary = read_json(root/'RESULTS.json')
    inventory = [(n, 0) for n in reg['accuracy_flits']]+[(1025, reg['delayed_ready'])]
    if (not summary['accuracy_passed'] or [(r['flits'], r['ready']) for r in summary['accuracy']] != inventory
            or summary['native_executions'] != 0 or summary['application_executions'] != 0):
        raise ValueError('Changed/missing accuracy inventory or scope')
    for (n, ready), stored in zip(inventory, summary['accuracy']):
        directory = root/f'accuracy-{n}-{ready}'
        inp = dict(contract=g1['contract'], messages=[dict(source=0, destination=3, flits=n, ready=ready)],
                   cycle_limit=reg['cycle_limit'])
        if read_json(directory/'INPUT.json') != inp:
            raise ValueError('Changed R3 accuracy input')
        record = read_json(directory/'MACRO_RECORD.json'); metrics = read_json(directory/'METRICS.json')
        cycles = [r['state']['cycle'] for r in metrics['checkpoints']]+[record['summary']['final_cycle']]
        reference, boundaries = reference_snapshots(**inp, cycles=cycles)
        saved_boundaries = {int(k): v for k, v in read_json(directory/'G1_BOUNDARIES.json').items()}
        if read_json(directory/'G1_REFERENCE.json') != reference or saved_boundaries != boundaries:
            raise ValueError('Saved original reference or boundary differs from independent G1')
        old_dir = g2_root/directory.name
        for name in ('INPUT.json', 'MACRO_RECORD.json'):
            if digest(old_dir/name) != old['artifacts_sha256'][str((old_dir/name).relative_to(g2_root))]:
                raise ValueError('Changed accepted G2.1 accuracy evidence')
        if read_json(old_dir/'INPUT.json') != inp or expand_prototype(read_json(old_dir/'MACRO_RECORD.json')) != reference:
            raise ValueError('Different accepted G2.1/R3 behavior')
        checked = check_accuracy(record, metrics, reference, boundaries)
        checked.update(ready=ready, prototype_prediction_equal=True, macro_disabled_exact=True,
                       all_modes_final_state_equal=True, final_sequence=11*n)
        if (checked != stored or checked != read_json(directory/'CHECKED.json')
                or read_json(directory/'PLAIN_FULL.json') != reference
                or read_json(directory/'MACRO_FULL.json') != reference
                or read_json(directory/'COUNTERS.json') != dict(expected_summary(reference),
                    evidence_mode='counters', full_flit_audit=False)):
            raise ValueError('Saved mode prediction/summary differs')
        expected_final = boundaries[reference['final_cycle']]
        states = read_json(directory/'FINAL_STATES.json')
        if ([r['mode'] for r in states] != ['macro_off_full', 'macro_on_full', 'macro_on_compact', 'macro_on_counters']
                or any({k: r[k] for k in ('state', 'progress')} != expected_final for r in states)):
            raise ValueError('Saved mode final causal/semantic state differs')
        print('readback accuracy', n, ready, flush=True)
    expected_cells = {(n, r, mode) for n in reg['benchmark_flits'] for r in range(reg['repetitions']) for mode in reg['cost_modes']}
    actual_cells = [(r['flits'], r['repetition'], r['mode']) for r in summary['cost']]
    if len(actual_cells) != len(expected_cells) or set(actual_cells) != expected_cells:
        raise ValueError('Missing/duplicate cost worker identity')
    cached, costs = {}, []
    for stored in summary['cost']:
        n, repetition, mode = stored['flits'], stored['repetition'], stored['mode']
        inp = dict(contract=g1['contract'], messages=[dict(source=0, destination=3, flits=n, ready=0)],
                   cycle_limit=reg['cycle_limit'])
        if n not in cached:
            cached[n] = simulate(**inp)
        costs.append(check_worker(root/f'cost-{n}-{repetition}-{mode}', stored, inp, cached[n], environment, reg))
    aggregate = []
    for n in reg['benchmark_flits']:
        modes = {}
        for mode in reg['cost_modes']:
            rows = [r for r in costs if r['flits'] == n and r['mode'] == mode]
            modes[mode] = dict(worker_wall_seconds_median=statistics.median(r['worker_wall_seconds'] for r in rows),
                worker_wall_seconds_range=[min(r['worker_wall_seconds'] for r in rows), max(r['worker_wall_seconds'] for r in rows)],
                prediction_seconds_median=statistics.median(r['prediction_seconds'] for r in rows),
                prediction_cpu_seconds_median=statistics.median(r['prediction_cpu_seconds'] for r in rows),
                process_cpu_seconds_median=statistics.median(r['process']['user_seconds']+r['process']['system_seconds'] for r in rows),
                peak_rss_kib_median=statistics.median(r['process']['peak_rss_kib'] for r in rows),
                physical_cycle_updates=rows[0]['metrics']['physical_cycle_updates'], skipped_cycles=rows[0]['metrics']['skipped_cycles'])
            if mode == 'macro_compact':
                modes[mode]['evidence_bytes'] = [r['evidence_bytes'] for r in rows]
        aggregate.append(dict(flits=n, modes=modes,
            same_core_worker_speedup=modes['macro_off']['worker_wall_seconds_median']/modes['macro_on']['worker_wall_seconds_median'],
            same_core_prediction_speedup=modes['macro_off']['prediction_seconds_median']/modes['macro_on']['prediction_seconds_median']))
    output.mkdir()
    write_json(output/'RESULTS.json', dict(accuracy_passed=True, accuracy=summary['accuracy'], cost=aggregate,
        native_executions=0, application_executions=0, scope=summary['scope']))
    write_json(output/'VERIFIED.json', dict(accuracy_passed=True, readback_passed=True,
        accuracy_cases=len(inventory), cost_workers=len(costs), artifacts_checked=len(manifest['artifacts_sha256']),
        checkpoints_checked=sum(r['checkpoints_checked'] for r in summary['accuracy']),
        source_commit=start['source_commit'], campaign_manifest_sha256=digest(root/'COMPLETE.json'),
        result_sha256=digest(output/'RESULTS.json'), native_executions=0, application_executions=0))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(); analyze(args.root, args.output)
