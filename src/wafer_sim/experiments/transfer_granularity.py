"""Bounded same-work network abstraction study, without changing either model."""
from contextlib import contextmanager
from dataclasses import asdict
import gc
import os
from pathlib import Path
import resource
import shutil
import sys
import time

from wafer_sim.adapters import wow
from wafer_sim.adapters.online_booksim import OnlineBookSim, prepare_online_config
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.adapters.transformer import place_block
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.transfer_granularity import isolated_comparison, summarize_isolated
from wafer_sim.execution.plan import ExecutionPolicy
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.network_reference import compare_reference
from wafer_sim.io import read_json, write_json, object_digest
from wafer_sim.workloads.transformer import build_block


def usage(who):
    value=resource.getrusage(who)
    return value.ru_utime+value.ru_stime


class Meter:
    def __init__(self): self.rows=[]

    @contextmanager
    def phase(self,name):
        wall=time.perf_counter(); cpu=usage(resource.RUSAGE_SELF); child=usage(resource.RUSAGE_CHILDREN)
        try: yield
        finally:
            self.rows.append(dict(phase=name,wall_seconds=time.perf_counter()-wall,
                python_cpu_seconds=usage(resource.RUSAGE_SELF)-cpu,
                exited_children_cpu_seconds=usage(resource.RUSAGE_CHILDREN)-child))


def native_peak(client):
    if client is None: return 0
    for line in Path(f'/proc/{client.process.pid}/status').read_text().splitlines():
        if line.startswith('VmHWM:'): return int(line.split()[1])
    raise RuntimeError('Native peak RSS unavailable')


def prepare(descriptor):
    config,wc=descriptor['experiment'],descriptor['workload']
    exported=read_json(descriptor['network_json'])
    cm={k:wc[k] for k in ('region_capacity_bytes','compute_rates','memory_bytes_per_cycle')}
    cm['scope']='Common analytical compute/memory; not calibrated to WoW'
    target,timing,contract=build_wow_target(exported,cm,config['flit_bytes'])
    block=build_block(**wc['block'])
    mapping=wow.rank_mapping(exported['endpoints'],block.dimensions['shards'],config['mapping'])
    placement=place_block(block,mapping)
    binding=bind(block.workload,target,placement,execution_policy=ExecutionPolicy(**config['execution_policy']))
    identity=dict(logical_workload=asdict(block.workload),tensors=block.tensors,operators=block.operators,
        collectives=block.collectives,mapping=asdict(placement),target=asdict(target),timing=asdict(timing),
        resource_contract=contract,worker_endpoints=mapping,execution_policy=config['execution_policy'])
    return binding,timing,exported,identity


def new_client(descriptor,exported,directory):
    runtime=Path(descriptor['runtime'])
    sys.path.insert(0,str(runtime/'upstream/nw-design-for-wsi'))
    relative=Path('rapidchiplet/booksim2/src')
    for part in ('rc_configs','rc_topologies','rc_stats','rc_xy_info'):
        (directory/relative/part).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(descriptor['geometry_directory'])/relative/'rc_topologies/network.anynet',
                    directory/relative/'rc_topologies/network.anynet')
    config=prepare_online_config(exported['inputs'],directory,descriptor['experiment']['network_seed'])
    return OnlineBookSim(runtime/'build/booksim-online/online_booksim',config,directory,
                         flit_bytes=descriptor['experiment']['flit_bytes'])


def reference(descriptor,exported,directory,messages):
    return compare_reference(exported['inputs'],directory,directory/'reference',
        Path(descriptor['runtime'])/'build/booksim/rapidchiplet/booksim2/src/booksim',
        messages,descriptor['experiment']['network_seed'])


