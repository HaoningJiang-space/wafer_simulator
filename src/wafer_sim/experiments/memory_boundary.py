"""Fixed native network, endpoint-boundary comparison orchestration only."""
from dataclasses import asdict,replace
import os
from pathlib import Path
import resource
import shutil
import sys

from wafer_sim.adapters.boundary_booksim import BoundaryBookSim
from wafer_sim.adapters.online_booksim import prepare_online_config
from wafer_sim.adapters.memory_boundary import reserve_endpoint_storage,fuse_movements
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.memory_boundary import audit_occupancy
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.memory_boundary import MemoryBoundary
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.transfer_granularity import prepare as prepare_block,Meter,native_peak,usage
from wafer_sim.io import read_json,write_json,object_digest
from wafer_sim.workloads.boundary_mechanisms import build


def prepare(descriptor):
    if 'flows' not in descriptor:
        binding,timing,exported,identity=prepare_block(descriptor)
    else:
        exported=read_json(descriptor['network_json']);wc=descriptor['workload']
        cm={k:wc[k] for k in ('region_capacity_bytes','compute_rates','memory_bytes_per_cycle')}
        cm['scope']='Declared boundary diagnostic, not calibrated endpoint hardware'
        target,timing,contract=build_wow_target(exported,cm,descriptor['experiment']['flit_bytes'])
        work,placement=build(descriptor['flows']);binding=bind(work,target,placement)
        overrides={f'memory-{k}':v for k,v in descriptor.get('memory_overrides',{}).items()}
        timing=replace(timing,services=tuple(replace(s,rate_numerator=overrides[s.resource])
            if s.resource in overrides else s for s in timing.services))
        identity=dict(logical_workload=asdict(work),mapping=asdict(placement),target=asdict(target),timing=asdict(timing),resource_contract=contract)
    cfg=descriptor['boundary']
    binding=reserve_endpoint_storage(binding,cfg['flit_bytes'],cfg['tx_slots'],cfg['rx_slots'])
    identity['boundary_contract']=cfg
    identity['usable_memory']={k:asdict(v) for k,v in binding.memory.items()}
    if descriptor.get('memory_quantum_bytes') is not None:
        identity['memory_quantum_bytes']=descriptor['memory_quantum_bytes']
    return binding,timing,exported,identity


def client(descriptor,exported,directory):
    runtime=Path(descriptor['runtime']);sys.path.insert(0,str(runtime/'upstream/nw-design-for-wsi'))
    relative=Path('rapidchiplet/booksim2/src')
    for part in ('rc_configs','rc_topologies','rc_stats','rc_xy_info'):(directory/relative/part).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(descriptor['geometry_directory'])/relative/'rc_topologies/network.anynet',directory/relative/'rc_topologies/network.anynet')
    config=prepare_online_config(exported['inputs'],directory,descriptor['experiment']['network_seed'])
    return BoundaryBookSim(runtime/'build/booksim-boundary/endpoint_booksim',config,directory,
                           flit_bytes=descriptor['boundary']['flit_bytes'])


def worker(descriptor_path,mode,directory,cpus,*,profile_execution=False):
    os.sched_setaffinity(0,cpus);directory=Path(directory);directory.mkdir(exist_ok=False)
    meter=Meter();d=read_json(descriptor_path);cfg=d['boundary']
    with meter.phase('input_graph_binding'):
        binding,timing,exported,identity=prepare(d)
        source_map={}
        if mode!='serial':binding,source_map=fuse_movements(binding)
    write_json(directory/'INPUT.json',identity);write_json(directory/'PHASE_MAP.json',source_map)
    child_start=usage(resource.RUSAGE_CHILDREN)
    with meter.phase('backend_initialization'):
        native=client(d,exported,directory);backend=native
        if mode=='serial':native.configure(rx_slots=cfg['rx_slots'],bounded=False,streaming=False)
        else:backend=MemoryBoundary(native,tx_slots=cfg['tx_slots'],rx_slots=cfg['rx_slots'],bounded=mode=='bounded')
    try:
        profiler=None
        if profile_execution:
            import cProfile
            profiler=cProfile.Profile()
        with meter.phase('execution'):
            if profiler is not None:profiler.enable()
            try:
                result=execute(binding,timing,network=backend,cycle_limit=d['experiment']['cycle_limit'],
                               memory_quantum_bytes=d.get('memory_quantum_bytes'))
            finally:
                if profiler is not None:profiler.disable()
        if not result['complete']:raise ValueError('Incomplete work under unchanged capacity')
        peaks=dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                   native_peak_rss_kib=native_peak(native))
        with meter.phase('close_and_network_serialization'):backend.close()
    finally:backend.abort()
    child_cpu=usage(resource.RUSAGE_CHILDREN)-child_start
    if profiler is not None:
        with meter.phase('profile_serialization'):
            profiler.dump_stats(str(directory/'execution.prof'))
    with meter.phase('result_serialization'):write_json(directory/'execution.json',result)
    with meter.phase('independent_audit'):
        check=audit(binding,timing,result)
        capacity=audit_occupancy(result['boundary']) if mode!='serial' else None
        chain=critical_chain(binding,result)
        write_json(directory/'AUDIT.json',dict(execution=check,boundary=capacity))
        write_json(directory/'critical_chain.json',chain)
    record=dict(mode=mode,application_cycles=result['application_cycles'],complete=True,
        input_identity=object_digest(identity),execution_identity=object_digest(result),
        network_identity=native.identity,phases=meter.rows,native_total_cpu_seconds=child_cpu,**peaks,
        peak_total_reserved_bytes={k:v+(cfg['tx_slots']+cfg['rx_slots'])*cfg['flit_bytes'] for k,v in result['peak_bytes'].items()},
        boundary=capacity,critical_chain_cycles=chain['cycles'],affinity=cpus,
        memory_scope='Python lifetime including imports; native pre-close peak; audit excluded',
        logging='Full native protocol and packet progress, services and occupancy retained')
    write_json(directory/'MEASURED.json',record)
    return record
