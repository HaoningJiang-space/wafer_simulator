"""Three observed native components; no application runs or new timing backend."""
import argparse
from collections import defaultdict
import os
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.analysis.local_service import conditional_replay, output_events, read_observation
from wafer_sim.analysis.local_service_state import reconstruct_state, compare_state
from wafer_sim.analysis.source_order import authenticated
from wafer_sim.experiments.server import require_active_server
from wafer_sim.experiments.shared_spatial_service import component_cases, component_probe
from wafer_sim.io import digest, object_digest, read_json, write_json

REPO = Path(__file__).resolve().parents[3]
REFERENCE_BINARY = 'd37fc5551d90adb03f2595f9e23ef0199b39be3a572f315ef154bad172d93beb'


def check_boundaries(records, network, router=24, destination=36):
    events = output_events(network['messages'], router, destination)
    expected = {r['flit']: r for r in events}
    stages = defaultdict(dict); ports = {}
    for record in records:
        if record['kind'] == 'allocate_pre':
            for row in record['inputs']:
                key, value = row['input'], row['upstream_router']
                if key in ports and ports[key] != value:
                    raise ValueError('Changed input attachment')
                ports[key] = value
        if record['kind'] in ('vc_commit', 'sw_commit', 'output_send'):
            stage = record['kind']; identity = record['flit']
            if identity not in expected or identity in stages[stage]:
                raise ValueError('Unknown or repeated observed flit')
            stages[stage][identity] = record
    if not expected or any(set(stages[k]) != set(expected) for k in ('vc_commit', 'sw_commit', 'output_send')):
        raise ValueError('Incomplete observed service boundaries')
    rows = []
    for identity, arrival in expected.items():
        vc, sw, sent = (stages[k][identity] for k in ('vc_commit', 'sw_commit', 'output_send'))
        if (not arrival['local_arrival'] <= vc['cycle'] <= sw['cycle'] <= sent['cycle'] <= arrival['cycle']
                or vc['input'] != sw['input'] or vc['message'] != sw['message']
                or sent['message'] != arrival['message'] or vc['message'] != arrival['message']):
            raise ValueError('Inconsistent local causal boundaries')
        if arrival['input_identity'] != f"router/{ports[sw['input']]}" or ports[sw['input']] < 0:
            raise ValueError('Observation input differs from saved channel identity')
        rows.append(dict(flit=identity, input_port=sw['input'], input_identity=arrival['input_identity'],
            local_arrival=arrival['local_arrival'], vc_commit=vc['cycle'], sw_commit=sw['cycle'],
            output_send=sent['cycle'], output_sink_arrival=arrival['cycle']))
    return rows