def worker(descriptor_path,backend,output,repetitions,affinity):
    """Measure before auditing, retaining immutable binding in reuse trials."""
    os.sched_setaffinity(0,affinity)
    output=Path(output);output.mkdir(exist_ok=False)
    meter=Meter()
    with meter.phase('input_graph_binding'):
        descriptor=read_json(descriptor_path)
        binding,timing,exported,identity=prepare(descriptor)
    with meter.phase('input_serialization'): write_json(output/'INPUT.json',identity)
    setup=list(meter.rows)
    trials=[]
    for repeat in range(repetitions):
        gc.collect()
        directory=output/f'trial-{repeat}';directory.mkdir()
        begin=len(meter.rows);client=None
        child_before=usage(resource.RUSAGE_CHILDREN)
        with meter.phase('backend_initialization'):
            if backend=='booksim': client=new_client(descriptor,exported,directory)
        try:
            with meter.phase('timed_execution'):
                result=execute(binding,timing,network=client,cycle_limit=descriptor['experiment']['cycle_limit'])
            # Snapshot before result serialization and before any audit/replay.
            peaks=dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                       native_lifetime_peak_rss_kib=native_peak(client))
            with meter.phase('native_close_and_serialization'):
                if client:
                    if result['complete']: client.close()
                    else: client.abort()
        finally:
            if client: client.abort()
        native_cpu=usage(resource.RUSAGE_CHILDREN)-child_before
        with meter.phase('execution_serialization'): write_json(directory/'execution.json',result)
        trials.append(dict(repetition=repeat,complete=result['complete'],application_cycles=result['application_cycles'],
            execution_identity=object_digest(result),native_total_cpu_seconds=native_cpu,**peaks,
            measured_phases=meter.rows[begin:]))
        incomplete=not result['complete'];del result
        if incomplete: break
    # Audit/replay after all measured repetitions to protect peak-RSS scope.
    for row in trials:
        if not row['complete']: continue
        directory=output/f"trial-{row['repetition']}";begin=len(meter.rows)
        with meter.phase('readback_independent_audit'):
            recorded=read_json(directory/'execution.json')
            write_json(directory/'AUDIT.json',audit(binding,timing,recorded))
        with meter.phase('standalone_reference'):
            if backend=='booksim': reference(descriptor,exported,directory,recorded['network_messages'])
        row['validation_phases']=meter.rows[begin:]
        row['artifact_bytes']=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
    if len({r['execution_identity'] for r in trials}) != 1: raise ValueError('Repeated execution changed simulated events')
    measured=dict(backend=backend,input_identity=object_digest(identity),trials=trials,setup_phases=setup,
        affinity=sorted(os.sched_getaffinity(0)),
        memory_scope='lifetime peaks before audit; reuse includes previous simulation/serialization; sum of peaks is only upper bound',
        cpu_scope='native CPU measured exactly after exit for initialize+execute+close; not a per-phase estimate',
        reuse_scope='immutable graph/binding; native process is always newly initialized',
        logging='full native protocol/flits and coarse services unchanged')
    write_json(output/'MEASURED.json',measured)


def characterize(descriptor_path,output):
    output=Path(output);output.mkdir(exist_ok=False)
    descriptor=read_json(descriptor_path)
    binding,timing,exported,identity=prepare(descriptor)
    target=TimedTarget(binding,timing)
    unique={}
    for op,plan in binding.plans.items():
        for i,phase in enumerate(plan.phases):
            if phase.transfer:
                t=phase.transfer;key=t.source_endpoint,t.destination_endpoint,t.size_bytes
                unique.setdefault(key,(t,[]))[1].append(f'{op}/phase/{i}')
    rows=[]
    for index,(_, (transfer,tokens)) in enumerate(sorted(unique.items())):
        directory=output/f'transfer-{index}';directory.mkdir()
        client=new_client(descriptor,exported,directory)
        try:
            client.submit('isolated',transfer,0)
            while client.pending:
                client.advance(descriptor['experiment']['cycle_limit'])
                if client.pending and client.now>=descriptor['experiment']['cycle_limit']:
                    raise TimeoutError('Isolated transfer incomplete')
            record=client.close()
        finally: client.abort()
        audit_messages(binding.network,record['messages'])
        reference(descriptor,exported,directory,record['messages'])
        row=isolated_comparison(target,record['messages'][0])
        row.update(index=index,logical_tokens=tokens)
        rows.append(row)
    write_json(output/'SERVICES.json',dict(rows=rows,input_identity=object_digest(identity),
        summary=summarize_isolated(rows,descriptor['service_tolerance_percent']),
        scope='one whole binding transfer, empty native network, same resources; not application replay'))
