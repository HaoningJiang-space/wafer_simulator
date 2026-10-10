"""Authenticated readback of bounded observation/reconstruction, no simulation."""
import argparse
from collections import Counter
import hashlib
from pathlib import Path
import subprocess

from wafer_sim.analysis.local_service import read_observation, conditional_replay
from wafer_sim.analysis.local_service_state import reconstruct_state, compare_state
from wafer_sim.io import digest, object_digest, read_json, write_json


def verify_tree(root):
    manifest = read_json(root/'COMPLETE.json')
    if not manifest['complete'] or (root/'FAILED.json').exists():
        raise ValueError('Incomplete evidence: '+str(root))
    for name, expected in manifest['artifacts_sha256'].items():
        if digest(root/name) != expected:
            raise ValueError('Changed saved artifact: '+str(root/name))
    return manifest


def analyze(components, curves, reference, acceptance, output):
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    manifest = verify_tree(components); plots = verify_tree(curves)
    accepted = read_json(acceptance); baseline = read_json(reference/'COMPLETE.json')
    if (not baseline['complete'] or (reference/'FAILED.json').exists() or
            digest(reference/'COMPLETE.json') != accepted['component_manifest_sha256'] or
            plots['component_manifest_sha256'] != accepted['component_manifest_sha256'] or
            plots['application_manifest_sha256'] != accepted['run_manifest_sha256']):
        raise ValueError('Changed accepted input domain')
    start = read_json(components/'STARTED.json'); source = Path(__file__).resolve().parents[3]
    for name, expected in start['source_hashes'].items():
        # The only subsequent writer change corrects a stale descriptive scope
        # string; service/model/observer bytes must be identical.
        if digest(source/name) == expected: continue
        if name == 'src/wafer_sim/experiments/local_service.py':
            normalized = (source/name).read_bytes().replace(
                b'not attempted; surrounding arrival/credit boundaries supplied by native',
                b'not attempted; eligibility and feedback supplied by native')
            if hashlib.sha256(normalized).hexdigest() == expected: continue
        raise ValueError('Changed service/model source: '+name)
    summary = read_json(components/'SUMMARY.json'); rows = []; checked = []
    for row in summary['rows']:
        directory = components/row['name']
        observations = read_observation(directory/'LOCAL_SERVICE.jsonl')
        network = read_json(directory/'NETWORK_RESULT.json')
        boundary = read_json(directory/'BOUNDARIES.json')
        original = reference/(row['name']+'-S-rep-0')
        for name in ('NETWORK_RESULT.json', 'INPUT.json', 'online_protocol.jsonl'):
            key = str((original/name).relative_to(reference))
            if digest(original/name) != baseline['artifacts_sha256'][key]:
                raise ValueError('Changed accepted native evidence')
            checked.append(key)
        expected = read_json(original/'NETWORK_RESULT.json')
        if (not network['complete'] or not network['final']['drained'] or
                object_digest(network['messages']) != object_digest(expected['messages']) or
                network['final'] != expected['final'] or
                object_digest(read_json(directory/'INPUT.json')) != object_digest(read_json(original/'INPUT.json')) or
                digest(directory/'online_protocol.jsonl') != digest(original/'online_protocol.jsonl')):
            raise ValueError('Observation changed native completion or demand')
        contract, = [r for r in observations if r['kind'] == 'contract']
        arrivals = [dict(flit=r['flit'], input=r['input_port'], cycle=r['local_arrival']) for r in boundary]
        credits = [dict(cycle=r['cycle'], amount=r['amount']) for r in observations if r['kind']=='credit_return']
        state = reconstruct_state(arrivals, credits, contract)
        state_check = compare_state(observations, boundary, state)
        if object_digest(state) != object_digest(read_json(directory/'STATE_REPLAY.json')) or state_check != row['state_reconstruction']:
            raise ValueError('Stored local-state reconstruction differs')
        replays = [conditional_replay(observations, stage) for stage in ('vc', 'sw')]
        for result, stored in zip(replays, row['conditional_replay']):
            if {k:v for k,v in result.items() if k!='rows'} != stored:
                raise ValueError('Stored grant reconstruction differs')
        zero_fields = ('boundary_mismatches', 'eligibility_mismatches', 'pointer_mismatches')
        if any(state_check[k] for k in zero_fields) or any(r['grant_mismatches'] or r['pointer_mismatches'] for r in replays):
            raise ValueError('Local reconstruction failed its conditional gate')
        pre = [r for r in observations if r['kind']=='allocate_pre']
        sw = [r for r in pre if r['stage']=='sw']; vc = [r for r in pre if r['stage']=='vc']
        queue_peaks = {}
        for record in pre:
            for inp in record['inputs']:
                if inp['upstream_router'] >= 0:
                    identity = str(inp['upstream_router'])
                    queue_peaks[identity] = max(queue_peaks.get(identity,0), inp['occupancy'])
        windows = read_json(curves/row['name']/'WINDOWS.json')
        events = read_json(curves/row['name']/'EVENTS.json')
        per_input = {}
        for identity in {e['input_identity'] for e in events}:
            cycles = [e['cycle'] for e in events if e['input_identity']==identity]
            per_input[identity] = [min(cycles), max(cycles)+1]
        common_begin = max(span[0] for span in per_input.values()); common_end = min(span[1] for span in per_input.values())
        steady = [w for w in windows if common_begin <= w['begin'] and w['end'] <= common_end]
        input_order = sorted(per_input)
        balance = Counter(tuple(w['input_counts'].get(i,0) for i in input_order) for w in steady)
        selected = [e for e in events if common_begin <= e['cycle'] < common_end]
        repeats = sum(a['input_identity']==b['input_identity'] for a,b in zip(selected, selected[1:]))
        rows.append(dict(name=row['name'], messages=len(network['messages']), flits=len(boundary),
            durations=[m['finish']-m['ready'] for m in network['messages']],
            contract=contract, conditional_state=state_check,
            vc_calls=len(vc), vc_multi_request_calls=sum(sum(i['requested'] for i in r['inputs'])>1 for r in vc),
            vc_zero_request_owned_calls=sum(not any(i['requested'] for i in r['inputs']) and not r['vc_available'] for r in vc),
            sw_calls=len(sw), sw_multi_request_calls=sum(sum(i['requested'] for i in r['inputs'])>1 for r in sw),
            sw_credit_full_calls=sum(not r['credit_available'] for r in sw),
            minimum_sw_credit_slots=min(r['credit_slots'] for r in sw),
            input_queue_peaks=queue_peaks, credit_returns=sum(r['amount'] for r in credits),
            common_sink_arrival_window=[common_begin,common_end] if common_end>common_begin else None,
            complete_common_windows=len(steady), fixed_window_cycles=128,
            common_window_count_patterns=[dict(input_order=input_order, counts=list(k), windows=v) for k,v in balance.items()],
            common_window_consecutive_same_input=repeats,
            input_counts=dict(Counter(e['input_identity'] for e in events))))
    output.mkdir(); write_json(output/'RESULTS.json', dict(rows=rows, native_component_executions=3,
        application_executions=0, eligibility_from_native=False,
        surrounding_arrival_credit_boundaries_from_native=True,
        note='Raw SUMMARY aggregate gate text is stale for the state layer; typed per-case flags and this readback preserve its conditional scope.'))
    write_json(output/'VERIFIED.json', dict(passed=True, source_commit=subprocess.check_output(
        ['git','-C',str(source),'rev-parse','HEAD'],text=True).strip(),
        observation_source_commit=start['source_commit'], observation_manifest_sha256=digest(components/'COMPLETE.json'),
        reconstruction_manifest_sha256=digest(curves/'COMPLETE.json'),
        reference_manifest_sha256=digest(reference/'COMPLETE.json'),
        observation_artifacts_checked=len(manifest['artifacts_sha256']), curve_artifacts_checked=len(plots['artifacts_sha256']),
        reference_artifacts_checked=len(checked), source_sha256=digest(Path(__file__).resolve()),
        artifacts_sha256={'RESULTS.json':digest(output/'RESULTS.json')}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('components','curves','reference','acceptance','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();analyze(args.components,args.curves,args.reference,args.acceptance,args.output)
