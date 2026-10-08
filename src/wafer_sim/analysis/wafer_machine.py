"""Independent transaction/path accounting on top of existing timed audits."""
from collections import Counter
from math import ceil

from wafer_sim.analysis.timing import audit


def audit_machine(workload,placement,compiled,binding,result,control_bytes=16):
    check=audit(binding,compiled.timing,result)
    stores={s.id:s for s in compiled.physical.stores}
    locals_={c.id:c.memory for c in compiled.target.compute}
    messages=result.get('network_messages')
    if messages is None: raise ValueError('Machine path acceptance requires live native network')
    by_op={o.id:[] for o in workload.operations}
    for msg in messages:
        op=msg['token'].rsplit('/phase/',1)[0]
        if op not in by_op:raise ValueError('Message from unknown logical operation')
        by_op[op].append(msg)
    objects={d.id:d for d in workload.data}; counts=Counter(); payload=Counter(); control=Counter()
    expected_command=Counter(); expected_channel=Counter(); expected_bank=Counter()
    for op in workload.operations:
        local=locals_[placement.compute[op.id]]; expected=[]
        def add(name,source,destination,size,kind):
            expected.append((name,source,destination,size));counts[kind]+=1
            (control if kind in {'read_request','write_ack'} else payload)[kind]+=size
        for name in op.inputs:
            home=placement.data[name];d=objects[name]
            if home==local:continue
            if stores[home].kind!='sram':
                add(name,local,home,control_bytes,'read_request')
                expected_command[stores[home].controller]+=control_bytes
                expected_channel[stores[home].controller]+=d.size_bytes
                expected_bank[home]+=d.size_bytes
            add(name,home,local,d.size_bytes,'read_response' if stores[home].kind!='sram' else 'c2c')
        for name in op.outputs:
            home=placement.data[name];d=objects[name]
            if home==local:continue
            add(name,local,home,d.size_bytes,'write_data' if stores[home].kind!='sram' else 'c2c')
            if stores[home].kind!='sram':
                add(name,home,local,control_bytes,'write_ack')
                expected_command[stores[home].controller]+=control_bytes
                expected_channel[stores[home].controller]+=d.size_bytes
                expected_bank[home]+=d.size_bytes
        observed=sorted(by_op[op.id],key=lambda m:int(m['token'].rsplit('/',1)[1]))
        actual=[(m['data'],m['source_memory'],m['destination_memory'],m['bytes']) for m in observed]
        if actual!=expected:raise ValueError('Request/response/ack sequence or logical byte count differs')
        for msg in observed:
            if (msg['source']!=compiled.endpoints[msg['source_memory']] or
                msg['destination']!=compiled.endpoints[msg['destination_memory']]):
                raise ValueError('Packet endpoint does not belong to its data location')
    work=Counter()
    for e in result['services']:work[e['resource'],e['unit']]+=e['amount']
    for ctrl in compiled.physical.controllers:
        if work[ctrl.id+'/command','bytes']!=expected_command[ctrl.id] or work[ctrl.id+'/channel','bytes']!=expected_channel[ctrl.id]:
            raise ValueError('Controller command/channel accounting mismatch')
    for home,amount in expected_bank.items():
        if work[home+'/port','bytes']!=amount:raise ValueError('Bank service byte conservation mismatch')
    edges={frozenset((compiled.router_ids[l.source],compiled.router_ids[l.destination])):l
           for l in compiled.physical.connections}
    link_flits=Counter(); kinds=Counter()
    for msg in messages:
        src=stores[msg['source_memory']];dst=stores[msg['destination_memory']]
        for flit in msg['flits']:
            used=Counter()
            for a,b in zip(flit['router_path'],flit['router_path'][1:]):
                edge=edges[frozenset((a,b))]
                link_flits[edge.id,a,b]+=1;kinds[edge.kind]+=1;used[edge.kind]+=1
            expected_hb=int(src.kind=='dram')+int(dst.kind=='dram')
            expected_io=int(src.kind=='external')+int(dst.kind=='external')
            if used['hb']!=expected_hb or used['io']!=expected_io:
                raise ValueError('Traffic used undeclared memory or external transit path')
    flits=sum(ceil(m['bytes']/compiled.physical.flit_bytes) for m in messages)
    if flits!=sum(len(m['flits']) for m in messages):raise ValueError('Protocol padding/flit mismatch')
    return dict(passed=True,execution=check,messages=dict(counts),payload_bytes=dict(payload),
        control_bytes=dict(control),native_flits=flits,physical_kind_flits=dict(kinds),
        directed_link_flits=[dict(link=link,source=a,destination=b,flits=n) for (link,a,b),n in sorted(link_flits.items())],
        compute_macs=sum(amount for op in workload.operations for unit,amount in op.work if unit=='mac'),
        terminal_ready={d.id:result['output_ready'][d.id] for d in workload.data if d.producer and d.retain},
        storage_peak_bytes=result['peak_bytes'],
        status=dict(execution_completed=True,semantic_audit_passed=True,storage_capacity='feasible',
            transaction_buffer_capacity='feasible',streaming_rx_capacity='unmodeled',
            hardware_calibration='declared assumptions',dram_command_timing='unmodeled'))
