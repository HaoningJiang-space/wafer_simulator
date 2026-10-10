"""Independent decoder for explicit-core compact evidence schema 1.

No execution/evidence producer imports, re-solving, Native input or expansion
during prediction. Format validation is not a substitute for reference equality.
"""
from copy import deepcopy

STREAMS = {'service', 'inputs', 'credits', 'credit_sends', 'allocations',
           'injections', 'ejections', 'retired'}
SUMMARY_FIELDS = {'complete', 'drained', 'final_cycle', 'messages', 'event_counts',
    'source_stall_cycles', 'router_credit_stall_cycles', 'queue_peaks', 'native_boundary_inputs'}
MESSAGE_FIELDS = {'id', 'source', 'destination', 'ready', 'generated', 'first_inject',
    'last_inject', 'first_eject', 'last_eject', 'finish', 'flits'}
FLIT_FIELDS = {'id', 'message', 'source', 'destination', 'generated', 'injected', 'ejected',
              'injection_router_arrival', 'router_path', 'link_arrivals', 'hops'}


def natural(value):
    return type(value) is int and value >= 0


def validate_row(name, row):
    if not isinstance(row, dict):
        raise ValueError('Evidence row must be an object')
    if name == 'retired':
        if (set(row) != FLIT_FIELDS or any(not natural(row[k]) for k in
                ('id', 'message', 'source', 'destination', 'generated', 'injected',
                 'ejected', 'injection_router_arrival', 'hops'))
                or not isinstance(row['router_path'], list) or row['hops'] != len(row['router_path'])
                or any(not natural(r) or r > 3 for r in row['router_path'])
                or not isinstance(row['link_arrivals'], list)):
            raise ValueError('Invalid retired flit evidence')
        for arrival in row['link_arrivals']:
            if (set(arrival) != {'source', 'destination', 'cycle', 'vc'}
                    or any(not natural(v) for v in arrival.values()) or arrival['vc'] != 0):
                raise ValueError('Invalid link arrival evidence')
        return
    fields = {
        'inputs': {'router', 'input', 'flit', 'cycle'},
        'credits': {'target', 'number', 'cycle', 'amount'},
        'credit_sends': {'router', 'input', 'cycle', 'amount'},
        'injections': {'message', 'cycle'}, 'ejections': {'message', 'cycle'},
        'allocations': {'router', 'cycle', 'vc_requests', 'sw_requests', 'vc_pointer',
                        'sw_pointer', 'owner', 'credit_slots', 'occupancy', 'heads'}}
    if name == 'service':
        kind = row.get('kind')
        if kind not in ('vc_commit', 'sw_commit', 'output_send'):
            raise ValueError('Unknown service kind')
        required = {'kind', 'router', 'flit', 'cycle'}
        if kind != 'output_send':
            required.add('input')
    else:
        required = fields[name]
    if set(row) != required or not natural(row['cycle']):
        raise ValueError('Invalid evidence row fields')
    if name == 'allocations':
        if (any(not natural(row[k]) for k in ('router', 'cycle', 'vc_pointer', 'sw_pointer', 'credit_slots'))
                or row['owner'] is not None and not natural(row['owner'])
                or any(not isinstance(row[k], list) or any(not natural(v) for v in row[k])
                       for k in ('vc_requests', 'sw_requests', 'occupancy'))
                or not isinstance(row['heads'], list)
                or any(type(v) is not int or v < -1 for v in row['heads'])
                or len(row['heads']) != len(row['occupancy'])):
            raise ValueError('Invalid allocation row')
    elif name == 'credits':
        if row['target'] not in ('router', 'endpoint') or any(
                not natural(row[k]) for k in ('number', 'amount')) or row['amount'] != 1:
            raise ValueError('Invalid credit row')
    elif any(not natural(v) for k, v in row.items() if k != 'kind'):
        raise ValueError('Invalid event integer')


def translate(row, cycles, flits, name):
    """Specified clock/identity translation, independently of the producer."""
    out = deepcopy(row)
    if name == 'retired':
        out['id'] += flits
        for key in ('injected', 'ejected', 'injection_router_arrival'):
            out[key] += cycles
        for arrival in out['link_arrivals']:
            arrival['cycle'] += cycles
    else:
        out['cycle'] += cycles
        if 'flit' in out:
            out['flit'] += flits
        if 'heads' in out:
            out['heads'] = [v+flits if v >= 0 else -1 for v in out['heads']]
    return out


