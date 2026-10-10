"""R2.1 seven-case semantic progress acceptance; full records stay unchanged."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from wafer_sim.execution.causal import run
from wafer_sim.analysis.causal_progress import registration, check_case
from wafer_sim.analysis.causal_transition import StateDivergence
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import digest, read_json, write_json

FILES = ['configs/causal_progress.json', 'configs/causal_closure.json',
    'src/wafer_sim/adapters/causal_merge.py', 'src/wafer_sim/adapters/causal_macro.py',
    'src/wafer_sim/architecture/causal_merge.py', 'src/wafer_sim/execution/causal/__init__.py',
    'src/wafer_sim/execution/causal/state.py', 'src/wafer_sim/execution/causal/transition.py',
    'src/wafer_sim/analysis/causal_transition.py', 'src/wafer_sim/analysis/causal_progress.py',
    'src/wafer_sim/experiments/causal_progress.py', 'tests/test_causal_progress.py',
    'tests/test_causal_transition.py', 'scripts/test_causal_progress_remote.py']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--r1-evidence', type=Path, required=True)
    args = parser.parse_args()
    root = require_active_server()
    repo = Path(__file__).resolve().parents[3]
    if not args.output.is_absolute() or not args.output.is_relative_to(root/'runs') or args.output.exists():
        raise ValueError('Fresh server output required')
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']):
        raise ValueError('Clean main required')
    source = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    tests = read_json(args.tests)
    if (not tests['passed'] or tests['source_commit'] != source
            or tests['tests_log_sha256'] != digest(args.tests.parent/'tests.log')
            or tests['executable_sha256'] != digest(Path(sys.executable).resolve())):
        raise ValueError('Successful authenticated same-source tests required')
    reg, g1, old_manifest = registration(repo, args.r1_evidence)
    args.output.mkdir()
    shutil.copyfile(args.tests, args.output/'TESTS.json')
    shutil.copyfile(args.tests.parent/'tests.log', args.output/'tests.log')
    environment = dict(host=platform.node(), python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines())
    write_json(args.output/'ENVIRONMENT.json', environment)
    write_json(args.output/'STARTED.json', dict(source_commit=source,
        source_hashes={p: digest(repo/p) for p in FILES}, tests_sha256=digest(args.output/'TESTS.json'),
        environment_sha256=digest(args.output/'ENVIRONMENT.json'),
        r1_campaign=str(args.r1_evidence), r1_manifest_sha256=digest(args.r1_evidence/'COMPLETE.json'),
        native_executions=0, application_executions=0, compression_enabled=False,
        evidence_mode='full'))
    rows = []
    try:
        for case in g1['cases']:
            directory = args.output/case['name']
            directory.mkdir()
            contract = dict(g1['contract'], capacity_flits=case.get('capacity_flits', g1['contract']['capacity_flits']))
            inp = dict(contract=contract, messages=case['messages'], cycle_limit=g1['cycle_limit'])
            write_json(directory/'INPUT.json', inp)
            write_json(directory/'PREDICTION.json', run(**inp))
            checked = check_case(directory, args.r1_evidence, case, g1, old_manifest)
            write_json(directory/'CHECKED.json', checked)
            rows.append(checked)
            print(case['name'], 'exact', checked['boundaries_checked'], 'states/progress boundaries', flush=True)
        write_json(args.output/'RESULTS.json', dict(passed=True, cases=len(rows), rows=rows,
            native_executions=0, application_executions=0, compression_enabled=False,
            evidence_mode='full', scope='R2.1 semantic progress only; no sinks/macros/cost claim'))
        artifacts = {str(p.relative_to(args.output)): digest(p) for p in args.output.rglob('*') if p.is_file()}
        write_json(args.output/'COMPLETE.json', dict(complete=True, passed=True, source_commit=source,
            artifacts_sha256=artifacts, native_executions=0, application_executions=0))
    except BaseException as error:
        write_json(args.output/'FAILED.json', dict(complete=False, error=repr(error),
            first_discrepancy=error.record if isinstance(error, StateDivergence) else None))
        raise


if __name__ == '__main__':
    main()
