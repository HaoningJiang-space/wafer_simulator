"""Observed critical intervals, supply overlap and unmodeled DMA demand.

No simulation, alternate ready clocks, fitted parameters or counterfactual
completion times. Half-open intervals describe the recorded execution only.
"""
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import fields
import statistics


def union(intervals):
    merged = []
    for begin, end in sorted(intervals):
        if begin > end: raise ValueError('Reversed interval')
        if begin == end: continue
        if merged and begin <= merged[-1][1]: merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else: merged.append((begin, end))
    return merged


def duration(intervals):
    return sum(end-begin for begin, end in union(intervals))


def overlap(first, second):
    a, b = union(first), union(second); i = j = total = 0
    while i < len(a) and j < len(b):
        total += max(0, min(a[i][1], b[j][1])-max(a[i][0], b[j][0]))
        if a[i][1] <= b[j][1]: i += 1
        else: j += 1
    return total


def interval_profile(rows):
    """Logical lifetimes; release before reuse at an integer boundary."""
    events = defaultdict(list)
    for r in rows:
        if (type(r['start']) is not int or type(r['finish']) is not int or
                not 0 <= r['start'] < r['finish'] or type(r['bytes']) is not int or r['bytes'] < 0):
            raise ValueError('Invalid lifetime/byte count')
        events[r['start']].append((1, r)); events[r['finish']].append((-1, r))
    active = {}; size = peak_count = peak_bytes = previous = area = 0
    witness_count = witness_bytes = None
    for cycle, changes in sorted(events.items()):
        area += len(active)*(cycle-previous)
        for delta, r in sorted(changes, key=lambda x: x[0]):
            key = r['id']
            if delta < 0:
                if key not in active: raise ValueError('Release without a lifetime')
                size -= active.pop(key)['bytes']
            else:
                if key in active: raise ValueError('Overlapping/repeated lifetime identity')
                active[key] = r; size += r['bytes']
        if len(active) > peak_count:
            peak_count = len(active); witness_count = dict(cycle=cycle, active=sorted(active))
        if size > peak_bytes:
            peak_bytes = size; witness_bytes = dict(cycle=cycle, active=sorted(active))
        previous = cycle
    if active or size: raise ValueError('Unclosed logical lifetimes')
    return dict(peak_count=peak_count, peak_useful_bytes=peak_bytes, position_cycle_integral=area,
                count_witness=witness_count, bytes_witness=witness_bytes)


def weighted_profile(events):
    """Delivered useful bytes minus atomic destination commits, no FIFO claim."""
    changes = Counter()
    for cycle, amount in events:
        if type(cycle) is not int or cycle < 0 or type(amount) is not int: raise ValueError('Invalid receive event')
        changes[cycle] += amount
    current = peak = previous = area = 0; at = None
    for cycle, amount in sorted(changes.items()):
        area += current*(cycle-previous); current += amount
        if current < 0: raise ValueError('Committed bytes not yet received')
        if current > peak: peak = current; at = cycle
        previous = cycle
    if current: raise ValueError('Uncommitted/missing receive bytes')
    return dict(peak_useful_bytes=peak, peak_cycle=at, useful_byte_cycle_integral=area)


def order_inversions(first, second):
    """Exact pair-order changes on the same semantic packet set."""
    if len(set(first)) != len(first) or len(set(second)) != len(second) or set(first) != set(second):
        raise ValueError('Packet order comparison needs the same unique semantic keys')
    positions = {key: i+1 for i, key in enumerate(first)}; tree = [0]*(len(first)+1); total = 0
    for seen, key in enumerate(second):
        index = positions[key]; before = 0; cursor = index
        while cursor: before += tree[cursor]; cursor -= cursor & -cursor
        total += seen-before
        while index < len(tree): tree[index] += 1; index += index & -index
    pairs = len(first)*(len(first)-1)//2
    return dict(packets=len(first), reversed_pairs=total, pairs=pairs,
                reversed_pair_fraction=total/pairs if pairs else 0)


def transaction_key(t):
    return f"{t['operation']}:{t['data']}:{t['kind']}:{t['source']}->{t['destination']}"


def fragments(t):
    if 'chunks' in t: return t['chunks']
    return [dict(ordinal=0, offset=0, bytes=t['bytes'],
        source_phase=t['first_phase']+2 if t['kind'] == 'read' else t['first_phase'],
        channel_phase=t['first_phase']+3 if t['kind'] == 'read' else t['payload_phase']+1 if t['kind'] == 'write' else None,
        payload_phase=t['payload_phase'], destination_phase=t['ack_phase']-1 if t['kind'] == 'write' else t['last_phase'])]


