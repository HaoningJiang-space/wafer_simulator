"""Saved local arrivals/output windows and conditional one-output iSLIP replay.

Output sink arrivals are not allocation grants. Native eligibility is a permitted
input only for conditional diagnosis, never an independent network prediction.
"""
import argparse
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import subprocess

from wafer_sim.io import digest, object_digest, read_json, write_json
from wafer_sim.analysis.source_order import authenticated


def output_events(messages, router, destination):
    rows = []
    seen = set()
    for message in messages:
        for flit in message['flits']:
            hops = flit['link_arrivals']
            indices = [i for i, hop in enumerate(hops)
                       if (hop['source'], hop['destination']) == (router, destination)]
            if len(indices) > 1:
                raise ValueError('Repeated selected edge in one flit path')
            if not indices:
                continue
            if flit['id'] in seen:
                raise ValueError('Duplicated selected flit')
            seen.add(flit['id'])
            i = indices[0]
            upstream = f"router/{hops[i-1]['source']}" if i else f"endpoint/{message['source']}"
            arrival = hops[i-1]['cycle'] if i else flit['injection_router_arrival']
            sink = hops[i]['cycle']
            if not arrival <= sink:
                raise ValueError('Output sink arrival precedes local arrival')
            rows.append(dict(cycle=sink, local_arrival=arrival, input_identity=upstream,
                             flit=flit['id'], message=message['id'], token=message['token']))
    return sorted(rows, key=lambda e: (e['cycle'], e['flit']))


