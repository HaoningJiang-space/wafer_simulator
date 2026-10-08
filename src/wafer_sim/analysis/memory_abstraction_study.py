"""Fresh artifact readback and application/design-error analysis, remote only."""
import argparse
import csv
from pathlib import Path
import platform
import statistics
import subprocess

from wafer_sim.analysis.memory_abstraction import audit, selection
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.analysis.wafer_machine import audit_machine
from wafer_sim.experiments.memory_abstraction import prepare, REPO
from wafer_sim.io import read_json, write_json, digest, object_digest


def csv_file(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def analyze(root, output):
    if platform.node().split('.')[0] != 'eex005': raise ValueError('Remote analysis only')
    done = read_json(root/'COMPLETE.json'); start = read_json(root/'STARTED.json')
    if not done['completed'] or (root/'FAILED.json').exists(): raise ValueError('Run incomplete')
    for name, sha in done['artifacts_sha256'].items():
        if digest(root/name) != sha: raise ValueError('Changed artifact: '+name)
    reg, spec = start['machine_registration'], start['registration']
    if spec != read_json(REPO/'configs/memory_abstraction.json') or reg != read_json(REPO/spec['base_registration']):
        raise ValueError('Changed registered experiment')
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain']): raise ValueError('Clean analysis source required')
    output.mkdir(exist_ok=False)
    samples = read_json(root/'SUMMARY.json'); rows = []; costs = []; messages = {}; queues = []; full_checks = 0
    old = {r['data_placement']: r for r in read_json(REPO/'docs/results/wafer-machine-001/SUMMARY.json')}
    for layout in spec['layouts']:
        for model in spec['models']:
            c, work, placement, base, binding, timing, contract, physical, projected = prepare(layout, model, reg)
            selected = [r for r in samples if r['layout'] == layout and r['model'] == model]
            if len(selected) != spec['cold_repetitions']+spec['binding_reuse_repetitions']:
                raise ValueError('Missing repetitions')
            hashes = set()
            for sample in selected:
                directory = root/sample['directory']
                if read_json(directory/'MEASURED.json') != {k: v for k, v in sample.items() if k != 'directory'}:
                    raise ValueError('Summary differs from raw measurement')
                inp = read_json(directory.parent/'INPUT.json')
                if object_digest(inp) != object_digest(dict(physical=physical, projection=projected)):
                    raise ValueError('Compiled input differs from saved full input')
                if sample['physical_input_sha256'] != old[layout]['input_sha256']:
                    raise ValueError('Changed underlying machine/work/layout')
                result = read_json(directory/'execution.json')
                checked = audit(c, base, binding, timing, contract, result)
                if model == 'S':
                    checked['physical'] = audit_machine(work, placement, c, binding, result)
                    if object_digest(result) != old[layout]['execution_sha256']:
                        raise ValueError('Spatial execution differs from frozen result')
                if checked != read_json(directory/'AUDIT.json'): raise ValueError('Audit readback differs')
                chain = critical_chain(binding, result)
                if object_digest(chain) != object_digest(read_json(directory/'critical_chain.json')):
                    raise ValueError('Observed critical chain differs')
                sha = object_digest(result); hashes.add(sha)
                if (sha != sample['execution_sha256'] or sample['application_cycles'] != result['application_cycles']
                        or sample['chain_cycles'] != chain['cycles'] or sample['status'] != checked['status']):
                    raise ValueError('Result metrics differ from event evidence')
                if sample['messages'] != checked['logical_messages'] or sample['bytes'] != checked['logical_message_bytes'] or sample['work'] != checked['work_by_unit']:
                    raise ValueError('Work conservation summary differs')
                full_checks += 1
            if len(hashes) != 1: raise ValueError('Repeated executions disagree')
            messages[model, layout] = {m['token']: m for m in result['network_messages']}
            ref = old[layout]['application_cycles']; app = result['application_cycles']
            rows.append(dict(model=model, layout=layout, application_cycles=app, reference_cycles=ref,
                error_cycles=app-ref, error_percent=100*(app/ref-1),
                within_time_budget=abs(100*(app/ref-1)) <= spec['absolute_time_error_budget_percent'],
                compute_chain=chain['cycles'].get('compute', 0), memory_chain=chain['cycles'].get('memory', 0),
                network_chain=chain['cycles'].get('network', 0), capacity_chain=chain['cycles'].get('capacity', 0),
                capacity_wait_sum_cycles=sum(o['capacity_wait_cycles'] for o in result['operations'].values()),
                per_bank_capacity=checked['status']['per_bank_capacity'],
                controller_staging_capacity=checked['status']['controller_staging_capacity'],
                dram_spatial_contention=checked['status']['dram_spatial_contention'],
                messages=checked['logical_messages'], bytes=checked['logical_message_bytes']))
            for resource_name, resource_row in result['resources'].items():
                queues.append(dict(model=model, layout=layout, resource=resource_name,
                    busy_cycles=resource_row['busy_cycles'], queue_wait_cycles=resource_row['queue_wait_cycles'],
                    requests=resource_row['requests']))
            for profile in ('cold', 'binding_reuse'):
                observations = [s for s in selected if s['profile'] == profile]
                measurements = [{p['phase']: p for p in s['phases']} for s in observations]
                row = dict(model=model, layout=layout, profile=profile, samples=len(observations))
                for phase in measurements[0]:
                    values = [p[phase]['wall_seconds'] for p in measurements]
                    row[phase+'_median_seconds'] = statistics.median(values)
                    row[phase+'_min_seconds'] = min(values); row[phase+'_max_seconds'] = max(values)
                row['execution_python_cpu_median_seconds'] = statistics.median(p['execution']['python_cpu_seconds'] for p in measurements)
                row['native_total_cpu_median_seconds'] = statistics.median(s['native_total_cpu_seconds'] for s in observations)
                row['native_peak_rss_median_kib'] = statistics.median(s['native_peak_rss_kib'] for s in observations)
                row['python_lifetime_peak_rss_median_kib'] = statistics.median(s['python_lifetime_peak_rss_kib'] for s in observations)
                preparations = [read_json((root/s['directory']).parent/'PREPARATION.json')[0]['wall_seconds'] for s in observations]
                row['binding_preparation_median_seconds'] = statistics.median(preparations)
                row['binding_preparation_amortized_seconds'] = statistics.median(preparations)/(len(observations) if profile == 'binding_reuse' else 1)
                costs.append(row)
    decision = selection(rows, spec['selection_tolerance_cycles'])
    for pair in decision['pairs']:
        pair['within_gap_budget'] = abs(pair['gap_error_cycles']) <= spec['gap_error_budget_cycles']
    message_rows = []
    for layout in spec['layouts']:
        reference = messages['S', layout]
        for model in ('U0', 'U1'):
            candidate = messages[model, layout]
            if set(reference) != set(candidate): raise ValueError('Different logical messages')
            for token, r in reference.items():
                m = candidate[token]
                for field in ('source', 'destination', 'bytes', 'data', 'source_memory', 'destination_memory'):
                    if m[field] != r[field]: raise ValueError('Changed logical transfer')
                message_rows.append(dict(model=model, layout=layout, token=token, bytes=m['bytes'],
                    source_memory=m['source_memory'], destination_memory=m['destination_memory'],
                    model_ready=m['ready'], reference_ready=r['ready'], model_finish=m['finish'], reference_finish=r['finish'],
                    model_duration=m['finish']-m['ready'], reference_duration=r['finish']-r['ready'],
                    reference_flits=r['expected_flits'], reference_injection_wait=r['first_inject']-r['ready'],
                    reference_injection_span=r['last_inject']-r['first_inject'],
                    reference_mean_links=sum(len(f['router_path'])-1 for f in r['flits'])/len(r['flits']),
                    duration_error=(m['finish']-m['ready'])-(r['finish']-r['ready'])))
    csv_file(output/'model_decision_table.csv', rows)
    csv_file(output/'design_gaps.csv', decision['pairs'])
    csv_file(output/'costs.csv', costs)
    csv_file(output/'message_pairs.csv', message_rows)
    csv_file(output/'resource_queues.csv', queues)
    write_json(output/'SUMMARY.json', dict(rows=rows, decision=decision, costs=costs))
    plot(output, rows, decision, costs)
    write_json(output/'VERIFIED.json', dict(passed=True,
        source_commit=subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip(),
        run_source_commit=start['source_commit'], run_complete_sha256=digest(root/'COMPLETE.json'),
        artifacts_checked=len(done['artifacts_sha256']), full_execution_readbacks=full_checks,
        spatial_reproduces_accepted_hashes=True, identical_repeated_events=True,
        artifacts_sha256={str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print({'rows': rows, 'decision': decision}, flush=True)


def plot(output, rows, decision, costs):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    models = ('U0', 'U1', 'S'); layouts = ('near', 'opposite', 'single_controller')
    colors = ('#D88928', '#4C91B0', '#263D57')
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none'})
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for j, (model, color) in enumerate(zip(models, colors)):
        ax.bar([i+(j-1)*.25 for i in range(3)],
               [next(r['application_cycles'] for r in rows if r['model'] == model and r['layout'] == p) for p in layouts],
               width=.24, label=model, color=color)
    ax.set_xticks(range(3), ['Near', 'Opposite', 'Single controller'])
    ax.set_ylabel('Complete application (cycles)'); ax.legend()
    ax.set_title('One machine and work; three storage abstractions')
    fig.tight_layout(); fig.savefig(output/'application.svg'); fig.savefig(output/'application.png', dpi=170); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    pairs = [(layouts[0], layouts[1]), (layouts[0], layouts[2]), (layouts[1], layouts[2])]
    for j, (model, color) in enumerate(zip(models, colors)):
        def oriented(a, b):
            r = next(r for r in decision['pairs'] if r['model'] == model and {r['first'], r['second']} == {a, b})
            return (1 if r['first'] == a else -1)*r['gap_cycles']
        axes[0].bar([i+(j-1)*.25 for i in range(3)], [-oriented(a, b) for a, b in pairs], width=.24, color=color, label=model)
        axes[1].bar([i+(j-1)*.25 for i in range(3)],
            [next(r['execution_median_seconds'] for r in costs if r['model'] == model and r['layout'] == p and r['profile'] == 'cold') for p in layouts],
            width=.24, color=color, label=model)
    axes[0].set_xticks(range(3), ['Opp. − Near', 'Single − Near', 'Single − Opp.'])
    axes[0].set_ylabel('Predicted layout penalty (cycles)'); axes[0].legend()
    axes[1].set_xticks(range(3), ['Near', 'Opposite', 'Single'])
    axes[1].set_ylabel('Instrumented execution, median seconds')
    axes[1].set_title('3 fresh processes per cell; native logging included')
    fig.tight_layout(); fig.savefig(output/'gaps_and_cost.svg'); fig.savefig(output/'gaps_and_cost.png', dpi=170); plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path); p.add_argument('output', type=Path)
    args = p.parse_args(); analyze(args.root, args.output)