def message_tags(transactions, compiled):
    stores = {s.id: s for s in compiled.physical.stores}; tags = {}; phase_tx = {}
    for t in transactions:
        key = transaction_key(t); op = t['operation']
        for i in range(t['first_phase'], t['last_phase']+1): phase_tx[f'{op}/phase/{i}'] = key
        source_kind = stores[t['source']].kind; dest_kind = stores[t['destination']].kind
        role = source_kind+'_response' if t['kind'] == 'read' else dest_kind+'_write' if t['kind'] == 'write' else 'c2c'
        for c in fragments(t):
            tags[f"{op}/phase/{c['payload_phase']}"] = dict(transaction=key, role=role, offset=c['offset'], ordinal=c['ordinal'])
        if t['request_phase'] is not None:
            tags[f"{op}/phase/{t['request_phase']}"] = dict(transaction=key, role=source_kind+'_request', offset=0, ordinal=None)
        if t['ack_phase'] is not None:
            tags[f"{op}/phase/{t['ack_phase']}"] = dict(transaction=key, role=dest_kind+'_ack', offset=0, ordinal=None)
    return tags, phase_tx


def network_slices(message):
    clocks = [message[k] for k in ('ready', 'generated', 'first_inject', 'last_inject', 'finish')]
    if any(a > b for a, b in zip(clocks, clocks[1:])): raise ValueError('Native network clock order')
    return dict(zip(('source_generation_wait', 'first_injection_wait', 'injection_span', 'completion_tail'),
                    (b-a for a, b in zip(clocks, clocks[1:]))))


def chain_accounting(result, chain, tags, phase_tx):
    messages = {m['token']: m for m in result['network_messages']}; total = Counter(); slices = Counter()
    by_transaction = Counter(); selected = []; annotated = []; cursor = 0
    for segment in chain['segments']:
        if segment['start'] != cursor or segment['finish']-segment['start'] != segment['duration']:
            raise ValueError('Critical intervals do not partition application time')
        cursor = segment['finish']; category = segment['category']; token = segment.get('token')
        if category == 'network':
            message = messages[token]; tag = tags[token]; bucket = 'network/'+tag['role']
            if (message['ready'], message['finish']) != (segment['start'], segment['finish']):
                raise ValueError('Critical network interval differs from message')
            parts = network_slices(message)
            if sum(parts.values()) != segment['duration']: raise ValueError('Network slices do not close')
            slices.update(parts)
            selected.append(dict(token=token, **tag, **parts, duration=segment['duration'],
                                 ready=message['ready'], finish=message['finish'], bytes=message['bytes']))
        elif category in {'memory', 'compute'}:
            point = segment['point'].split(':'); event = result['services'][int(point[1])]
            resource = event['resource']; trailing = point[-1] == 'finish'
            if category == 'compute': bucket = 'compute'
            elif resource.endswith('/command'): bucket = 'controller_command'
            elif resource.endswith('/channel'): bucket = 'controller_channel'
            elif resource.startswith('dram-'): bucket = 'dram_bank_latency' if trailing else 'dram_bank_serialize'
            elif resource.startswith('host-memory/'): bucket = 'external_store_latency' if trailing else 'external_store_serialize'
            elif resource.startswith('sram-'): bucket = 'sram'
            else: raise ValueError('Unknown critical service resource: '+resource)
        else: bucket = category
        total[bucket] += segment['duration']
        key = phase_tx.get(token, 'ordinary/'+segment['operation'])
        by_transaction[key] += segment['duration']
        annotated.append(dict(segment, accounting_bucket=bucket, transaction=key))
    if cursor != result['application_cycles'] or sum(total.values()) != cursor:
        raise ValueError('Critical accounting does not equal makespan')
    return dict(application_cycles=cursor, totals=dict(total), network_slices=dict(slices),
                by_transaction=dict(by_transaction), selected_messages=selected, annotated_segments=annotated,
                terminal_operations=sorted(op for op, r in result['operations'].items() if r['finish'] == cursor),
                scope='One observed execution/resource critical chain; opaque network durations; accounting, not causal intervention')


def interface_name(compiled, endpoint):
    interfaces = getattr(compiled.target, 'network_interfaces', ())
    if interfaces: return next(i.id for i in interfaces if i.endpoint == endpoint)
    return next(m.id+'/nic' for m in compiled.target.memory if m.endpoint == endpoint)


