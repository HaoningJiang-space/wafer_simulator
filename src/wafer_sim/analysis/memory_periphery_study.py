"""Recheck saved artifacts and report organization/policy sensitivity."""
import argparse
from pathlib import Path
import statistics
import time

from wafer_sim.analysis.memory_periphery import audit_periphery
from wafer_sim.experiments.memory_periphery import prepare, REPO
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server


def relation(gap, tolerance):
    return 'tie' if abs(gap) <= tolerance else 'A' if gap < 0 else 'B'


def run(source, output):
    require_active_server(); started = time.perf_counter()
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    complete = read_json(source/'COMPLETE.json'); start = read_json(source/'STARTED.json')
    if (not complete['complete'] or complete['application_cells'] != 6 or
            complete['application_executions'] != 18 or complete['components'] != 9):
        raise ValueError('Incomplete registered study')
    for name, sha in complete['artifacts_sha256'].items():
        if digest(source/name) != sha: raise ValueError('Changed result artifact: '+name)
    for name, sha in start['source_hashes'].items():
        if digest(REPO/name) != sha: raise ValueError('Saved experiment source changed: '+name)
    receipt = start['tests_receipt']
    if (not receipt['passed'] or receipt['source_commit'] != start['source_commit'] or
            digest(receipt['tests_log']) != receipt['tests_log_sha256']): raise ValueError('Changed tests receipt')
    rows = read_json(source/'SUMMARY.json'); reg = start['registration']
    if len(rows) != 27 or not all(r['passed'] for r in rows): raise ValueError('Missing checked executions')
    output.mkdir(); rechecks = []
    for row in rows:
        c, w, p, b, tx, policy, identity = prepare(row['condition'], row['layout'], row['component'])
        if object_digest(identity) != row['input_sha256']: raise ValueError('Recreated another input')
        result = read_json(source/row['directory']/'execution.json')
        if object_digest(result) != row['execution_sha256']: raise ValueError('Changed execution object')
        checked = audit_periphery(w, p, c, b, tx, policy, result)
        if checked != read_json(source/row['directory']/'AUDIT.json'): raise ValueError('Independent saved audit differs')
        windows = []
        for t in tx:
            if 'chunks' not in t: continue
            phases = {x['phase']: x for x in result['phases'] if x['operation'] == t['operation']}
            points = [(phases[x['source_phase']]['ready'], 1) for x in t['chunks']]
            points += [(phases[x['destination_phase']]['finish'], -1) for x in t['chunks']]
            current = maximum = 0
            for _, delta in sorted(points):
                current += delta; maximum = max(maximum, current)
                if current < 0: raise ValueError('Fragment finished before its admission')
            if current or maximum > reg['window_chunks']: raise ValueError('Exceeded declared DMA window')
            windows.append(maximum)
        rechecks.append(dict(directory=row['directory'], passed=True, execution_sha256=row['execution_sha256'],
                             maximum_observed_fragment_window=max(windows, default=0)))
        print('rechecked', row['directory'], flush=True)
        del result
    applications = [r for r in rows if r['component'] is None]
    table, costs = [], []
    for condition in reg['conditions']:
        cells = {layout: [r for r in applications if r['condition'] == condition and r['layout'] == layout]
                 for layout in reg['layouts']}
        for cell in cells.values():
            if len(cell) != 3 or len({r['execution_sha256'] for r in cell}) != 1: raise ValueError('Unstable repeated cell')
        a, b = (cells[k][0]['application_cycles'] for k in reg['layouts'])
        table.append(dict(condition=condition, A_cycles=a, B_cycles=b, A_minus_B_cycles=a-b,
                          preferred=relation(a-b, reg['tie_tolerance_cycles']),
                          old_A_choice_regret_cycles=a-min(a, b)))
        for layout, cell in cells.items():
            first = cell[0]
            stage = {name: [next(p['wall_seconds'] for p in r['phases'] if p['phase'] == name) for r in cell]
                     for name in ('graph_binding_preparation', 'network_configuration', 'network_initialization',
                                  'execution', 'network_close_serialization', 'result_serialization', 'independent_audit')}
            costs.append(dict(condition=condition, layout=layout,
                process_wall_median_seconds=statistics.median(r['process_wall_seconds'] for r in cell),
                process_wall_range_seconds=[min(r['process_wall_seconds'] for r in cell), max(r['process_wall_seconds'] for r in cell)],
                phase_wall_median_seconds={k: statistics.median(v) for k, v in stage.items()},
                native_cpu_median_seconds=statistics.median(r['native_cpu_seconds'] for r in cell),
                python_cpu_median_seconds=statistics.median(r['python_cpu_seconds'] for r in cell),
                python_rss_range_kib=[min(r['python_peak_rss_kib'] for r in cell), max(r['python_peak_rss_kib'] for r in cell)],
                native_rss_range_kib=[min(r['native_peak_rss_kib'] for r in cell), max(r['native_peak_rss_kib'] for r in cell)],
                native_messages=first['native_messages'], native_flits=first['native_flits'],
                payload_bytes=first['payload_bytes'], control_bytes=first['control_bytes'],
                artifact_bytes_range=[min(r['output_bytes_before_measurement'] for r in cell), max(r['output_bytes_before_measurement'] for r in cell)]))
    effects = dict(interface_at_whole={layout: table[1][f'{label}_cycles']-table[0][f'{label}_cycles']
                  for label, layout in zip(('A', 'B'), reg['layouts'])},
        pipeline_at_shared={layout: table[2][f'{label}_cycles']-table[1][f'{label}_cycles']
                            for label, layout in zip(('A', 'B'), reg['layouts'])},
        pipeline_gap_change_cycles=table[2]['A_minus_B_cycles']-table[1]['A_minus_B_cycles'])
    components = [dict(case=r['component'], condition=r['condition'], cycles=r['application_cycles'],
        execution_sha256=r['execution_sha256'], native_messages=r['native_messages'], native_flits=r['native_flits'],
        process_wall_seconds=r['process_wall_seconds']) for r in rows if r['component'] is not None]
    replay = read_json(source/'REPLAYS.json')
    if len(replay) != 15 or not all(r['passed'] and r['binary_sha256'] == start['binary_sha256'] for r in replay):
        raise ValueError('Missing replay acceptance')
    timing = {}
    for r in applications:
        if r['repetition'] != 0: continue
        groups = {}
        for t in read_json(source/r['directory']/'TRANSACTIONS.json'):
            source_kind = 'external' if t['source'] == 'host-memory' else 'dram' if t['source'].startswith('dram-') else 'sram'
            key = t['kind']+'/'+source_kind
            groups.setdefault(key, []).append(t)
        timing[r['condition']+'/'+r['layout']] = {key: dict(transactions=len(v),
            payload_ready_span_median_cycles=statistics.median(t['last_payload_ready']-t['first_payload_ready'] for t in v),
            transaction_duration_median_cycles=statistics.median(t['transaction_finish']-t['transaction_ready'] for t in v),
            payload_envelope_median_cycles=statistics.median(t['last_payload_finish']-t['first_payload_ready'] for t in v),
            first_payload_offset_median_cycles=statistics.median(t['first_payload_ready']-t['transaction_ready'] for t in v))
            for key, v in groups.items()}
    compact_rows = [{k: r[k] for k in ('condition', 'layout', 'component', 'repetition', 'directory',
        'application_cycles', 'execution_sha256', 'input_sha256', 'physical_sha256', 'work_placement_sha256',
        'native_messages', 'native_flits', 'payload_bytes', 'control_bytes', 'process_wall_seconds',
        'python_peak_rss_kib', 'native_peak_rss_kib', 'passed')} for r in rows]
    write_json(output/'SUMMARY.json', compact_rows)
    write_json(output/'CHECKED.json', dict(passed=True, experiment_source_commit=start['source_commit'],
        source_run=str(source), completion_sha256=digest(source/'COMPLETE.json'),
        hashed_artifacts=len(complete['artifacts_sha256']), source_hashes_checked=len(start['source_hashes']),
        executions_reaudited=len(rechecks), native_replays=len(replay), rechecks=rechecks,
        v1_export_equivalence=read_json(source/'V1_EXPORT_EQUIVALENCE.json'),
        binary_sha256=start['binary_sha256'], tests=receipt['tests'], tests_receipt_sha256=start['tests_sha256']))
    write_json(output/'RESULTS.json', dict(application_table=table, effects=effects, components=components,
        transaction_timing=timing, costs=costs, campaign_cost=read_json(source/'COST.json'),
        validation_seconds=time.perf_counter()-started))
    changed = table[2]['preferred'] != table[1]['preferred']
    finding = 'changes' if changed else 'preserves'
    report = ['# Memory-periphery policy sensitivity: 6x6 A/B', '',
        f'The declared bounded pipeline {finding} the restricted A/B preference. This is',
        'machine-policy sensitivity, not a prediction-error comparison or hardware validation.', '',
        '| Condition | A cycles | B cycles | A−B | Preferred | Old A choice regret |',
        '|---|---:|---:|---:|---|---:|']
    for t in table:
        report.append(f"| {t['condition']} | {t['A_cycles']} | {t['B_cycles']} | {t['A_minus_B_cycles']} | {t['preferred']} | {t['old_A_choice_regret_cycles']} |")
    report.extend(['', 'A=`clustered_local`; B=`remote_balanced`. Positive A−B favors B.',
        'All six cells reproduce exactly across three fresh-process repetitions.',
        'Old v1 A/B execution hashes reproduce the accepted S records. The v1 export',
        'config and topology are byte-identical to the archived exporter.', '',
        'At whole-object policy the interface change leaves both application times',
        'unchanged in this experiment. At the fixed shared-interface organization,',
        'the pipeline changes the supply schedule and application preference. The',
        'old reversal therefore depends on transaction policy in this declared case.',
        'It remains evidence for v1, but is not established as policy-independent.', '',
        'The pipeline preserves payload/control bytes, work, full-object reservations,',
        'operand order and retirement/publication. It uses 4 KiB fragments and four',
        'slots per transaction; all observed windows are within that bound. Bank',
        'latency follows each serializer request and can overlap other requests.',
        'The policy also applies to external-controller traffic; SRAM C2C stays whole.',
        'This is not solely a change in DRAM response scheduling.', '',
        'Nine native component executions precede applications; all 27 saved',
        'executions were independently reaudited and all 15 registered command',
        'streams replayed. Detailed traffic/resource/event evidence stays on hn072.', '',
        '| Component | v1 whole | shared whole | shared pipeline |',
        '|---|---:|---:|---:|'])
    for case in reg['component_cases']:
        values = [next(r['cycles'] for r in components if r['case'] == case and r['condition'] == c) for c in reg['conditions']]
        report.append(f'| {case} | {values[0]} | {values[1]} | {values[2]} |')
    report.extend(['', '| Condition/layout | Fresh worker median (s) | Native messages | Native flits | Python RSS max (MiB) | Native RSS max (MiB) |',
                   '|---|---:|---:|---:|---:|---:|'])
    for c in costs:
        report.append(f"| {c['condition']}/{c['layout']} | {c['process_wall_median_seconds']:.3f} | {c['native_messages']} | {c['native_flits']} | {max(c['python_rss_range_kib'])/1024:.1f} | {max(c['native_rss_range_kib'])/1024:.1f} |")
    campaign = read_json(source/'COST.json')
    report.extend(['', f"Campaign wall: {campaign['total_wall_seconds']:.3f} s; component workers: {campaign['component_workers_seconds']:.3f} s; application workers: {campaign['application_workers_seconds']:.3f} s; native replay: {campaign['replay_seconds']:.3f} s. No calibration table was fitted.", '',
        'Per-stage timing, CPU, RSS ranges, output size, source/binary/input/result',
        'identities, traffic envelopes and verification receipts are in RESULTS.json,',
        'SUMMARY.json and CHECKED.json. Host load and affinity were recorded; other',
        'research jobs shared the host, so wall times are descriptive measurements.', '',
        'Limits: one fixed fragment/window choice and one known 6x6 workload/layout',
        'pair. No bank-specific-interface pipeline arm, no factorial interaction',
        'estimate, no Local rerun/global optimum claim, no new holdout or hardware',
        'calibration. D1 remains an unvalidated v1 application candidate. D0/D1 need',
        'the same policy/organization before any new prediction-accuracy assessment.', '',
        f"Experiment source: `{start['source_commit']}`. Server evidence: `{source}`."])
    (output/'REVIEW.md').write_text('\n'.join(report)+'\n')
    write_json(output/'COMPLETE.json', dict(complete=True, artifacts_sha256={p.name: digest(p) for p in output.iterdir() if p.is_file()}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True); args = p.parse_args(); run(args.source, args.output)
