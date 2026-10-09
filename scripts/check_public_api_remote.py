"""Check portable tests, fixed events and archived-input compatibility on hn072."""
import argparse
from pathlib import Path
import os
import re
import subprocess
import sys
import time
from unittest.mock import patch

from wafer_sim.adapters.periphery_case import case_from_record
from wafer_sim.analysis.periphery_input import audit_input
from wafer_sim.analysis.memory_periphery import transaction_timing
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.analysis.periphery_evidence import checked_row, verify_source
from wafer_sim.experiments.memory_periphery import prepare
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json, write_json, digest, object_digest


def main():
    root = require_active_server(); repo = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tests', type=Path, required=True); p.add_argument('--portable-python', type=Path, required=True)
    args = p.parse_args(); started = time.perf_counter()
    if not args.output.is_absolute() or args.output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']): raise ValueError('Clean source required')
    commit = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    tests = read_json(args.tests)
    if (not tests['passed'] or tests['source_commit'] != commit or 'test_public_periphery' not in tests['modules'] or
            digest(tests['tests_log']) != tests['tests_log_sha256']):
        raise ValueError('Same-source semantic regression receipt required')
    args.output.mkdir()
    environment = {k: v for k, v in os.environ.items() if not k.startswith('WAFER_')}
    environment.update(PYTHONPATH=str(repo/'src'), WAFER_REMOTE_ROOT='/unavailable-private-path')
    with (args.output/'portable-tests.log').open('w') as log:
        result = subprocess.run([str(args.portable_python), str(repo/'scripts/test_public.py')],
                                cwd=args.output, env=environment, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode: raise ValueError('Portable semantic suite failed')
    text = (args.output/'portable-tests.log').read_text()
    portable_count = int(re.search(r'Ran (\d+) tests', text).group(1))
    baseline = root/'runs/public-api-baseline-002'
    completion = read_json(baseline/'COMPLETE.json'); expected = read_json(baseline/'EXPECTED.json')
    if not completion['complete'] or expected['baseline_commit'] != 'f91824d171917e0e58824b97a1d2a2bff2e4cf51':
        raise ValueError('Wrong or incomplete behavior baseline')
    for name, sha in completion['artifacts_sha256'].items():
        if digest(baseline/name) != sha: raise ValueError('Changed baseline artifact: '+name)
    for name in ('EXPECTED.json', 'COMPLETE.json', 'controller_pipeline_read-INPUT.json',
                 'controller_pipeline_read-EXECUTION.json', 'controller_pipeline_read-AUDIT.json'):
        if digest(repo/'tests/fixtures/public-periphery'/name) != digest(baseline/name):
            raise ValueError('Published fixture differs from original baseline')
    if digest(repo/'tests/public_cases.py') != expected['fixtures_sha256']:
        raise ValueError('Fixture generator differs from pre-refactor capture')
    source = root/'runs/periphery-applications-001'; start = read_json(source/'STARTED.json')
    compatible = verify_source(repo, start)
    summaries = read_json(source/'SUMMARY.json'); inputs = []
    seen = set()
    for row in summaries:
        key = (row['condition'], row['layout'], row['component'])
        if key in seen: continue
        seen.add(key)
        c, w, placement, binding, transactions, policy, identity = prepare(*key)
        saved = read_json(source/f"inputs/{row['directory']}.json")
        if object_digest(identity) != row['input_sha256'] or object_digest(identity) != object_digest(saved):
            raise ValueError('Registered input changed: '+row['directory'])
        restored = case_from_record(saved)
        if tuple(restored.binding.plans) != tuple(binding.plans): raise ValueError('Plan iteration order changed')
        inputs.append(dict(directory=row['directory'], input_sha256=row['input_sha256']))
    if len(inputs) != 15: raise ValueError('Incomplete registered input identity coverage')
    events = []
    for row in summaries:
        if row['component'] != 'read': continue
        directory = source/row['directory']; identity = read_json(source/f"inputs/{row['directory']}.json")
        before = digest(directory/'execution.json'); result = read_json(directory/'execution.json')
        with patch('subprocess.Popen', side_effect=AssertionError('Native process during audit')):
            checked = audit_input(identity, result)
        if checked != read_json(directory/'AUDIT.json'): raise ValueError('Archived native audit changed')
        case = case_from_record(identity)
        if object_digest(critical_chain(case.binding, result)) != object_digest(read_json(directory/'critical_chain.json')):
            raise ValueError('Archived critical chain changed')
        if object_digest(transaction_timing(case.binding, case.transactions, result)) != object_digest(read_json(directory/'TRANSACTIONS.json')):
            raise ValueError('Archived transaction completion changed')
        checked_row(row, read_json(directory/'MEASURED.json'), read_json(directory/'PROCESS.json'), identity, result, checked)
        if digest(directory/'execution.json') != before: raise ValueError('Reader wrote archived events')
        events.append(dict(directory=row['directory'], execution_file_sha256=before, execution_sha256=object_digest(result)))
    if len(events) != 3: raise ValueError('Missing bank/shared/whole/pipeline native readback')
    preserved = ('src/wafer_sim/execution', 'src/wafer_sim/architecture',
        'src/wafer_sim/adapters/memory_periphery.py', 'src/wafer_sim/adapters/wafer_machine.py',
        'src/wafer_sim/analysis/memory_periphery.py', 'src/wafer_sim/workloads',
        'configs', 'patches', 'third_party', 'docs/results')
    if subprocess.check_output(['git', '-C', str(repo), 'diff', expected['baseline_commit'], '--name-only', '--', *preserved]):
        raise ValueError('Frozen resource, timing, execution or accepted-evidence implementation changed')
    native = root/'build/booksim-online/online_booksim'
    if digest(native) != start['binary_sha256']: raise ValueError('Accepted native binary changed')
    packages = subprocess.check_output([str(args.portable_python), '-m', 'pip', 'freeze'], text=True).splitlines()
    write_json(args.output/'CHECKED.json', dict(passed=True, source_commit=commit, baseline_commit=expected['baseline_commit'],
        baseline_completion_sha256=digest(baseline/'COMPLETE.json'), baseline_files_checked=len(completion['artifacts_sha256']),
        baseline_cases=len(expected['cases']), full_tests=tests, full_tests_receipt_sha256=digest(args.tests),
        portable_tests=portable_count, portable_packages=packages, portable_python_sha256=digest(args.portable_python.resolve()),
        portable_log_sha256=digest(args.output/'portable-tests.log'), portable_cwd=str(args.output),
        source_hashes={str(f.relative_to(repo)): digest(f) for base, pattern in
            ((repo/'src', '*.py'), (repo/'tests', '*.py'), (repo/'scripts', '*public*.py'))
            for f in sorted(base.rglob(pattern))},
        private_root='/unavailable-private-path', registered_inputs_unchanged=inputs, archived_native_readbacks=events,
        compatible_source_changes=compatible, preserved_paths=list(preserved), native_binary_sha256=start['binary_sha256'],
        new_application_executions=0, source_identity_changed=True, observed_behavior_changed=False,
        wall_seconds=time.perf_counter()-started))
    write_json(args.output/'COMPLETE.json', dict(complete=True, source_commit=commit, artifacts_sha256={
        f.name: digest(f) for f in args.output.iterdir() if f.is_file()}))
    print(dict(passed=True, portable_tests=portable_count, full_tests=tests['tests'], baseline_cases=len(expected['cases']),
               unchanged_registered_inputs=len(inputs), archived_native_readbacks=len(events)))


if __name__ == '__main__': main()
