"""Pure saved-trace summaries/figures; private orchestration lives in experiments."""
from collections import defaultdict
import statistics
from wafer_sim.analysis.periphery_attribution import fragments, transaction_key


def summary(profile):
    supply = profile['supply']; controllers = supply['dma_by_controller']; rx = supply['rx_by_interface']
    groups = defaultdict(list)
    for m in supply['movements']: groups[m['kind']+'/'+str(m['periphery_kind'])].append(m)
    metrics = ('duration', 'first_payload_offset', 'payload_release_span', 'payload_completion_envelope',
               'bank_channel_overlap_cycles', 'bank_network_pending_overlap_cycles')
    peaks = {name: max((r[name]['peak_count'] for r in controllers.values()), default=0)
             for name in ('fragment_positions', 'descriptor_proxy', 'transactions_outstanding')}
    witnesses = {name: [c for c, r in controllers.items() if r[name]['peak_count'] == peaks[name]] for name in peaks}
    return dict(application_cycles=profile['chain']['application_cycles'], chain=profile['chain']['totals'],
        critical_network_slices=profile['chain']['network_slices'], terminal_operations=profile['chain']['terminal_operations'],
        selected_network_messages=profile['chain']['selected_messages'],
        transactions={kind: dict(count=len(rows), **{name+'_median': statistics.median(r[name] for r in rows) for name in metrics})
                      for kind, rows in groups.items()},
        controller_peak_counts=peaks, peak_controllers=witnesses,
        controller_demand={c: dict(fragment_positions=r['fragment_positions']['peak_count'],
            associated_fragment_useful_bytes=r['fragment_positions']['peak_useful_bytes'],
            descriptor_proxy=r['descriptor_proxy']['peak_count'], transactions_outstanding=r['transactions_outstanding']['peak_count'],
            reserved_staging_peak_bytes=r['staging_reserved_peak_bytes'], staging_capacity_bytes=r['staging_capacity_bytes'])
            for c, r in controllers.items()},
        per_transaction_fragment_peak=supply['per_transaction_fragment_max'],
        receive_envelope_peak_bytes=max((r['peak_useful_bytes'] for r in rx.values()), default=0),
        receive_envelope_by_interface=rx,
        native_messages=profile['network']['native_messages'], wire_packets=profile['network']['wire_packets'],
        message_slices_by_role=profile['network']['message_slices_by_role'],
        native_protocol_commands=profile['native_protocol_commands'])


def match_movements(first, second):
    a = {r['transaction']: r for r in first}; b = {r['transaction']: r for r in second}
    if set(a) != set(b): raise ValueError('Movement identities changed')
    metrics = ('ready', 'finish', 'duration', 'first_payload_offset', 'first_payload_ready',
               'payload_release_span', 'payload_completion_envelope', 'bank_channel_overlap_cycles',
               'bank_network_pending_overlap_cycles')
    return [dict(transaction=k, kind=a[k]['kind'], periphery_kind=a[k]['periphery_kind'],
                 whole={name: a[k][name] for name in metrics}, pipeline={name: b[k][name] for name in metrics},
                 delta={name: b[k][name]-a[k][name] for name in metrics}) for k in a]


def timeline(tx, result):
    token_set = {f"{tx['operation']}/phase/{i}" for i in range(tx['first_phase'], tx['last_phase']+1)}
    rows = []
    for e in result['services']:
        if e['token'] not in token_set: continue
        resource = e['resource']
        if resource.startswith('dram-'): lane = 'bank'
        elif resource.endswith('/channel'): lane = 'channel'
        elif resource.startswith('sram-'): lane = 'destination'
        else: continue
        rows.append(dict(lane=lane, start=e['start'], finish=e['resource_released'], kind='serialize'))
        if lane == 'bank' and e['finish'] > e['resource_released']:
            rows.append(dict(lane=lane, start=e['resource_released'], finish=e['finish'], kind='latency'))
    messages = {m['token']: m for m in result['network_messages']}
    for c in fragments(tx):
        m = messages[f"{tx['operation']}/phase/{c['payload_phase']}"]
        rows.append(dict(lane='network', start=m['ready'], finish=m['finish'], kind='pending', fragment=c['ordinal']))
        if m['generated'] > m['ready']:
            rows.append(dict(lane='generation_queue', start=m['ready'], finish=m['generated'], kind='waiting'))
    begin = min(p['ready'] for p in result['phases'] if p['operation'] == tx['operation'] and
                tx['first_phase'] <= p['phase'] <= tx['last_phase'])
    return dict(transaction=transaction_key(tx), ready=begin, intervals=rows)


