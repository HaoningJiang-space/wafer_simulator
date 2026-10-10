"""R1 unchanged G1/G2.1 reference preservation and seven-case state equivalence."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
from wafer_sim.execution.causal import run
from wafer_sim.analysis.causal_transition import compare_cycles, first_difference, StateDivergence
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import digest, read_json, write_json

FILES = ['configs/causal_transition.json', 'configs/causal_closure.json',
    'src/wafer_sim/adapters/causal_merge.py', 'src/wafer_sim/adapters/causal_macro.py',
    'src/wafer_sim/architecture/causal_merge.py', 'src/wafer_sim/execution/causal/__init__.py',
    'src/wafer_sim/execution/causal/state.py', 'src/wafer_sim/execution/causal/transition.py',
    'src/wafer_sim/analysis/causal_transition.py', 'src/wafer_sim/experiments/causal_transition.py',
    'tests/test_causal_transition.py', 'scripts/test_causal_transition_remote.py']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--g1-evidence', type=Path, required=True)
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
    reg = read_json(repo/'configs/causal_transition.json')
    g1 = read_json(repo/'configs/causal_closure.json')
    if (digest(repo/'configs/causal_closure.json') != reg['g1_registration_sha256']
            or digest(repo/'src/wafer_sim/adapters/causal_merge.py') != reg['g1_predictor_sha256']
            or digest(args.g1_evidence/'COMPLETE.json') != reg['g1_campaign_manifest_sha256']):
        raise ValueError('Changed accepted G1 identity')
    old = read_json(args.g1_evidence/'COMPLETE.json')
    if not old['complete'] or not old['accuracy_passed'] or (args.g1_evidence/'FAILED.json').exists():
        raise ValueError('Incomplete accepted G1')
    if [case['name'] for case in g1['cases']] != reg['cases']:
        raise ValueError('Changed seven-case registration')
    args.output.mkdir()
    environment = dict(host=platform.node(), python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines())
    write_json(args.output/'ENVIRONMENT.json', environment)
    write_json(args.output/'STARTED.json', dict(source_commit=source,
        source_hashes={p: digest(repo/p) for p in FILES}, tests_sha256=digest(args.tests),
        environment_sha256=digest(args.output/'ENVIRONMENT.json'),
        g1_campaign=str(args.g1_evidence), g1_manifest_sha256=digest(args.g1_evidence/'COMPLETE.json'),
        native_executions=0, application_executions=0, compression_enabled=False))
    rows = []
    try:
        for case in g1['cases']:
            directory = args.output/case['name']
            directory.mkdir()
            contract = dict(g1['contract'], capacity_flits=case.get('capacity_flits', g1['contract']['capacity_flits']))
            inp = dict(contract=contract, messages=case['messages'], cycle_limit=g1['cycle_limit'])
            write_json(directory/'INPUT.json', inp)
            # Ordinary prediction has no trace hooks or reference data; persist it first.
            prediction = run(**inp)
            write_json(directory/'PREDICTION.json', prediction)
            with (directory/'STATE_DIGESTS.jsonl').open('w') as stream:
                reference, checked = compare_cycles(**inp, stream=stream)
            mismatch = first_difference(reference, prediction, 'saved_prediction')
            if mismatch:
                raise StateDivergence(reference['final_cycle'], mismatch)
            old_input = args.g1_evidence/case['name']/'INPUT.json'
            old_prediction = args.g1_evidence/case['name']/'PREDICTION.json'
            for p in (old_input, old_prediction):
                if digest(p) != old['artifacts_sha256'][str(p.relative_to(args.g1_evidence))]:
                    raise ValueError('Changed archived G1 input/prediction')
            if read_json(old_input) != dict(contract=contract, messages=case['messages']) or read_json(old_prediction) != prediction:
                raise ValueError('Different archived G1 input/prediction')
            checked.update(name=case['name'], flits=sum(m['flits'] for m in case['messages']),
                service_boundaries=len(prediction['service']), credit_returns=len(prediction['credit_returns']),
                allocations=len(prediction['allocations']), final_cycle=prediction['final_cycle'],
                predicted_finishes=[m['finish'] for m in prediction['messages']],
                archived_prediction_sha256=digest(old_prediction), input_sha256=digest(directory/'INPUT.json'),
                prediction_sha256=digest(directory/'PREDICTION.json'), saved_output_exact=True)
            write_json(directory/'CHECKED.json', checked)
            rows.append(checked)
            print(case['name'], 'exact', checked['boundaries_checked'], 'boundaries', flush=True)
        write_json(args.output/'RESULTS.json', dict(passed=True, rows=rows, cases=len(rows),
            native_executions=0, application_executions=0, compression_enabled=False,
            scope='R1 seven-case ordinary-engine equivalence; no performance claim'))
        artifacts = {str(p.relative_to(args.output)): digest(p) for p in args.output.rglob('*') if p.is_file()}
        write_json(args.output/'COMPLETE.json', dict(complete=True, passed=True, source_commit=source,
            artifacts_sha256=artifacts, native_executions=0, application_executions=0))
    except BaseException as error:
        write_json(args.output/'FAILED.json', dict(complete=False, error=repr(error),
            first_discrepancy=error.record if isinstance(error, StateDivergence) else None))
        raise


if __name__ == '__main__':
    main()
