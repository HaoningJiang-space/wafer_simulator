"""Independent byte, packet, event and endpoint capacity readback."""
from collections import defaultdict


def audit_move(phase, row, move, message, services, ready):
    t=phase.transfer;token=move['token'];expected=set()
    if (row['kind']!='memory_network' or row['ready']!=ready or move['ready']!=ready or
        row['finish']!=move['finish'] or message['ready']!=ready or
        message['source']!=t.source_endpoint or message['destination']!=t.destination_endpoint or
        message['bytes']!=t.size_bytes or move['bytes']!=t.size_bytes or
        message['data']!=t.data or message['source_memory']!=t.source_memory or
        message['destination_memory']!=t.destination_memory or row['network_token']!=token):
        raise ValueError('Movement differs from logical phase')
    packets=move['packets'];flits=sorted(message['flits'],key=lambda f:(f['injected'],f['id']))
    if len(packets)!=len(flits) or sum(p['bytes'] for p in packets)!=t.size_bytes:
        raise ValueError('Movement payload not conserved')
    for k,(p,f) in enumerate(zip(packets,flits)):
        if p['ordinal']!=k or p['bytes']!=min(message['flit_bytes'],t.size_bytes-k*message['flit_bytes']):
            raise ValueError('Chunk identity or valid payload differs')
        for kind,port in (('read',phase.demands[0].resource),('write',phase.demands[1].resource)):
            name=f'{token}/{kind}/{k}';expected.add(name);rows=services[name]
            if (len(rows)!=1 or rows[0]['resource']!=port or rows[0]['amount']!=p['bytes'] or
                    rows[0]['unit']!='bytes' or rows[0]['category']!='memory' or rows[0]['step']!=0):
                raise ValueError('Chunk memory service missing or duplicated')
            event=rows[0]
            if kind=='read':
                if event['ready']!=p['reserved'] or event['finish']!=p['supplied']:
                    raise ValueError('Supply is not the completed read')
            elif event['ready']!=p['received'] or event['finish']!=p['committed']:
                raise ValueError('Commit is not the completed destination write')
        if not ready<=p['reserved']<p['supplied']<=f['injected']<p['injected']<=p['received']<p['committed']:
            raise ValueError('Premature injection, receive or commit')
        if p['flit']!=f['id'] or p['injected']!=f['injected']+1 or p['received']!=f['ejected']+1:
            raise ValueError('Endpoint progress differs from native packet')
    if move['finish']!=max(p['committed'] for p in packets) or move['committed']!=t.size_bytes:
        raise ValueError('Movement completed before full object commit')
    return expected


def audit_occupancy(boundary):
    moves={m['token']:m for m in boundary['moves']}
    tx=defaultdict(int);rx=defaultdict(int);peak_tx=defaultdict(int);peak_rx=defaultdict(int)
    seen=defaultdict(list);last=0
    for event in boundary['events']:
        m=moves[event['token']];p=m['packets'][event['ordinal']]
        key=event['token'],event['ordinal'];kind=event['event']
        order=['tx_reserve','supply','inject','receive','commit']
        if seen[key]!=order[:len(seen[key])] or len(seen[key])>=5 or kind!=order[len(seen[key])]:
            raise ValueError('Packet boundary events incomplete, repeated or reordered')
        seen[key].append(kind)
        field=dict(tx_reserve='reserved',supply='supplied',inject='injected',receive='received',commit='committed')[kind]
        if (event['cycle']!=p[field] or event['cycle']<last or event['bytes']!=p['bytes'] or
            event['source']!=m['source'] or event['destination']!=m['destination']):
            raise ValueError('Boundary event identity or clock differs')
        last=event['cycle'];src,dst=m['source'],m['destination']
        if kind=='tx_reserve': tx[src]+=1
        if kind=='inject': tx[src]-=1
        if kind=='receive': rx[dst]+=1
        if kind=='commit': rx[dst]-=1
        if tx[src]<0 or tx[src]>boundary['tx_capacity_slots'] or rx[dst]<0:
            raise ValueError('Endpoint capacity violation')
        if boundary['bounded'] and rx[dst]>boundary['rx_capacity_slots']:
            raise ValueError('Finite receive capacity exceeded')
        if tx[src]!=event['tx_slots'] or rx[dst]!=event['rx_slots']:
            raise ValueError('Recorded occupancy inconsistent with byte events')
        peak_tx[src]=max(peak_tx[src],tx[src]);peak_rx[dst]=max(peak_rx[dst],rx[dst])
    if (any(tx.values()) or any(rx.values()) or len(seen)!=sum(len(m['packets']) for m in moves.values()) or
        any(len(v)!=5 for v in seen.values())): raise ValueError('Incomplete endpoint lifetime')
    return dict(passed=True,peak_tx_slots=dict(peak_tx),peak_rx_slots=dict(peak_rx),
        rx_overflow_slots=max(0,max(peak_rx.values(),default=0)-boundary['rx_capacity_slots']))