def supply_and_dma(compiled, transactions, result):
    phases = {(p['operation'], p['phase']): p for p in result['phases']}
    services = defaultdict(list)
    for e in result['services']: services[e['token']].append(e)
    messages = {m['token']: m for m in result['network_messages']}
    stores = {s.id: s for s in compiled.physical.stores}
    controllers = {c.id: c for c in compiled.physical.controllers}
    demand = {c: dict(fragment_positions=[], descriptor_proxy=[], transactions_outstanding=[]) for c in controllers}
    rx_events = defaultdict(list); movement = []; window_max = 0
    for t in transactions:
        key = transaction_key(t); op = t['operation']; chunks = fragments(t)
        group = [phases[op, i] for i in range(t['first_phase'], t['last_phase']+1)]
        events = [e for i in range(t['first_phase'], t['last_phase']+1) for e in services[f'{op}/phase/{i}']]
        periphery = t['source'] if t['kind'] == 'read' else t['destination'] if t['kind'] == 'write' else None
        array = [(e['start'], e['resource_released']) for e in events if periphery and e['resource'] == periphery+'/port']
        channel = [(e['start'], e['resource_released']) for e in events if t['controller'] and e['resource'] == t['controller']+'/channel']
        payload = [messages[f"{op}/phase/{c['payload_phase']}"] for c in chunks]
        pending = [(m['ready'], m['finish']) for m in payload]
        injections = [(m['first_inject'], m['last_inject']+1) for m in payload]
        begin = min(p['ready'] for p in group); finish = max(p['finish'] for p in group)
        positions = []
        for c, m in zip(chunks, payload):
            commit = phases[op, c['destination_phase']]['finish']
            position = dict(id=key+f"/fragment/{c['ordinal']}", start=phases[op, c['source_phase']]['ready'],
                            finish=commit, bytes=c['bytes'])
            positions.append(position)
            # Each native flit is a packet; sorted IDs give its byte ordinal in
            # the generated message, even if arrivals are out of order.
            name = interface_name(compiled, m['destination'])
            useful = 0
            for j, flit in enumerate(sorted(m['flits'], key=lambda f: f['id'])):
                amount = min(m['flit_bytes'], m['bytes']-j*m['flit_bytes'])
                if amount <= 0 or flit['ejected']+1 > commit: raise ValueError('Invalid receive/commit coverage')
                useful += amount; rx_events[name].append((flit['ejected']+1, amount))
            if useful != c['bytes']: raise ValueError('Receive useful-byte conservation')
            rx_events[name].append((commit, -c['bytes']))
        observed = interval_profile(positions)
        if 'chunks' in t:
            window_max = max(window_max, observed['peak_count'])
            if observed['peak_count'] > 4: raise ValueError('Frozen per-transaction window exceeded')
        if t['controller']:
            d = demand[t['controller']]; d['fragment_positions'].extend(positions)
            command = t['command_phase'] if 'chunks' in t else t['request_phase']+1 if t['kind'] == 'read' else t['payload_phase']+1
            final_commit = max(phases[op, c['destination_phase']]['finish'] for c in chunks)
            d['descriptor_proxy'].append(dict(id=key, start=phases[op, command]['ready'], finish=final_commit, bytes=0))
            d['transactions_outstanding'].append(dict(id=key, start=begin, finish=finish, bytes=0))
        movement.append(dict(transaction=key, operation=op, data=t['data'], kind=t['kind'],
            periphery_kind=stores[periphery].kind if periphery else None, controller=t['controller'], bytes=t['bytes'],
            ready=begin, finish=finish, duration=finish-begin, fragments=len(chunks),
            first_payload_ready=min(m['ready'] for m in payload),
            first_payload_offset=min(m['ready'] for m in payload)-begin,
            payload_release_span=max(m['ready'] for m in payload)-min(m['ready'] for m in payload),
            payload_completion_envelope=max(m['finish'] for m in payload)-min(m['ready'] for m in payload),
            bank_busy_cycles=duration(array), channel_busy_cycles=duration(channel),
            bank_channel_overlap_cycles=overlap(array, channel),
            bank_network_pending_overlap_cycles=overlap(array, pending),
            bank_injection_envelope_overlap_cycles=overlap(array, injections),
            per_transaction_window_peak=observed['peak_count']))
    dma = {}
    for controller, groups in demand.items():
        dma[controller] = {name: interval_profile(rows) for name, rows in groups.items()}
        dma[controller].update(staging_reserved_peak_bytes=result['peak_bytes'][controller+'/buffer'],
                               staging_capacity_bytes=controllers[controller].buffer_bytes,
                               hardware_descriptor_limit=None, hardware_fragment_limit=None)
    rx = {name: dict(weighted_profile(events), hardware_rx_limit_bytes=None,
                    scope='Useful delivered/uncommitted byte envelope; atomic commit; not certified FIFO residency')
          for name, events in rx_events.items()}
    return dict(movements=movement, dma_by_controller=dma, rx_by_interface=rx, per_transaction_fragment_max=window_max,
                controller_dataclass_fields=[f.name for f in fields(next(iter(controllers.values())))],
                descriptor_contract='unmodeled; command-ready to final destination commit is a proxy lifetime',
                aggregate_fragment_contract='unmodeled; summed positions are associated end-to-end demand, not local residency',
                rx_contract='uncertified; native credit return is not coupled to destination commit')


