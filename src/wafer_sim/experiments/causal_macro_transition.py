"""R3 saved accuracy/boundaries and same-core costs; no Native or applications."""
import argparse
from pathlib import Path
import os
import platform
import random
import resource
import shutil
import signal
import subprocess
import sys
import threading
import time
from wafer_sim.execution.causal.macro import run
from wafer_sim.execution.causal import result
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import digest, read_json, write_json

FILES = ['configs/causal_macro_transition.json', 'configs/causal_closure.json',
    'src/wafer_sim/adapters/causal_merge.py', 'src/wafer_sim/adapters/causal_macro.py',
    'src/wafer_sim/architecture/causal_merge.py', 'src/wafer_sim/execution/causal/__init__.py',
    'src/wafer_sim/execution/causal/state.py', 'src/wafer_sim/execution/causal/transition.py',
    'src/wafer_sim/execution/causal/evidence.py', 'src/wafer_sim/execution/causal/source.py',
    'src/wafer_sim/execution/causal/macro.py', 'src/wafer_sim/analysis/causal_evidence.py',
    'src/wafer_sim/analysis/causal_evidence_study.py', 'src/wafer_sim/analysis/causal_transition.py',
    'src/wafer_sim/analysis/causal_macro_transition.py', 'src/wafer_sim/analysis/causal_macro_single.py',
    'src/wafer_sim/analysis/causal_macro_transition_study.py',
    'src/wafer_sim/experiments/causal_macro_transition.py', 'scripts/test_causal_macro_transition_remote.py',
    'tests/test_causal_macro_transition.py', 'src/wafer_sim/io.py', 'src/wafer_sim/experiments/server.py']


