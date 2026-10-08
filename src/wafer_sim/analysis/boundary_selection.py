"""Separate prediction objectives and locate feedback differences in saved events.

Inputs must first pass the existing full execution/identity audit. This module
does not execute a workload, select a backend, or claim hardware accuracy.
"""


def prediction_objectives(rows, registration):
    """Evaluate the registered absolute AND relative error limits separately."""
    output = []
    for row in rows:
        app_ok = (
            abs(row['error_cycles']) <= registration['application_tolerance_cycles']
            and row['ape'] <= registration['application_tolerance_percent']
        )
        message_ok = (
            row['max_message_error_cycles'] <= registration['message_tolerance_cycles']
            and row['max_message_ape'] <= registration['message_tolerance_percent']
        )
        if (app_ok, message_ok) != (row['application_target_met'], row['message_target_met']):
            raise ValueError('Saved acceptance disagrees with registered tolerances')
        occupancy = row['occupancy']
        reference = row['mode'] == 'bounded'
        output.append(dict(
            shape=row['shape'], memory_contract=row['memory_contract'], model=row['mode'],
            reference=reference, application_cycles=row['application_cycles'],
            application_error_cycles=row['error_cycles'], application_ape=row['ape'],
            application_target_met=app_ok,
            max_message_error_cycles=row['max_message_error_cycles'],
            max_message_ape=row['max_message_ape'], message_target_met=message_ok,
            peak_rx_slots=max(occupancy['peak_rx_slots'].values()) if occupancy else None,
            capacity_feasible=row['capacity_feasible'],
            accuracy_status='reference_self_comparison' if reference else 'conditional_model_comparison',
        ))
    return output


def feedback_reconvergence(pipeline, bounded):
    """Compare internal commits, reduction joins and externally visible events.

The join is derived from the recorded, independently audited phase DAG, not
from a hardcoded phase index. Readiness and actual compute service are distinct.
Different operand finish times with an equal maximum identify reconvergence;
they do not establish a universal bound on feedback's application impact.
"""
    results = {'pipeline': pipeline, 'bounded': bounded}
    moves = {name: {m['token']: m for m in r['boundary']['moves']} for name, r in results.items()}
    phases = {name: {(p['operation'], p['phase']): p for p in r['phases']} for name, r in results.items()}
    if set(moves['pipeline']) != set(moves['bounded']) or set(phases['pipeline']) != set(phases['bounded']):
        raise ValueError('Feedback comparison changed movement or phase identities')
    for token, move in moves['pipeline'].items():
        other = moves['bounded'][token]
        if any(move[k] != other[k] for k in ('source', 'destination', 'bytes')):
            raise ValueError('Feedback comparison changed logical traffic')
    changed = {t for t, m in moves['pipeline'].items() if m['finish'] != moves['bounded'][t]['finish']}
    overview = dict(
        messages=len(moves['pipeline']), changed_message_commits=len(changed),
        operations=len(pipeline['operations']),
        all_operations_equal=pipeline['operations'] == bounded['operations'],
        all_outputs_equal=pipeline['output_ready'] == bounded['output_ready'],
        application_cycles_pipeline=pipeline['application_cycles'],
        application_cycles_bounded=bounded['application_cycles'],
    )
    joins, operands = [], []
    # Only inspect operations with movements, and actual multi-input compute joins.
    operations = {t.rsplit('/phase/', 1)[0] for t in moves['pipeline']}
    for key, phase in sorted(phases['pipeline'].items()):
        op, index = key
        if op not in operations or phase['kind'] != 'compute' or len(phase['predecessors']) < 2:
            continue
        other = phases['bounded'][key]
        if other['kind'] != phase['kind'] or other['predecessors'] != phase['predecessors']:
            raise ValueError('Feedback comparison changed reduction dependencies')
        row = dict(operation=op, compute_phase=index, operands=len(phase['predecessors']))
        for name, result in results.items():
            join = phases[name][key]
            incoming = [phases[name][op, i] for i in join['predecessors']]
            if any(p['kind'] != 'memory_read' for p in incoming):
                raise ValueError('Expected memory-read predecessors for this study')
            latest = max(p['finish'] for p in incoming)
            if latest != join['ready']:
                raise ValueError('Reduction not ready at its recorded dependency join')
            service = [s for s in result['services'] if s['token'] == f'{op}/phase/{index}'
                       and s['category'] == 'compute']
            if not service:
                raise ValueError('Missing reduction service')
            row.update({
                name + '_last_operand_read': latest,
                name + '_compute_ready': join['ready'],
                name + '_compute_start': min(s['start'] for s in service),
                name + '_compute_finish': join['finish'],
            })
        for i in phase['predecessors']:
            a, b = phases['pipeline'][op, i], phases['bounded'][op, i]
            operands.append(dict(operation=op, compute_phase=index, operand_phase=i,
                pipeline_ready=a['ready'], bounded_ready=b['ready'],
                pipeline_finish=a['finish'], bounded_finish=b['finish']))
        row['changed_operand_finishes'] = sum(
            phases['pipeline'][op, i]['finish'] != phases['bounded'][op, i]['finish']
            for i in phase['predecessors'])
        row['same_compute_timing'] = all(row['pipeline_' + k] == row['bounded_' + k]
            for k in ('compute_ready', 'compute_start', 'compute_finish'))
        descendants = {index}
        for (owner, i), p in sorted(phases['pipeline'].items()):
            if owner == op and descendants.intersection(p['predecessors']):
                descendants.add(i)
        row['downstream_phases_equal'] = all(
            phases['pipeline'][op, i] == phases['bounded'][op, i] for i in descendants)
        joins.append(row)
    return overview, joins, operands