def network_profile(compiled, result, tags, selected_messages, bin_cycles):
    edges = defaultdict(list); source_order = defaultdict(list); facts = {}; bins = defaultdict(Counter)
    role_slices = defaultdict(list)
    for m in result['network_messages']:
        tag = tags[m['token']]; role = tag['role']; width = m['flit_bytes']
        if tag['offset'] % width: raise ValueError('Semantic flit matching needs aligned frozen fragments')
        bins[role, m['ready']//bin_cycles]['released_flits'] += len(m['flits'])
        bins[role, m['ready']//bin_cycles]['released_useful_bytes'] += m['bytes']
        role_slices[role].append(network_slices(m))
        name = interface_name(compiled, m['source'])
        for ordinal, f in enumerate(sorted(m['flits'], key=lambda f: f['id'])):
            key = (tag['transaction'], role, tag['offset']//width+ordinal)
            if key in facts: raise ValueError('Repeated semantic flit')
            facts[key] = dict(source=name, injected=f['injected'], generated=f['generated'], ejected=f['ejected'],
                              route=tuple(f['router_path']))
            source_order[name].append((f['injected'], key))
            bins[role, f['injected']//bin_cycles]['injected_flits'] += 1
            for e in f['link_arrivals']:
                edges[e['source'], e['destination']].append((e['cycle'], tag['transaction'], m['token'], role))
    for events in edges.values(): events.sort()
    edge_times = {edge: [e[0] for e in events] for edge, events in edges.items()}
    messages = {m['token']: m for m in result['network_messages']}; windows = []
    for selected in selected_messages:
        m = messages[selected['token']]; own = defaultdict(list)
        for f in m['flits']:
            for e in f['link_arrivals']: own[e['source'], e['destination']].append(e['cycle'])
        for edge, times in own.items():
            begin, end = min(times), max(times); events = edges[edge]
            present = events[bisect_left(edge_times[edge], begin):bisect_right(edge_times[edge], end)]
            peers = Counter(tx for _, tx, token, _ in present if tx != selected['transaction'])
            sibling = sum(token != m['token'] and tx == selected['transaction'] for _, tx, token, _ in present)
            if len(present) > end-begin+1: raise ValueError('Directed-link capacity violated')
            windows.append(dict(token=m['token'], transaction=selected['transaction'], role=selected['role'],
                source=edge[0], destination=edge[1], first_arrival=begin, last_arrival=end,
                own_flits=len(times), sibling_fragment_flits=sibling, other_transaction_flits=sum(peers.values()),
                other_transactions=len(peers), peer_transactions=dict(peers),
                link_activity=len(present)/(end-begin+1),
                scope='Actual flits in this message link-use window; no queue-delay attribution'))
    summaries = {role: dict(messages=len(rows), **{name+'_median_cycles': statistics.median(r[name] for r in rows)
                 for name in ('source_generation_wait', 'first_injection_wait', 'injection_span', 'completion_tail')},
                 source_generation_wait_max_cycles=max(r['source_generation_wait'] for r in rows))
                 for role, rows in role_slices.items()}
    report = dict(native_messages=len(messages), wire_packets=len(facts), wire_packet_flits=1,
        message_slices_by_role=summaries, critical_link_windows=windows,
        activity_bins=[dict(role=role, bin_index=b, begin_cycle=b*bin_cycles, end_cycle=(b+1)*bin_cycles, **values)
                       for (role, b), values in sorted(bins.items())],
        scope='Observed post-execution routes, release batches and source injection order')
    return report, facts, {name: [key for _, key in sorted(rows)] for name, rows in source_order.items()}


def compare_packet_facts(first, second, first_order, second_order):
    if set(first) != set(second) or set(first_order) != set(second_order): raise ValueError('Different semantic packet/source sets')
    paths = defaultdict(Counter); source = {}
    for key, a in first.items():
        b = second[key]
        if a['source'] != b['source']: raise ValueError('Organization changed in policy comparison')
        role = key[1]; paths[role]['packets'] += 1
        paths[role]['route_changed_packets'] += a['route'] != b['route']
        paths[role]['generated_clock_changed_packets'] += a['generated'] != b['generated']
        paths[role]['injection_clock_changed_packets'] += a['injected'] != b['injected']
    for name in first_order: source[name] = order_inversions(first_order[name], second_order[name])
    return dict(semantic_packets=len(first), by_role={r: dict(c) for r, c in paths.items()},
        source_injection_order=source, reversed_pairs=sum(r['reversed_pairs'] for r in source.values()),
        comparable_pairs=sum(r['pairs'] for r in source.values()),
        scope='Paired actual executions with different ready times; no isolated batching/overlap intervention')