def run(output, binary, tests):
    root = require_active_server()
    if not output.is_absolute() or not output.is_relative_to(root/'runs') or output.exists():
        raise ValueError('Fresh absolute server run directory required')
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain']):
        raise ValueError('Clean committed source required')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = read_json(tests)
    if (not receipt['passed'] or receipt['source_commit'] != commit or
            'test_local_service' not in receipt['modules'] or digest(Path(receipt['tests_log'])) != receipt['tests_log_sha256']):
        raise ValueError('Same-source local-service tests required')
    if (binary.parent/'source_commit').read_text().strip() != commit:
        raise ValueError('Observation binary must be built from this source')
    if (binary.parent/'FAILED.txt').exists():
        raise ValueError('Failed observation build')
    for line in (binary.parent/'binaries.sha256').read_text().splitlines():
        expected, filename = line.split(None, 1)
        if digest(Path(filename.lstrip('*'))) != expected:
            raise ValueError('Changed observation build artifact')
    baseline = root/'build/booksim-online/online_booksim'
    if digest(baseline) != REFERENCE_BINARY or digest(binary) == REFERENCE_BINARY:
        raise ValueError('Invalid baseline/observation binary identity')
    accepted = root/'runs/d1-components-001'
    published = read_json(REPO/'docs/results/shared-spatial-service-001/VERIFIED.json')
    manifest = read_json(accepted/'COMPLETE.json')
    if (not manifest['complete'] or (accepted/'FAILED.json').exists() or
            digest(accepted/'COMPLETE.json') != published['component_manifest_sha256']):
        raise ValueError('Changed accepted component evidence')
    checked = set(); summaries = authenticated(accepted, manifest, 'SUMMARY.json', checked)
    start = authenticated(accepted, manifest, 'STARTED.json', checked)
    os.sched_setaffinity(0, start['affinity'])
    output.mkdir()
    write_json(output/'STARTED.json', dict(source_commit=commit, host=platform.node(), python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()), tests=receipt,
        packages=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines(),
        component_manifest_sha256=digest(accepted/'COMPLETE.json'), baseline_binary_sha256=REFERENCE_BINARY,
        observed_binary_sha256=digest(binary), build_manifest_sha256=digest(binary.parent/'binaries.sha256'),
        compiler_sha256=digest(binary.parent/'compiler.txt'), affinity=sorted(os.sched_getaffinity(0)),
        selection=dict(router=24, destination=36), new_application_executions=0,
        source_hashes={str(p.relative_to(REPO)): digest(p) for p in [
            Path(__file__).resolve(), REPO/'src/wafer_sim/analysis/local_service.py',
            REPO/'src/wafer_sim/analysis/local_service_state.py',
            REPO/'src/wafer_sim/adapters/native/wafer_local_service.inc',
            REPO/'src/wafer_sim/adapters/native/wafer_local_service.hpp',
            REPO/'patches/booksim-local-service-observation.patch',
            REPO/'patches/online-booksim-local-service.patch']}))
    rows = []
    keys = ('WAFER_LOCAL_SERVICE_OUTPUT', 'WAFER_LOCAL_SERVICE_ROUTER', 'WAFER_LOCAL_SERVICE_DESTINATION')
    old_env = {k: os.environ.get(k) for k in keys}
    try:
        for offset in (0, 509, 3000):
            name = f'three-shared-stagger-{offset}'
            matches = [r for r in summaries if (r['name'], r['model'], r['repetition']) == (name, 'S', 0)]
            if len(matches) != 1:
                raise ValueError('Missing or duplicated accepted component')
            sample, = matches
            reference = authenticated(accepted, manifest, sample['directory']+'/NETWORK_RESULT.json', checked)
            expected_input = authenticated(accepted, manifest, sample['directory']+'/INPUT.json', checked)
            if (not reference['complete'] or not reference['final']['drained'] or
                    object_digest(reference['messages']) != sample['message_sha256']):
                raise ValueError('Changed accepted component completion')
            case, = [c for c in component_cases() if c['name'] == name]
            directory = output/name
            os.environ.update(dict(WAFER_LOCAL_SERVICE_OUTPUT=str(directory/'LOCAL_SERVICE.jsonl'),
                                   WAFER_LOCAL_SERVICE_ROUTER='24', WAFER_LOCAL_SERVICE_DESTINATION='36'))
            component_probe(directory, case, 'S', binary)
            record = read_json(directory/'NETWORK_RESULT.json')
            if (object_digest(record['messages']) != object_digest(reference['messages']) or
                    object_digest(read_json(directory/'INPUT.json')) != object_digest(expected_input) or
                    record['final'] != reference['final']):
                raise ValueError('Observation changed component inputs/completion/flit events')
            if digest(directory/'online_protocol.jsonl') != digest(accepted/sample['directory']/'online_protocol.jsonl'):
                raise ValueError('Observation changed native protocol')
            # Authenticate protocol before its use in the equality gate.
            protocol_key = sample['directory']+'/online_protocol.jsonl'
            if digest(accepted/protocol_key) != manifest['artifacts_sha256'][protocol_key]:
                raise ValueError('Changed accepted protocol')
            observations = read_observation(directory/'LOCAL_SERVICE.jsonl')
            if observations[0]['router'] != 24 or observations[0]['destination'] != 36:
                raise ValueError('Observation selection mismatch')
            boundaries = check_boundaries(observations, record)
            write_json(directory/'BOUNDARIES.json', boundaries)
            contracts = [r for r in observations if r['kind'] == 'contract']
            if len(contracts) != 1: raise ValueError('Missing observed timing contract')
            # Supply external boundaries only, not native requests or service clocks.
            arrivals = [dict(flit=r['flit'], input=r['input_port'], cycle=r['local_arrival'])
                        for r in boundaries]
            credits = [dict(cycle=r['cycle'], amount=r['amount']) for r in observations
                       if r['kind'] == 'credit_return']
            causal = reconstruct_state(arrivals, credits, contracts[0])
            state_check = compare_state(observations, boundaries, causal)
            write_json(directory/'STATE_REPLAY.json', causal)
            write_json(directory/'STATE_CHECKED.json', state_check)
            replay = []
            for stage in ('vc', 'sw'):
                try:
                    result = conditional_replay(observations, stage)
                    write_json(directory/f'{stage}-replay.json', result)
                    replay.append({k: v for k, v in result.items() if k != 'rows'})
                except ValueError as error:
                    replay.append(dict(stage=stage, supported=False, reason=str(error)))
            row = dict(name=name, exact_messages=True, exact_protocol=True, exact_input=True,
                       observed_flits=len(boundaries), conditional_replay=replay,
                       state_reconstruction=state_check,
                       independent_arrival_feedback_prediction=False)
            write_json(directory/'CHECKED.json', row); rows.append(row)
        if digest(baseline) != REFERENCE_BINARY:
            raise ValueError('Reference binary changed')
        write_json(output/'SUMMARY.json', dict(rows=rows, native_component_executions=3,
            application_executions=0, conditional_replay_only=True,
            independent_component_model_gate='not attempted; eligibility and feedback supplied by native'))
        write_json(output/'COMPLETE.json', dict(complete=True, source_commit=commit,
            exact_reference_events=True, native_component_executions=3, application_executions=0,
            artifacts_sha256={str(p.relative_to(output)): digest(p) for p in output.rglob('*') if p.is_file()}))
    except BaseException as error:
        write_json(output/'FAILED.json', dict(type=type(error).__name__, message=str(error))); raise
    finally:
        for key, value in old_env.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--binary', required=True, type=Path)
    parser.add_argument('--tests', required=True, type=Path)
    args = parser.parse_args()
    run(args.output, args.binary, args.tests)
