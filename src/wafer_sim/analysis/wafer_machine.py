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
    expected_command=Counter(); expected_channel=Counter(); expected_bank=Counter(); expected_staging=Counter()
    for op in workload.operations:
        local=locals_[placement.compute[op.id]]; expected=[]; protocols=[]
        def add(name,source,destination,size,kind):
            expected.append((name,source,destination,size));counts[kind]+=1
            (control if kind in {'read_request','write_ack'} else payload)[kind]+=size
        for name in op.inputs:
            home=placement.data[name];d=objects[name]
            if home==local:continue
            if stores[home].kind!='sram':
                protocols.append((len(expected),len(expected)+1,home,d.size_bytes,'read'))
                add(name,local,home,control_bytes,'read_request')
                expected_command[stores[home].controller]+=control_bytes
                expected_channel[stores[home].controller]+=d.size_bytes
                expected_bank[home]+=d.size_bytes
                expected_staging[op.id,stores[home].controller+'/buffer',d.size_bytes]+=1
            add(name,home,local,d.size_bytes,'read_response' if stores[home].kind!='sram' else 'c2c')
        for name in op.outputs:
            home=placement.data[name];d=objects[name]
            if home==local:continue
            first=len(expected)
            add(name,local,home,d.size_bytes,'write_data' if stores[home].kind!='sram' else 'c2c')
            if stores[home].kind!='sram':
                protocols.append((first,first+1,home,d.size_bytes,'write'))
                add(name,home,local,control_bytes,'write_ack')
                expected_command[stores[home].controller]+=control_bytes
                expected_channel[stores[home].controller]+=d.size_bytes
                expected_bank[home]+=d.size_bytes
                expected_staging[op.id,stores[home].controller+'/buffer',d.size_bytes]+=1
        observed=sorted(by_op[op.id],key=lambda m:int(m['token'].rsplit('/',1)[1]))
        actual=[(m['data'],m['source_memory'],m['destination_memory'],m['bytes']) for m in observed]
        if actual!=expected:raise ValueError('Request/response/ack sequence or logical byte count differs')
        for before,after,home,size,kind in protocols:
            first,last=observed[before],observed[after]
            lo=int(first['token'].rsplit('/',1)[1]);hi=int(last['token'].rsplit('/',1)[1])
            events=[e for e in result['services'] if e['token'].rsplit('/phase/',1)[0]==op.id
                    and lo<int(e['token'].rsplit('/',1)[1])<hi]
            ctrl=stores[home].controller
            expected_service=[(ctrl+'/command',control_bytes)]
            data_service=[(home+'/port',size),(ctrl+'/channel',size)]
            expected_service+=data_service if kind=='read' else data_service[::-1]
            if [(e['resource'],e['amount']) for e in events]!=expected_service:
                raise ValueError('Bank/channel service does not occur inside its transaction')
            if (events[0]['ready']!=first['finish'] or events[-1]['finish']!=last['ready'] or
                any(a['finish']!=b['ready'] for a,b in zip(events,events[1:]))):
                raise ValueError('Memory service precedes request/data arrival or response precedes commit')
        for msg in observed:
            if (msg['source']!=compiled.endpoints[msg['source_memory']] or
                msg['destination']!=compiled.endpoints[msg['destination_memory']]):
                raise ValueError('Packet endpoint does not belong to its data location')
    actual_staging=Counter((op,a.memory,a.size_bytes) for op,p in binding.plans.items()
                           for a in p.reservations if a.key[0]=='controller-staging')
    if actual_staging!=expected_staging:raise ValueError('Missing or repeated controller staging capacity')
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


def verify_saved(root,output,tests):
    """Fresh readback and exact compiled-input check after source organization."""
    from dataclasses import asdict
    from pathlib import Path
    import platform
    import subprocess
    from wafer_sim.io import read_json,write_json,digest,object_digest
    from wafer_sim.architecture.wafer_machine import from_config
    from wafer_sim.adapters.wafer_machine import compile_machine,bind_machine
    from wafer_sim.adapters.memory_machine_workload import place
    from wafer_sim.workloads.memory_machine import build
    from wafer_sim.analysis.timed_attribution import critical_chain
    if platform.node().split('.')[0]!='eex005':raise ValueError('Remote evidence readback only')
    repo=Path(__file__).resolve().parents[3];root=Path(root);output=Path(output)
    if not output.is_absolute():raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    receipt=read_json(tests)
    if (not receipt['passed'] or receipt['source_commit']!=commit or
        digest(receipt['tests_log'])!=receipt['tests_log_sha256']):raise ValueError('Same-source passing tests required')
    done=read_json(root/'COMPLETE.json');start=read_json(root/'STARTED.json')
    if not done['all_registered_work_complete'] or (root/'FAILED.json').exists():raise ValueError('Not an accepted complete run')
    for f,h in done['artifacts_sha256'].items():
        if digest(root/f)!=h:raise ValueError('Changed artifact: '+f)
    reg=read_json(repo/'configs/wafer_machine_validation.json')
    if reg!=start['registration']:raise ValueError('Changed registration')
    if subprocess.check_output(['git','-C',str(repo),'diff',reg['frozen_execution_commit'],
        '--name-only','--','src/wafer_sim/execution','patches','third_party']):raise ValueError('Changed frozen kernel')
    if digest(Path(reg['runtime'])/'build/booksim-online/online_booksim')!=start['binary_sha256']:
        raise ValueError('Changed native binary')
    c=compile_machine(from_config(read_json(repo/reg['machine'])))
    work,meta=build(**reg['workload']);rows=[]
    for mode in reg['data_placements']:
        directory=root/mode;p=place(meta,mode);b,tx=bind_machine(work,c,p)
        expected=dict(machine=asdict(c.physical),target=asdict(c.target),timing=asdict(c.timing),
            workload=asdict(work),placement=asdict(p),transactions=tx,
            plans={k:asdict(v) for k,v in b.plans.items()},capacities={k:asdict(v) for k,v in b.memory.items()})
        if object_digest(expected)!=object_digest(read_json(directory/'INPUT.json')):
            raise ValueError('Compiled input changed after separation of workload and placement')
        result=read_json(directory/'execution.json')
        check=audit_machine(work,p,c,b,result)
        if check!=read_json(directory/'AUDIT.json'):raise ValueError('Audit recomputation differs')
        if object_digest(critical_chain(b,result))!=object_digest(read_json(directory/'critical_chain.json')):
            raise ValueError('Critical-chain readback differs')
        rows.append(dict(placement=mode,passed=True,compiled_input_equal=True,
                         application_cycles=result['application_cycles']))
    output.mkdir(exist_ok=False)
    result=dict(passed=True,analysis_commit=commit,run_commit=done['source_commit'],
        checked_artifact_hashes=len(done['artifacts_sha256']),run_manifest_sha256=digest(root/'COMPLETE.json'),
        source_tests=receipt,tests_sha256=digest(tests),frozen_kernel_unchanged=True,rows=rows,
        scope='All retained events reaudited; current compiled work/placement/resources/phases equal accepted inputs; no application rerun')
    write_json(output/'VERIFIED.json',result)
    return result
