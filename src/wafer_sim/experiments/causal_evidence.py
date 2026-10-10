"""R2.2 evidence-mode acceptance using archived G1/R1, no Native execution."""
import argparse
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from wafer_sim.execution.causal import initialize, step_one_cycle, result, compact_record
from wafer_sim.analysis.causal_evidence_study import registration, check_case
from wafer_sim.analysis.causal_transition import StateDivergence
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import digest, read_json, write_json

FILES = ['configs/causal_evidence.json', 'configs/causal_closure.json',
    'src/wafer_sim/adapters/causal_merge.py', 'src/wafer_sim/adapters/causal_macro.py',
    'src/wafer_sim/architecture/causal_merge.py', 'src/wafer_sim/execution/causal/__init__.py',
    'src/wafer_sim/execution/causal/state.py', 'src/wafer_sim/execution/causal/transition.py',
    'src/wafer_sim/execution/causal/evidence.py', 'src/wafer_sim/analysis/causal_evidence.py',
    'src/wafer_sim/analysis/causal_evidence_study.py', 'src/wafer_sim/analysis/causal_transition.py',
    'src/wafer_sim/experiments/causal_evidence.py', 'tests/test_causal_evidence.py',
    'scripts/test_causal_evidence_remote.py', 'src/wafer_sim/io.py', 'src/wafer_sim/experiments/server.py']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path); parser.add_argument('--r1', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True); args = parser.parse_args()
    root = require_active_server(); repo = Path(__file__).resolve().parents[3]
    if (not args.output.is_absolute() or not args.output.is_relative_to(root/'runs') or args.output.exists()
            or subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain'])):
        raise ValueError('Clean source and fresh server output required')
    source = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    tests = read_json(args.tests)
    if (not tests['passed'] or tests['source_commit'] != source
            or tests['tests_log_sha256'] != digest(args.tests.parent/'tests.log')):
        raise ValueError('Passing same-source tests required')
    reg, g1, old_manifest = registration(repo, args.r1)
    args.output.mkdir()
    shutil.copyfile(args.tests, args.output/'TESTS.json')
    shutil.copyfile(args.tests.parent/'tests.log', args.output/'tests.log')
    write_json(args.output/'ENVIRONMENT.json', dict(host=platform.node(), platform=platform.platform(),
        python=sys.version, executable=str(Path(sys.executable).resolve()),
        executable_sha256=digest(Path(sys.executable).resolve())))
    write_json(args.output/'STARTED.json', dict(source_commit=source,
        source_hashes={name: digest(repo/name) for name in FILES}, r1_campaign=str(args.r1),
        r1_manifest_sha256=digest(args.r1/'COMPLETE.json'), tests_sha256=digest(args.output/'TESTS.json'),
        environment_sha256=digest(args.output/'ENVIRONMENT.json')))
    try:
        rows = []
        for case in g1['cases']:
            directory = args.output/case['name']; directory.mkdir()
            contract = dict(g1['contract'], capacity_flits=case.get('capacity_flits', g1['contract']['capacity_flits']))
            inp = dict(contract=contract, messages=case['messages'], cycle_limit=g1['cycle_limit'])
            write_json(directory/'INPUT.json', inp)
            for mode, name in [('full', 'PREDICTION.json'), ('compact', 'COMPACT.json'), ('counters', 'COUNTERS.json')]:
                state = initialize(**inp, evidence=mode)
                while not state.complete:
                    step_one_cycle(state)
                write_json(directory/name, compact_record(state) if mode == 'compact' else result(state))
            checked = check_case(directory, args.r1, case, g1, old_manifest)
            write_json(directory/'CHECKED.json', checked); rows.append(checked)
            print(case['name'], checked['boundaries_checked'], 'three-mode boundaries', flush=True)
        write_json(args.output/'RESULTS.json', dict(passed=True, cases=len(rows), rows=rows,
            native_executions=0, application_executions=0, compression_enabled=False,
            evidence_modes=reg['modes'], scope='R2.2 sink separation; eager source/packet state retained'))
        artifacts = {str(p.relative_to(args.output)): digest(p) for p in args.output.rglob('*') if p.is_file()}
        write_json(args.output/'COMPLETE.json', dict(complete=True, passed=True, source_commit=source,
            artifacts_sha256=artifacts, native_executions=0, application_executions=0))
    except BaseException as error:
        write_json(args.output/'FAILED.json', dict(complete=False, error=repr(error),
            first_discrepancy=error.record if isinstance(error, StateDivergence) else None))
        raise


if __name__ == '__main__':
    main()
