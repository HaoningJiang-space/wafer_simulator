"""Independent logical-byte, interface, causal/window and execution audit."""
from collections import Counter
from dataclasses import asdict
from math import ceil

from wafer_sim.analysis.timing import audit as audit_timing
from wafer_sim.execution.plan import Phase, Demand, Transfer


def audit_periphery(workload, placement, compiled, binding, transactions, policy, result):
    # Check the policy independently of the plan used by execute()/audit_timing.
    # Ordinary periphery outputs publish at retirement; collective rank-local
    # publication belongs to its separate adapter and is deliberately untouched.
    for op in workload.operations:
        if op.collective is not None:
            raise ValueError('Periphery audit accepts ordinary operations only')
        plan = binding.plans[op.id]
        required = tuple(range(len(plan.phases)))
        if plan.output_requirements and (len(plan.output_requirements) != len(op.outputs) or
                dict(plan.output_requirements) != {name: required for name in op.outputs}):
            raise ValueError('Periphery output publication requires whole-operation retirement')
        for name in op.outputs:
            if result['output_ready'][name] != result['operations'][op.id]['retired']:
                raise ValueError('Periphery output published before retirement')
    checked = audit_timing(binding, compiled.timing, result)
    stores = {s.id: s for s in compiled.physical.stores}
    objects = {d.id: d for d in workload.data}
    local = {c.id: c.memory for c in compiled.target.compute}
    expected_work, expected_allocations = Counter(), Counter()
    controls, payload = Counter(), Counter()
    all_transactions = []

    def phase(kind, resource, size):
        return Phase(kind, (Demand(resource, 'bytes', size),))

    def transfer(data, source, destination, size):
        return Phase('transfer', transfer=Transfer(data, source, destination,
                     compiled.endpoints[source], compiled.endpoints[destination], size))

    for op in workload.operations:
        plan = binding.plans[op.id]; here = local[placement.compute[op.id]]
        skeleton = []

        def movement(name, source, destination):
            size = objects[name].size_bytes
            kind = 'read' if stores[source].kind != 'sram' else 'write' if stores[destination].kind != 'sram' else 'c2c'
            skeleton.append(('move', (name, source, destination, size, kind)))
            expected_work[stores[source].id+'/port', 'bytes'] += size
            expected_work[stores[destination].id+'/port', 'bytes'] += size
            if kind != 'c2c':
                ctrl = stores[source if kind == 'read' else destination].controller
                expected_work[ctrl+'/command', 'bytes'] += 16
                expected_work[ctrl+'/channel', 'bytes'] += size
                expected_allocations['controller-staging', ctrl+'/buffer', size] += 1
                controls[kind] += 16
            payload[kind] += size

        for name in op.inputs:
            home = placement.data[name]
            if home != here:
                expected_allocations['input', here, objects[name].size_bytes] += 1
                movement(name, home, here)
        amount = sum(objects[n].size_bytes for n in op.inputs)
        if amount: skeleton.append(('phase', phase('memory_read', here+'/port', amount)))
        skeleton.append(('phase', Phase('compute', tuple(Demand(placement.compute[op.id], unit, amount)
                                                       for unit, amount in op.work))))
        amount = sum(objects[n].size_bytes for n in op.outputs)
        if amount: skeleton.append(('phase', phase('memory_write', here+'/port', amount)))
        for name in op.outputs:
            home = placement.data[name]; size = objects[name].size_bytes
            expected_allocations['object', home, size] += 1
            if home != here:
                expected_allocations['output', here, size] += 1
                movement(name, here, home)
        if op.scratch_bytes: expected_allocations['scratch', here, op.scratch_bytes] += 1
        txs = sorted((t for t in transactions if t['operation'] == op.id), key=lambda t: t['first_phase'])
        cursor, tx_index, frontier = 0, 0, ()

        def check_phase(index, expected, predecessors):
            if plan.phases[index] != expected or plan.predecessors(index) != tuple(dict.fromkeys(predecessors)):
                raise ValueError('Periphery service/bytes or causal/window dependencies differ')

        for item_kind, item in skeleton:
            if item_kind == 'phase':
                check_phase(cursor, item, frontier)
                for d in item.demands: expected_work[d.resource, d.unit] += d.amount
                frontier = (cursor,); cursor += 1
                continue
            if tx_index >= len(txs): raise ValueError('Missing logical transaction')
            t = txs[tx_index]; tx_index += 1; all_transactions.append(t)
            name, source, destination, size, kind = item
            if ((t['data'], t['source'], t['destination'], t['bytes'], t['kind']) != item or
                    t['first_phase'] != cursor):
                raise ValueError('Transaction differs from logical work/operand order')
            ctrl = stores[source if kind == 'read' else destination].controller if kind != 'c2c' else None
            if t['controller'] != ctrl: raise ValueError('Transaction uses another controller')
            if policy.kind == 'whole' or kind == 'c2c':
                expected = []
                if kind == 'read':
                    expected.extend((transfer(name, destination, source, 16),
                        phase('memory_read', ctrl+'/command', 16),
                        phase('memory_read', source+'/port', size),
                        phase('memory_read', ctrl+'/channel', size),
                        transfer(name, source, destination, size),
                        phase('memory_write', destination+'/port', size)))
                elif kind == 'write':
                    expected.extend((phase('memory_read', source+'/port', size), transfer(name, source, destination, size),
                        Phase('memory_write', (Demand(ctrl+'/command', 'bytes', 16), Demand(ctrl+'/channel', 'bytes', size))),
                        phase('memory_write', destination+'/port', size), transfer(name, destination, source, 16)))
                else:
                    expected.extend((phase('memory_read', source+'/port', size), transfer(name, source, destination, size),
                                     phase('memory_write', destination+'/port', size)))
                for p in expected:
                    check_phase(cursor, p, frontier)
                    frontier = (cursor,); cursor += 1
                expected_payload = t['first_phase'] + (4 if kind == 'read' else 1)
                if (t['payload_phase'] != expected_payload or
                    t['request_phase'] != (t['first_phase'] if kind == 'read' else None) or
                    t['ack_phase'] != (cursor-1 if kind == 'write' else None)):
                    raise ValueError('Whole transaction evidence points at another phase')
            else:
                entry = frontier
                if tuple(t['entry_phases']) != entry: raise ValueError('Premature independent input transfer')
                seen = set(); chunks = t['chunks']; terminals = []
                if len(chunks) != ceil(size/policy.chunk_bytes): raise ValueError('Missing or extra fragments')
                if kind == 'read':
                    request, command = t['request_phase'], t['command_phase']
                    if request != cursor or command != cursor+1 or t['ack_phase'] is not None:
                        raise ValueError('Read control sequence differs')
                    check_phase(request, transfer(name, destination, source, 16), entry)
                    check_phase(command, phase('memory_read', ctrl+'/command', 16), (request,))
                    seen.update((request, command))
                else:
                    command = t['command_phase']
                    if t['request_phase'] is not None: raise ValueError('Write gained a read request')
                    check_phase(command, phase('memory_write', ctrl+'/command', 16), (chunks[0]['payload_phase'],))
                    seen.add(command)
                offset = 0
                for j, chunk in enumerate(chunks):
                    amount = min(policy.chunk_bytes, size-offset)
                    if (chunk['ordinal'], chunk['offset'], chunk['bytes']) != (j, offset, amount):
                        raise ValueError('Fragment offsets overlap, skip or pad logical bytes')
                    src, channel, move, dst = (chunk[k] for k in
                        ('source_phase', 'channel_phase', 'payload_phase', 'destination_phase'))
                    if seen.intersection((src, channel, move, dst)) or len({src, channel, move, dst}) != 4:
                        raise ValueError('Fragment phases reused')
                    seen.update((src, channel, move, dst))
                    gate = (terminals[j-policy.window_chunks],) if j >= policy.window_chunks else ()
                    check_phase(src, phase('memory_read', source+'/port', amount),
                                (command, *gate) if kind == 'read' else (*entry, *gate))
                    check_phase(channel, phase('memory_read' if kind == 'read' else 'memory_write', ctrl+'/channel', amount),
                                (src,) if kind == 'read' else (move, command))
                    check_phase(move, transfer(name, source, destination, amount), (channel,) if kind == 'read' else (src,))
                    check_phase(dst, phase('memory_write', destination+'/port', amount), (move,) if kind == 'read' else (channel,))
                    terminals.append(dst); offset += amount
                if kind == 'write':
                    ack = t['ack_phase']
                    check_phase(ack, transfer(name, destination, source, 16), tuple(terminals))
                    seen.add(ack); frontier = (ack,)
                else: frontier = tuple(terminals)
                if seen != set(range(cursor, t['last_phase']+1)):
                    raise ValueError('Hidden or missing transaction phase')
                cursor = t['last_phase']+1
            if t['last_phase'] != cursor-1: raise ValueError('Wrong transaction boundary')
        if cursor != len(plan.phases) or tx_index != len(txs): raise ValueError('Extra work/transaction')
    if len(all_transactions) != len(transactions): raise ValueError('Transaction belongs to unknown operation')
    actual_work = Counter()
    for e in result['services']:
        if e['category'] != 'network': actual_work[e['resource'], e['unit']] += e['amount']
    if actual_work != expected_work: raise ValueError('Memory/compute byte or work conservation failed')
    actual_allocations = Counter((a.key[0], a.memory, a.size_bytes) for p in binding.plans.values() for a in p.reservations)
    if actual_allocations != expected_allocations: raise ValueError('Capacity reservations changed')
    edges = {frozenset((compiled.router_ids[l.source], compiled.router_ids[l.destination])): l.kind
             for l in compiled.physical.connections}
    physical_flits = Counter()
    for message in result.get('network_messages', []):
        src, dst = stores[message['source_memory']], stores[message['destination_memory']]
        if (message['source'] != compiled.endpoints[src.id] or message['destination'] != compiled.endpoints[dst.id]):
            raise ValueError('Payload bypassed declared interface')
        for flit in message['flits']:
            kinds = Counter(edges[frozenset((a, b))] for a, b in zip(flit['router_path'], flit['router_path'][1:]))
            if (kinds['hb'] != int(src.kind == 'dram') + int(dst.kind == 'dram') or
                    kinds['io'] != int(src.kind == 'external') + int(dst.kind == 'external')):
                raise ValueError('Memory/I-O leaf used as free fabric transit')
            physical_flits.update(kinds)
    return dict(passed=True, execution=checked, logical_transactions=len(transactions),
                payload_bytes=dict(payload), control_bytes=dict(controls),
                service_work=[dict(resource=r, unit=u, amount=n) for (r, u), n in sorted(expected_work.items())],
                physical_kind_flits=dict(physical_flits), whole_object_reservations=True,
                max_transaction_window_chunks=policy.window_chunks if policy.kind == 'pipeline' else None,
                hardware_calibration=False)


def transaction_timing(binding, transactions, result):
    phases = {(p['operation'], p['phase']): p for p in result['phases']}
    messages = {m['token']: m for m in result['network_messages']}
    rows = []
    for t in transactions:
        op = t['operation']
        indices = [c['payload_phase'] for c in t['chunks']] if 'chunks' in t else [t['payload_phase']]
        payload = [messages[f'{op}/phase/{i}'] for i in indices]
        group = [phases[op, i] for i in range(t['first_phase'], t['last_phase']+1)]
        rows.append(dict(operation=op, data=t['data'], kind=t['kind'], bytes=t['bytes'],
            source=t['source'], destination=t['destination'], fragments=len(payload),
            transaction_ready=min(p['ready'] for p in group), transaction_finish=max(p['finish'] for p in group),
            first_payload_ready=min(m['ready'] for m in payload), last_payload_ready=max(m['ready'] for m in payload),
            first_payload_inject=min(m['first_inject'] for m in payload), last_payload_inject=max(m['last_inject'] for m in payload),
            last_payload_finish=max(m['finish'] for m in payload)))
    return rows