def service_windows(events, width=128):
    if type(width) is not int or width <= 0:
        raise ValueError('Positive integer window length required')
    if not events:
        raise ValueError('No selected output events')
    if len({e['flit'] for e in events}) != len(events):
        raise ValueError('Duplicated output events')
    if len({e['cycle'] for e in events}) != len(events):
        raise ValueError('More than one flit/cycle on selected output')
    groups = defaultdict(list)
    for event in events:
        groups[(event['cycle'] // width) * width].append(event)
    rows = []
    previous = None
    for begin in range(min(groups), max(groups) + width, width):
        current = sorted(groups[begin], key=lambda e: e['cycle'])
        repetitions = 0
        for event in current:
            if previous is not None and previous['input_identity'] == event['input_identity']:
                repetitions += 1
            previous = event
        rows.append(dict(begin=begin, end=begin+width, flits=len(current),
                         input_counts=dict(Counter(e['input_identity'] for e in current)),
                         message_counts=dict(Counter(e['token'] for e in current)),
                         consecutive_same_input=repetitions,
                         scope='Observed order, including idle gaps; eligibility unknown'))
    return rows


def conditional_replay(records, stage):
    """One-output iSLIP operator with true requests, independently advanced pointer.

    Reject cross-output accept competition rather than substituting its native
    decisions. Eligibility, VC state and credit remain diagnostic inputs.
    """
    if stage not in ('vc', 'sw'):
        raise ValueError('Unknown allocation stage')
    selected = [r for r in records if r.get('stage') == stage]
    pending = None
    pointer = 0  # Pinned iSLIP constructor initializes grant pointers to zero.
    rows = []
    previous_cycle = -1
    input_count = None
    for record in selected:
        if record['kind'] == 'allocate_pre':
            if pending is not None or record['cycle'] <= previous_cycle:
                raise ValueError('Repeated or unordered allocation snapshot')
            n = record['input_count']
            if n <= 0 or (input_count is not None and input_count != n):
                raise ValueError('Changed allocator input count')
            input_count = n
            if sorted(r['input'] for r in record['inputs']) != list(range(n)):
                raise ValueError('Missing input snapshot')
            eligible = [r['input'] for r in record['inputs'] if r['requested']]
            if any(r['requested'] and r['other_output_requests'] for r in record['inputs']):
                raise ValueError('One-output replay cannot resolve cross-output accept competition')
            winner = min(eligible, key=lambda i: (i-pointer) % n) if eligible else -1
            pending = dict(cycle=record['cycle'], pointer_before=pointer,
                           observed_pointer_before=record['grant_pointer'],
                           eligible_inputs=eligible, predicted_grant=winner)
            if winner >= 0:
                pointer = (winner+1) % n
        elif record['kind'] == 'allocate_post':
            if pending is None or record['cycle'] != pending['cycle']:
                raise ValueError('Unpaired allocation snapshot')
            rows.append(dict(**pending, observed_grant=record['grant_input'],
                             pointer_after=pointer, observed_pointer_after=record['grant_pointer'],
                             grant_matches=record['grant_input'] == pending['predicted_grant'],
                             pointer_matches=pending['observed_pointer_before'] == pending['pointer_before']
                             and record['grant_pointer'] == pointer))
            previous_cycle = record['cycle']
            pending = None
        else:
            raise ValueError('Unexpected staged observation')
    if pending is not None or not rows:
        raise ValueError('Truncated or empty allocation observation')
    return dict(stage=stage, allocation_calls=len(rows),
                multiple_request_calls=sum(len(r['eligible_inputs']) > 1 for r in rows),
                grant_mismatches=sum(not r['grant_matches'] for r in rows),
                pointer_mismatches=sum(not r['pointer_matches'] for r in rows), rows=rows,
                scope='Conditional true-request replay; no independent arrival or credit prediction')


def read_observation(path):
    records = [json.loads(line) for line in Path(path).read_text().splitlines()]
    if len(records) < 3 or records[0].get('kind') != 'begin' or records[-1].get('kind') != 'end':
        raise ValueError('Incomplete local-service evidence')
    if (not records[-1].get('complete') or records[-1]['rows_before_end'] != len(records)-1
            or any(r.get('kind') in ('begin', 'end') for r in records[1:-1])):
        raise ValueError('Duplicate or truncated observation')
    return records


def plot(events, windows, path, title, focus=None):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    identities = sorted({e['input_identity'] for e in events})
    fig, axes = plt.subplots(2, 1, figsize=(8, 6), sharex=True)
    final_boundary = max(e['cycle'] for e in events)+1
    for identity in identities:
        cycles = sorted(e['cycle']+1 for e in events if e['input_identity'] == identity)
        points = [0, *cycles]; amounts = list(range(len(cycles)+1))
        if cycles[-1] < final_boundary:
            points.append(final_boundary); amounts.append(len(cycles))
        axes[0].step(points, amounts, where='post', label=identity)
        counts = [w['input_counts'].get(identity, 0) for w in windows]
        axes[1].step([w['begin'] for w in windows]+[windows[-1]['end']], counts+[counts[-1]],
                     where='post', label=identity)
    axes[0].set(title=title, ylabel='Cumulative output sink arrivals (flits)')
    axes[1].set(xlabel='Native cycle boundary', ylabel='Flits / fixed window')
    for axis in axes:
        axis.grid(alpha=.25); axis.legend()
        if focus:
            axis.axvspan(*focus, color='grey', alpha=.12)
    fig.tight_layout()
    fig.savefig(path.with_suffix('.svg')); fig.savefig(path.with_suffix('.png'), dpi=160)
    plt.close(fig)


def reconstruct(components, applications, acceptance, output, width=128):
    if not output.is_absolute() or output.exists():
        raise ValueError('Fresh absolute output required')
    accepted = read_json(acceptance)
    cm = read_json(components/'COMPLETE.json'); am = read_json(applications/'COMPLETE.json')
    if (digest(components/'COMPLETE.json') != accepted['component_manifest_sha256'] or
            digest(applications/'COMPLETE.json') != accepted['run_manifest_sha256']):
        raise ValueError('Changed accepted references')
    if (not accepted['passed'] or not cm['complete'] or not am['complete'] or
            (components/'FAILED.json').exists() or (applications/'FAILED.json').exists()):
        raise ValueError('Incomplete reference')
    checked = set(); rows = authenticated(components, cm, 'SUMMARY.json', checked)
    selected = []
    for offset in (0, 509, 3000):
        found = [r for r in rows if (r['name'], r['model'], r['repetition']) ==
                 (f'three-shared-stagger-{offset}', 'S', 0)]
        if len(found) != 1:
            raise ValueError('Missing or duplicated selected component')
        row = found[0]; record = authenticated(components, cm, row['directory']+'/NETWORK_RESULT.json', checked)
        if not record['complete'] or not record['final']['drained'] or object_digest(record['messages']) != row['message_sha256']:
            raise ValueError('Incomplete or changed selected component')
        selected.append((row['name'], record['messages'], 24, 36, None))
    for side, edge, token in ((6, (46, 34), 'first17/phase/4'), (7, (56, 42), 'first21/phase/4')):
        record = authenticated(applications, am, f'{side}-remote_balanced-S-rep-0/execution.json', checked)
        if not record['complete']:
            raise ValueError('Incomplete selected application')
        selected.append((f'{side}-B-critical-output', record['network_messages'], *edge, token))
    output.mkdir(); summaries = []
    for name, messages, router, destination, token in selected:
        events = output_events(messages, router, destination)
        target = [e for e in events if e['token'] == token] if token else []
        if token and not target:
            raise ValueError('Critical token absent at selected output')
        focus = [target[0]['cycle'], target[-1]['cycle']+1] if target else None
        windows = service_windows(events, width)
        directory = output/name; directory.mkdir()
        write_json(directory/'EVENTS.json', events); write_json(directory/'WINDOWS.json', windows)
        with (directory/'windows.csv').open('w', newline='') as stream:
            writer = csv.writer(stream); writer.writerow(['begin', 'end', 'input', 'flits'])
            for w in windows:
                for identity in sorted({e['input_identity'] for e in events}):
                    writer.writerow([w['begin'], w['end'], identity, w['input_counts'].get(identity, 0)])
        plot(events, windows, directory/'output', f'{name}: {router} → {destination}, {width}-cycle windows', focus)
        summaries.append(dict(name=name, router=router, destination=destination,
            output_flits=len(events), input_counts=dict(Counter(e['input_identity'] for e in events)),
            fixed_window_cycles=width, windows=len(windows), critical_token=token,
            critical_sink_arrival_span=focus,
            scope='Observed local arrivals and output sink arrivals; no eligibility inference'))
    write_json(output/'RESULTS.json', dict(cases=summaries, new_native_executions=0, new_application_executions=0))
    repo = Path(__file__).resolve().parents[3]
    write_json(output/'COMPLETE.json', dict(complete=True, source_commit=subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(), artifacts_checked=len(checked),
        source_sha256=digest(Path(__file__).resolve()), component_manifest_sha256=digest(components/'COMPLETE.json'),
        application_manifest_sha256=digest(applications/'COMPLETE.json'),
        artifacts_sha256={str(p.relative_to(output)): digest(p) for p in output.rglob('*') if p.is_file()}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('components', type=Path); parser.add_argument('applications', type=Path)
    parser.add_argument('acceptance', type=Path); parser.add_argument('output', type=Path)
    parser.add_argument('--window-cycles', type=int, default=128)
    args = parser.parse_args()
    reconstruct(args.components, args.applications, args.acceptance, args.output, args.window_cycles)