def make_figures(output, cells, timelines):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    labels = ['A / whole', 'A / pipeline', 'B / whole', 'B / pipeline']
    keys = [f'{c}/{layout}' for layout in ('clustered_local', 'remote_balanced') for c in ('shared_whole', 'shared_pipeline')]
    categories = ['compute', 'sram', 'dram_bank_serialize', 'dram_bank_latency', 'controller_channel', 'controller_command', 'external_store']
    colors = ['#555555', '#aab7c4', '#ce8c30', '#ebc38b', '#9b61b0', '#78509b', '#52a49c', '#327cb7']
    fig, ax = plt.subplots(figsize=(10, 4.1)); left = [0]*4
    for color, category in zip(colors, categories):
        values = [sum(v for k, v in cells[key]['chain'].items() if (k.startswith('external_store') if category == 'external_store' else k == category)) for key in keys]
        ax.barh(labels, values, left=left, color=color, label=category.replace('_', ' ')); left = [a+b for a, b in zip(left, values)]
    values = [sum(v for k, v in cells[key]['chain'].items() if k.startswith('network/')) for key in keys]
    ax.barh(labels, values, left=left, color=colors[-1], label='network elapsed')
    for i, key in enumerate(keys): ax.text(cells[key]['application_cycles']+180, i, str(cells[key]['application_cycles']), va='center', fontsize=9)
    ax.set_xlim(0, 35000); ax.invert_yaxis(); ax.set_xlabel('Cycles on one observed execution/resource critical chain')
    ax.set_title('Policy changes critical exposure; these are accounting intervals, not causal contributions')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.22), ncol=4, fontsize=8, frameon=False); fig.subplots_adjust(bottom=.32, left=.14, right=.97)
    fig.savefig(output/'critical_chain.png', dpi=160); fig.savefig(output/'critical_chain.svg'); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.8), sharex=True)
    lanes = ['bank', 'channel', 'generation_queue', 'network', 'destination']; lane_colors = dict(zip(lanes, ['#ce8c30', '#9b61b0', '#cc7777', '#327cb7', '#aab7c4']))
    for ax, condition in zip(axes, ('shared_whole', 'shared_pipeline')):
        t = timelines[condition]
        for r in t['intervals']:
            y = lanes.index(r['lane']); color = '#f0ddbc' if r['kind'] == 'latency' else lane_colors[r['lane']]
            ax.broken_barh([(r['start']-t['ready'], r['finish']-r['start'])], (y-.32, .64), facecolors=color, edgecolors='white', linewidth=.3)
            if r['lane'] == 'network' and r.get('fragment') in (0, 3, 7, 11, 15):
                ax.text((r['start']+r['finish'])/2-t['ready'], y, str(r['fragment']), color='white', fontsize=8, ha='center', va='center')
        ax.set_yticks(range(len(lanes)), ['Bank serializer + pale trailing latency', 'Controller channel serializer', 'Source generation wait', 'Network message pending', 'Destination SRAM serializer'], fontsize=8)
        ax.invert_yaxis(); ax.set_title(condition+' — observed first17:w17 read', fontsize=10); ax.grid(axis='x', alpha=.2)
    axes[-1].set_xlabel('Cycles from this transaction launch; pending includes generation wait, rows must not be added')
    fig.subplots_adjust(left=.28, bottom=.12, hspace=.35, right=.98); fig.savefig(output/'supply_timeline.png', dpi=160)
    fig.savefig(output/'supply_timeline.svg'); plt.close(fig)


