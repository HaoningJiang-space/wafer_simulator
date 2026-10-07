"""Compare network abstractions with the logical execution contract held fixed.

BookSim is a detailed network reference, not a measured wafer ground truth.
Message service differences are observational; upstream readiness can change.
"""
from collections import Counter, defaultdict
from statistics import mean

from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.analysis.resource_balance import checked_run, check_current
from wafer_sim.analysis.timed_attribution import critical_chain


def error_summary(rows):
    if not rows or any(r['reference_cycles'] <= 0 or r['coarse_cycles'] <= 0 for r in rows):
        raise ValueError('Positive complete application times required')
    errors = [abs(r['coarse_cycles'] / r['reference_cycles'] - 1) * 100 for r in rows]
    return dict(cases=len(rows), application_mape_percent=mean(errors),
                maximum_application_ape_percent=max(errors))


def placement_pairs(rows):
    groups = defaultdict(dict)
    for row in rows:
        key = row['algorithm'], row['memory_bytes_per_cycle']
        if row['placement'] in groups[key]: raise ValueError('Duplicate placement')
        groups[key][row['placement']] = row
    result = []
    sign = lambda x: (x > 0) - (x < 0)
    for (algorithm, bw), pair in sorted(groups.items()):
        if set(pair) != {'baseline', 'ours_rotated'}: raise ValueError('Incomplete placement pair')
        b, r = pair['baseline'], pair['ours_rotated']
        fine = b['reference_cycles'] - r['reference_cycles']
        coarse = b['coarse_cycles'] - r['coarse_cycles']
        result.append(dict(algorithm=algorithm, memory_bytes_per_cycle=bw,
            reference_gap_cycles=fine, coarse_gap_cycles=coarse,
            gap_error_cycles=coarse-fine,
            gap_absolute_relative_error_percent=100*abs(coarse-fine)/abs(fine) if fine else None,
            gap_error_percent_reference_baseline=100*(coarse-fine)/b['reference_cycles'],
            ordering_agrees=sign(fine) == sign(coarse)))
    return result


def compare_execution(binding, timing, native, coarse):
    target = TimedTarget(binding, timing)
    phases = {f"{p['operation']}/phase/{p['phase']}": p for p in coarse['phases'] if 'path' in p}
    services = defaultdict(list)
    for row in coarse['services']:
        if row['category'] == 'network': services[row['token']].append(row)
    if set(phases) != {m['token'] for m in native['network_messages']}:
        raise ValueError('Different logical transfers between backends')
    def independent_cost(path, message):
        selected = [target.endpoints[message['source']].injection,
                    *(target.links[a, b] for a, b in zip(path, path[1:])),
                    target.endpoints[message['destination']].ejection]
        duration = lambda s: (message['bytes']*s.rate_denominator+s.rate_numerator-1)//s.rate_numerator
        return dict(serialization_cycles=sum(duration(s) for s in selected),
                    latency_cycles=sum(s.latency_cycles for s in selected))
    rows = []
    for message in native['network_messages']:
        token = message['token']; phase = phases[token]; events = services[token]
        if phase['transfer_bytes'] != message['bytes']: raise ValueError('Payload differs')
        queue = sum(s['start']-s['ready'] for s in events)
        serial = sum(s['resource_released']-s['start'] for s in events)
        latency = sum(s['finish']-s['resource_released'] for s in events)
        coarse_time = phase['finish']-phase['ready']
        if coarse_time != queue+serial+latency: raise ValueError('Coarse service decomposition does not close')
        paths = Counter(tuple(f['router_path']) for f in message['flits'])
        rows.append(dict(token=token, bytes=message['bytes'], flits=message['expected_flits'],
            source=message['source'], destination=message['destination'],
            reference_ready=message['ready'], coarse_ready=phase['ready'],
            reference_finish=message['finish'], coarse_finish=phase['finish'],
            reference_duration=message['finish']-message['ready'], coarse_duration=coarse_time,
            service_error_cycles=coarse_time-(message['finish']-message['ready']),
            coarse_queue_cycles=queue, coarse_serialization_cycles=serial, coarse_latency_cycles=latency,
            coarse_path=phase['path'], native_routes=[dict(path=list(p), flits=n,
                independent_whole_message_cost=independent_cost(p, message)) for p,n in sorted(paths.items())],
            flits_on_different_path=sum(n for p,n in paths.items() if p != tuple(phase['path'])),
            first_injection_wait=message['first_inject']-message['ready']))
    chains = {name: critical_chain(binding, result) for name, result in [('booksim', native), ('coarse', coarse)]}
    return dict(messages=rows, critical_chains=chains,
                message_service_mape_percent=mean(abs(r['service_error_cycles'])/r['reference_duration']*100 for r in rows),
                flits_on_different_path=sum(r['flits_on_different_path'] for r in rows),
                coarse_network_queue_cycles=sum(r['coarse_queue_cycles'] for r in rows))


def analyze_saved(direct_path, tree_path):
    rows, details, receipts = [], {}, []
    for algorithm, root in [('direct', direct_path), ('tree', tree_path)]:
        arms, receipt = checked_run(root); receipts.append(receipt)
        for (case, placement), arm in sorted(arms.items()):
            bw = arm['config']['workload']['memory_bytes_per_cycle']
            if bw not in (32, 256, 1024): continue
            binding = check_current(arm)
            record = arm['record']
            # check_current reconstructs timing; keep original compute unit order.
            from wafer_sim.adapters.wow_target import build_wow_target
            cm = dict(record['resource_contract']['compute_memory_parameters'])
            cm['compute_rates'] = {k: cm['compute_rates'][k] for k in record['target']['compute'][0]['work_units']}
            _, timing, _ = build_wow_target(arm['exported'], cm, arm['config']['experiment']['flit_bytes'])
            detail = compare_execution(binding, timing, record['booksim'], record['store_and_forward'])
            fine, coarse = record['booksim']['application_cycles'], record['store_and_forward']['application_cycles']
            rows.append(dict(algorithm=algorithm, memory_bytes_per_cycle=bw, placement=placement,
                reference_cycles=fine, coarse_cycles=coarse, error_cycles=coarse-fine,
                absolute_percentage_error=100*abs(coarse/fine-1),
                message_service_mape_percent=detail['message_service_mape_percent'],
                flits_on_different_path=detail['flits_on_different_path'],
                coarse_network_queue_cycles=detail['coarse_network_queue_cycles']))
            details[f'{algorithm}/{case}/{placement}'] = detail
    if len(rows) != 12: raise ValueError('Expected exactly twelve saved comparisons')
    pairs = placement_pairs(rows)
    return dict(rows=rows, pairs=pairs, **error_summary(rows),
                placement_ordering_agreements=sum(p['ordering_agrees'] for p in pairs),
                source_runs=receipts, new_simulations=0), details