def worker(inp, output, mode):
    if output.exists():
        raise ValueError('Fresh cost worker output required')
    before, cpu_before = time.perf_counter(), time.process_time()
    candidate = run(**inp, compress=mode != 'macro_off',
                    evidence='compact' if mode == 'macro_compact' else 'counters')
    summary, metrics = candidate.compact(), candidate.metrics()
    metrics.pop('batches'); metrics.pop('checkpoints')
    prediction_seconds, prediction_cpu_seconds = time.perf_counter()-before, time.process_time()-cpu_before
    record = dict(mode=mode, complete=True, compact=summary, metrics=metrics,
        prediction_seconds=prediction_seconds, prediction_cpu_seconds=prediction_cpu_seconds,
        process_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if mode == 'macro_compact':
        path = output.parent/'COMPACT_EVIDENCE.json'; write_json(path, candidate.record())
        record.update(evidence_sha256=digest(path), evidence_bytes=path.stat().st_size)
    write_json(output, record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path); parser.add_argument('--tests', type=Path)
    parser.add_argument('--g2', type=Path); parser.add_argument('--worker-input', type=Path)
    parser.add_argument('--mode', choices=('macro_off', 'macro_on', 'macro_compact'))
    args = parser.parse_args(); root = require_active_server(); repo = Path(__file__).resolve().parents[3]
    if args.worker_input is not None:
        if args.mode is None:
            raise ValueError('Explicit worker mode required')
        worker(read_json(args.worker_input), args.output, args.mode); return
    # Reference/analysis dependencies are absent from the timed worker process.
    from wafer_sim.analysis.causal_macro_transition import reference_snapshots, check_accuracy
    from wafer_sim.analysis.causal_macro_single import process_fields
    from wafer_sim.adapters.causal_macro import expand_record as expand_prototype
    if (args.tests is None or args.g2 is None or not args.output.is_absolute()
            or not args.output.is_relative_to(root/'runs') or args.output.exists()
            or subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'])):
        raise ValueError('Clean source, references and fresh server output required')
    source = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    tests = read_json(args.tests)
    if (not tests['passed'] or tests['source_commit'] != source
            or tests['tests_log_sha256'] != digest(args.tests.parent/'tests.log')
            or tests['executable_sha256'] != digest(Path(sys.executable).resolve())):
        raise ValueError('Passing same-source/interpreter tests required')
    reg = read_json(repo/'configs/causal_macro_transition.json'); g1 = read_json(repo/'configs/causal_closure.json')
    if (digest(repo/'configs/causal_closure.json') != reg['g1_registration_sha256']
            or digest(repo/'src/wafer_sim/adapters/causal_merge.py') != reg['g1_predictor_sha256']
            or digest(args.g2/'COMPLETE.json') != reg['g2_campaign_manifest_sha256']):
        raise ValueError('Changed accepted G1/G2.1 reference')
    old_manifest = read_json(args.g2/'COMPLETE.json')
    if not old_manifest['complete'] or not old_manifest['accuracy_passed'] or (args.g2/'FAILED.json').exists():
        raise ValueError('Incomplete G2.1 reference')
    args.output.mkdir()
    shutil.copyfile(args.tests, args.output/'TESTS.json'); shutil.copyfile(args.tests.parent/'tests.log', args.output/'tests.log')
    write_json(args.output/'ENVIRONMENT.json', dict(host=platform.node(), python=sys.version,
        executable=str(Path(sys.executable).resolve()), launcher_executable=sys.executable,
        executable_sha256=digest(Path(sys.executable).resolve()),
        platform=platform.platform(), affinity=reg['affinity']))
    write_json(args.output/'STARTED.json', dict(source_commit=source,
        source_hashes={name: digest(repo/name) for name in FILES}, g2_campaign=str(args.g2),
        g2_manifest_sha256=digest(args.g2/'COMPLETE.json'), tests_sha256=digest(args.output/'TESTS.json'),
        environment_sha256=digest(args.output/'ENVIRONMENT.json'), native_executions=0, application_executions=0))
    rows, costs = [], []
    try:
        accuracy = [(n, 0) for n in reg['accuracy_flits']]+[(1025, reg['delayed_ready'])]
        for n, ready in accuracy:
            directory = args.output/f'accuracy-{n}-{ready}'; directory.mkdir()
            inp = dict(contract=g1['contract'], messages=[dict(source=0, destination=3, flits=n, ready=ready)],
                       cycle_limit=reg['cycle_limit'])
            write_json(directory/'INPUT.json', inp)
            candidate = run(**inp, checkpoints=True)
            write_json(directory/'MACRO_RECORD.json', candidate.record()); write_json(directory/'METRICS.json', candidate.metrics())
            clocks = [r['state']['cycle'] for r in candidate.metrics()['checkpoints']]+[candidate.final_cycle]
            reference, boundaries = reference_snapshots(**inp, cycles=clocks)
            write_json(directory/'G1_REFERENCE.json', reference); write_json(directory/'G1_BOUNDARIES.json', boundaries)
            checked = check_accuracy(candidate.record(), candidate.metrics(), reference, boundaries)
            old_dir = args.g2/directory.name
            for name in ('INPUT.json', 'MACRO_RECORD.json'):
                if digest(old_dir/name) != old_manifest['artifacts_sha256'][str((old_dir/name).relative_to(args.g2))]:
                    raise ValueError('Changed accepted G2.1 accuracy artifact')
            if read_json(old_dir/'INPUT.json') != inp or expand_prototype(read_json(old_dir/'MACRO_RECORD.json')) != reference:
                raise ValueError('Different G2.1/R3 contract or complete behavior')
            plain = run(**inp, compress=False, evidence='full')
            full = run(**inp, evidence='full'); counters = run(**inp, evidence='counters')
            write_json(directory/'PLAIN_FULL.json', result(plain.state))
            write_json(directory/'MACRO_FULL.json', result(full.state))
            write_json(directory/'COUNTERS.json', result(counters.state))
            write_json(directory/'FINAL_STATES.json', [dict(mode=mode,
                state=value.state.snapshot().to_record(), progress=value.state.progress_snapshot().to_record())
                for mode, value in [('macro_off_full', plain), ('macro_on_full', full),
                                    ('macro_on_compact', candidate), ('macro_on_counters', counters)]])
            if (result(plain.state) != reference or result(full.state) != reference
                    or plain.compact() != candidate.compact() or counters.compact() != candidate.compact()
                    or any(x.state.snapshot() != plain.state.snapshot() for x in (candidate, full, counters))
                    or any(x.state.progress_snapshot() != plain.state.progress_snapshot() for x in (candidate, full, counters))
                    or candidate.state.snapshot().to_record() != boundaries[candidate.final_cycle]['state']):
                raise ValueError('Macro off/on/mode final states differ')
            checked.update(ready=ready, prototype_prediction_equal=True, macro_disabled_exact=True,
                           all_modes_final_state_equal=True, final_sequence=candidate.state.events.next_sequence)
            write_json(directory/'CHECKED.json', checked); rows.append(checked)
            print('accuracy', n, ready, 'updates', checked['physical_cycle_updates'], 'skipped', checked['skipped_cycles'], flush=True)
        jobs = [(n, r, mode) for n in reg['benchmark_flits'] for r in range(reg['repetitions']) for mode in reg['cost_modes']]
        random.Random(reg['order_seed']).shuffle(jobs)
        for n, repetition, mode in jobs:
            directory = args.output/f'cost-{n}-{repetition}-{mode}'; directory.mkdir()
            inp = dict(contract=g1['contract'], messages=[dict(source=0, destination=3, flits=n, ready=0)],
                       cycle_limit=reg['cycle_limit']); write_json(directory/'INPUT.json', inp)
            command = ['taskset', '-c', ','.join(map(str, reg['affinity'])), '/usr/bin/time', '-v', '-o',
                str(directory/'PROCESS.time'), sys.executable, '-m', 'wafer_sim.experiments.causal_macro_transition',
                str(directory/'WORKER.json'), '--worker-input', str(directory/'INPUT.json'), '--mode', mode]
            before = time.perf_counter(); timed_out = [False]
            with (directory/'worker.log').open('w') as log:
                process = subprocess.Popen(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                def expire():
                    if process.poll() is None:
                        timed_out[0] = True; os.killpg(process.pid, signal.SIGKILL)
                watchdog = threading.Timer(reg['process_deadline_seconds'], expire); watchdog.start()
                try:
                    exit_status = process.wait()
                finally:
                    watchdog.cancel(); watchdog.join()
            after = time.perf_counter()
            if timed_out[0] or exit_status != 0:
                raise RuntimeError('Timed-out/failed R3 cost worker')
            measured = read_json(directory/'WORKER.json'); gnu_time = process_fields((directory/'PROCESS.time').read_text())
            write_json(directory/'PROCESS.json', dict(started_counter=before, finished_counter=after,
                exit_status=exit_status, timed_out=timed_out[0], command=command, gnu_time=gnu_time,
                input_sha256=digest(directory/'INPUT.json'), worker_sha256=digest(directory/'WORKER.json')))
            measured.update(flits=n, repetition=repetition, worker_wall_seconds=after-before,
                process=gnu_time, process_record_sha256=digest(directory/'PROCESS.json'))
            write_json(directory/'CHECKED.json', measured); costs.append(measured)
            print('cost', n, repetition, mode, round(after-before, 4), flush=True)
        write_json(args.output/'RESULTS.json', dict(accuracy_passed=True, accuracy=rows, cost=costs,
            native_executions=0, application_executions=0, scope='R3 explicit-core single-flow macro migration only'))
        artifacts = {str(p.relative_to(args.output)): digest(p) for p in args.output.rglob('*') if p.is_file()}
        write_json(args.output/'COMPLETE.json', dict(complete=True, accuracy_passed=True, source_commit=source,
            artifacts_sha256=artifacts, native_executions=0, application_executions=0))
    except BaseException as error:
        write_json(args.output/'FAILED.json', dict(complete=False, source_commit=source, error=repr(error),
            first_discrepancy=getattr(error, 'record', None), native_executions=0, application_executions=0))
        raise


if __name__ == '__main__':
    main()