def report(output, cells, packets, differences, checks, elapsed):
    lines = ['# Frozen memory-periphery traces: critical chain and DMA contract', '',
        'All 18 accepted applications are reaudited. No simulation or model/policy change.',
        'The available traces support changed supply timing and overlap; they do not',
        'uniquely partition the relative 2,442-cycle benefit into independent causes.', '',
        '![Observed critical accounting](critical_chain.png)', '',
        '| Layout / shared-interface policy | Compute | Memory | Network elapsed | Makespan |',
        '|---|---:|---:|---:|---:|']
    for layout, label in (('clustered_local', 'A'), ('remote_balanced', 'B')):
        for condition in ('shared_whole', 'shared_pipeline'):
            cell = cells[condition+'/'+layout]; chain = cell['chain']; network = sum(v for k, v in chain.items() if k.startswith('network/'))
            lines.append(f"| {label} / {condition} | {chain.get('compute', 0)} | {sum(chain.values())-chain.get('compute', 0)-network} | {network} | {cell['application_cycles']} |")
    lines.extend(['', 'These columns partition one observed execution/resource critical chain. Network',
        'durations remain opaque. Chains change selected operations/fragments; subtraction',
        'is accounting, not an intervention or independent delay attribution.', '',
        '| Critical bucket | A whole | A pipeline | A difference | B whole | B pipeline | B difference |',
        '|---|---:|---:|---:|---:|---:|---:|'])
    buckets = sorted(set().union(*(r['chain'] for key, r in cells.items() if key.startswith('shared_'))))
    for bucket in buckets:
        a, ap, b, bp = [cells[key]['chain'].get(bucket, 0) for key in
            ('shared_whole/clustered_local', 'shared_pipeline/clustered_local', 'shared_whole/remote_balanced', 'shared_pipeline/remote_balanced')]
        lines.append(f'| {bucket} | {a} | {ap} | {ap-a} | {b} | {bp} | {bp-b} |')
    lines.extend(['', '![Observed B supply timing](supply_timeline.png)', '',
        '| DRAM read medians | Transaction duration | First payload offset | Release span | Bank/channel busy overlap | Bank/network-pending overlap |',
        '|---|---:|---:|---:|---:|---:|'])
    for layout, label in (('clustered_local', 'A'), ('remote_balanced', 'B')):
        for condition in ('shared_whole', 'shared_pipeline'):
            r = cells[condition+'/'+layout]['transactions']['read/dram']
            values = [r[k+'_median'] for k in ('duration', 'first_payload_offset', 'payload_release_span', 'bank_channel_overlap_cycles', 'bank_network_pending_overlap_cycles')]
            lines.append(f"| {label} / {condition} | "+' | '.join(str(v) for v in values)+' |')
    lines.extend(['', 'Earlier first supply and serializer/network overlap are observed, including',
        'external-controller traffic. A read-duration median can increase while',
        'application time falls: peer bank serializers and alternative dependencies',
        'can control the selected chain. Neither sum of medians nor overlap area',
        'is an application-time causal decomposition.', '',
        'The frozen native trace injection branch uses one-flit packets (head and tail',
        'both true), batching a ready message when the source partial queue is empty.',
        '254 versus 1,445 messages changes release/generation batches, not wire packet',
        'size: both transmit 92,525 single-flit packets. Exact source-order comparisons:', '',
        '| Layout | Semantic packets | Reversed source-order pairs | Comparable pairs | DRAM-response routes changed |',
        '|---|---:|---:|---:|---:|'])
    for layout, p in packets.items():
        lines.append(f"| {layout} | {p['semantic_packets']} | {p['reversed_pairs']} | {p['comparable_pairs']} | {p['by_role']['dram_response']['route_changed_packets']} / {p['by_role']['dram_response']['packets']} |")
    lines.extend(['', 'Source order is compared between actual complete executions with different',
        'ready times, so it does not isolate message batching from supply/overlap.',
        'Critical directed-link windows separately distinguish target, sibling',
        'fragments and other transactions. They demonstrate actual sharing, but',
        'cannot translate peer flits into a unique number of queue-delay cycles.', '',
        '| Shared pipeline layout | Max per-transaction fragments | Max controller-associated positions | Max descriptor-lifetime proxy | Max receive byte envelope |',
        '|---|---:|---:|---:|---:|'])
    for layout in ('clustered_local', 'remote_balanced'):
        c = cells['shared_pipeline/'+layout]
        lines.append(f"| {layout} | {c['per_transaction_fragment_peak']} | {c['controller_peak_counts']['fragment_positions']} | {c['controller_peak_counts']['descriptor_proxy']} | {c['receive_envelope_peak_bytes']} |")
    lines.extend(['', 'The four-position window is per transaction. Summed positions include queued',
        'source service and remote network/destination work; they are associated',
        'end-to-end demand, not proven controller-resident buffer/descriptor usage.',
        'The descriptor proxy counts command-ready to final destination commit,',
        'one explicitly assumed lifetime. Hardware may use another lifetime or more',
        'than one descriptor per transaction. Existing staging reservations remain',
        'within their declared capacities; they do not enforce either count budget.', '',
        'Receive envelope adds useful bytes at native ejection+1 and subtracts a',
        'fragment at destination commit. It includes partial fragments and excludes',
        'padding. Partial consumption during serialization is not recorded, and',
        'these native command streams contain no boundary/supply/commit commands.',
        'Endpoint credit return is not tied to SRAM/bank commit. This is not an',
        'RX FIFO capacity certification or a hardware sizing recommendation.', '',
        'User confirms no target hardware descriptor, outstanding-fragment or RX',
        'budget. All three contract checks remain unmodeled/uncertified; no finite',
        'budget is invented and no recorded run is reclassified against one.', '',
        'Retain v1 whole and shared pipeline as declared candidates. No hardware-',
        'based principal contract is selected. v1 remains the numerical reference',
        'for its registered D1 experiment only; D1 is unchanged and its applications',
        'remain deferred. A future hardware contract must specify descriptor',
        'lifetime/ownership, controller-wide issue and window limits, and RX storage',
        'with commit/backpressure before selecting a principal target.', '',
        f"Verified {checks['artifact_hashes_checked']} raw artifact hashes, {checks['applications_reaudited']} applications and their existing chains; {checks['tests']} new reader regressions pass. Analysis wall {elapsed:.3f} s; zero new simulations. Large profiles, matched movements and activity tables stay at `{output}`."])
    (output/'REVIEW.md').write_text('\n'.join(lines)+'\n')


if __name__ == '__main__':
    raise SystemExit('Private study entry moved to: python -m wafer_sim.experiments.periphery_attribution')