def expand_record(record):
    if (not isinstance(record, dict) or set(record) != {'schema', 'producer', 'summary', 'evidence'}
            or type(record['schema']) is not int or record['schema'] != 1
            or record['producer'] != 'Explicit causal core compact evidence'
            or not isinstance(record['evidence'], dict) or set(record['evidence']) != STREAMS):
        raise ValueError('Complete explicit-core compact evidence required')
    summary = record['summary']
    if (set(summary) != SUMMARY_FIELDS or summary['complete'] is not True
            or summary['drained'] is not True or summary['native_boundary_inputs'] is not False
            or not natural(summary['final_cycle']) or set(summary['event_counts']) != STREAMS
            or any(not natural(v) for v in summary['event_counts'].values())
            or not isinstance(summary['messages'], list) or not summary['messages']):
        raise ValueError('Invalid compact completion summary')
    tables = {}
    for name, segments in record['evidence'].items():
        rows = []
        if not isinstance(segments, list):
            raise ValueError('Invalid stream segments')
        for segment in segments:
            if not isinstance(segment, dict):
                raise ValueError('Invalid stream segment')
            if segment.get('kind') == 'rows' and set(segment) == {'kind', 'rows'}:
                if not isinstance(segment['rows'], list) or not segment['rows']:
                    raise ValueError('Empty/invalid raw evidence segment')
                additions = deepcopy(segment['rows'])
            elif (segment.get('kind') == 'repeat' and set(segment) ==
                    {'kind', 'period', 'flit_stride', 'repetitions', 'template'}
                    and type(segment['period']) is int and segment['period'] == 2
                    and type(segment['flit_stride']) is int and segment['flit_stride'] == 1
                    and type(segment['repetitions']) is int and segment['repetitions'] > 0
                    and isinstance(segment['template'], list) and segment['template']):
                for row in segment['template']:
                    validate_row(name, row)
                additions = [translate(row, 2*i, i, name)
                    for i in range(1, segment['repetitions']+1) for row in segment['template']]
            else:
                raise ValueError('Invalid compact evidence segment')
            for row in additions:
                validate_row(name, row)
            rows.extend(additions)
        if len(rows) != summary['event_counts'][name]:
            raise ValueError('Expanded stream count differs')
        clock = 'ejected' if name == 'retired' else 'cycle'
        if any(rows[i][clock] > rows[i+1][clock] for i in range(len(rows)-1)):
            raise ValueError('Evidence clock order differs')
        tables[name] = rows
    retired = tables['retired']
    if sorted(f['id'] for f in retired) != list(range(len(retired))):
        raise ValueError('Missing/duplicate retired flit identity')
    for name, identity in [('service', lambda r: (r['kind'], r['router'], r['flit'])),
                           ('inputs', lambda r: (r['router'], r['flit'])),
                           ('allocations', lambda r: (r['router'], r['cycle']))]:
        keys = [identity(row) for row in tables[name]]
        if len(set(keys)) != len(keys):
            raise ValueError('Repeated service/allocation identity')
    messages = []
    for mid, message in enumerate(summary['messages']):
        if (set(message) != MESSAGE_FIELDS or any(not natural(v) for v in message.values())
                or message['id'] != mid or message['flits'] <= 0 or message['destination'] != 3):
            raise ValueError('Invalid compact message inventory')
        flits = sorted((f for f in retired if f['message'] == mid), key=lambda f: (f['ejected'], f['id']))
        injections = [r['cycle'] for r in tables['injections'] if r['message'] == mid]
        ejections = [r['cycle'] for r in tables['ejections'] if r['message'] == mid]
        if (len(flits) != message['flits'] or injections != sorted(f['injected'] for f in flits)
                or ejections != [f['ejected'] for f in flits]
                or any(f['generated'] != message['generated'] or f['source'] != message['source']
                       or f['destination'] != message['destination'] for f in flits)
                or [injections[0], injections[-1], ejections[0], ejections[-1], ejections[-1]+1] !=
                   [message[k] for k in ('first_inject', 'last_inject', 'first_eject', 'last_eject', 'finish')]):
            raise ValueError('Message progress/time evidence differs')
        messages.append(dict(message, flits=flits))
    if any(f['message'] >= len(messages) for f in retired) or any(
            r['message'] >= len(messages) for name in ('injections', 'ejections') for r in tables[name]):
        raise ValueError('Unknown message identity')
    return dict(complete=True, drained=True, final_cycle=summary['final_cycle'], messages=messages,
        service=tables['service'], input_arrivals=tables['inputs'], credit_returns=tables['credits'],
        credit_sends=tables['credit_sends'], allocations=tables['allocations'],
        source_stall_cycles=deepcopy(summary['source_stall_cycles']),
        router_credit_stall_cycles=deepcopy(summary['router_credit_stall_cycles']),
        queue_peaks=deepcopy(summary['queue_peaks']), native_boundary_inputs=False,
        processed_cycles=summary['final_cycle'],
        scope='Independent bounded four-router G1 prediction; no service compression')
