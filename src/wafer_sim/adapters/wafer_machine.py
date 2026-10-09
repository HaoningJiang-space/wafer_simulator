"""Compile a declared physical machine to the existing execution contracts.

Read transactions: request -> controller -> bank -> channel -> response.
Writes: data arrival -> controller -> channel -> bank -> acknowledgement.
Whole-object admission reserves finite controller staging until operation
retirement. This is an explicit conservative transaction policy, not a DRAM
command simulator or a streaming-memory reference.
"""
from dataclasses import dataclass, replace
from types import MappingProxyType

from wafer_sim.architecture.wafer_machine import validate
from wafer_sim.architecture.spatial import Target, MemoryRegion, ComputeResource, Network
from wafer_sim.architecture.timing import Timing, Service, Endpoint, Link
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.execution.plan import Allocation, Demand, Phase, Transfer

CONTROL_BYTES = 16


@dataclass(frozen=True)
class CompiledMachine:
    physical: object
    target: Target
    timing: Timing
    router_ids: dict
    endpoints: dict
    controller_buffers: tuple[MemoryRegion, ...]


def compile_machine(machine):
    validate(machine)
    routers={t.id:i for i,t in enumerate(machine.tiles)}
    endpoints={s.id:i for i,s in enumerate(machine.stores)}
    memory=tuple(MemoryRegion(s.id,endpoints[s.id],s.capacity_bytes,
                 s.id+'/port',s.id+'/port',machine.provenance) for s in machine.stores)
    compute=tuple(ComputeResource(s.tile,s.id,tuple(dict(machine.compute_rates)),machine.provenance)
                  for s in machine.stores if s.kind=='sram')
    network=Network(tuple((endpoints[s.id],routers[s.tile]) for s in machine.stores),
        tuple((routers[l.source],routers[l.destination]) for l in machine.connections),machine.provenance)
    services=[Service(m.id+'/port','bytes',m.bytes_per_cycle,latency_cycles=m.latency_cycles)
              for m in machine.stores]
    services.extend(Service(c.id,unit,rate) for c in compute for unit,rate in machine.compute_rates)
    buffers=[]
    for c in machine.controllers:
        services.extend((Service(c.id+'/command','bytes',CONTROL_BYTES,c.command_cycles),
                         Service(c.id+'/channel','bytes',c.channel_bytes_per_cycle)))
        representative=next(s for s in machine.stores if s.controller==c.id)
        # Capacity-only storage is not a second communication endpoint. Its
        # attached ID names the controller's existing gateway for provenance.
        buffers.append(MemoryRegion(c.id+'/buffer',endpoints[representative.id],c.buffer_bytes,
                                    c.id+'/channel',c.id+'/channel',machine.provenance))
    links=tuple(Link(a,b,Service(f'fabric/{a}/{b}','bytes',l.bytes_per_cycle,
                                latency_cycles=l.latency_cycles+machine.router_latency_cycles))
                for l in machine.connections
                for a,b in ((routers[l.source],routers[l.destination]),(routers[l.destination],routers[l.source])))
    eps=tuple(Endpoint(e,Service(f'inject/{e}','bytes',machine.flit_bytes,
                                latency_cycles=machine.access_latency_cycles),
                        Service(f'eject/{e}','bytes',machine.flit_bytes,
                                latency_cycles=machine.access_latency_cycles+machine.router_latency_cycles))
              for e in endpoints.values())
    target=Target(memory,compute,network)
    return CompiledMachine(machine,target,Timing(tuple(services),links,eps,machine.provenance),
                           routers,endpoints,tuple(buffers))


def bind_machine(workload, compiled, placement):
    """Keep the logical DAG. Expand only movements to addressable memory."""
    if any(op.collective is not None for op in workload.operations):
        raise ValueError('Memory transaction adapter currently accepts ordinary operations only')
    base=bind(workload,compiled.target,placement)
    stores={s.id:s for s in compiled.physical.stores}
    controllers={c.id:c for c in compiled.physical.controllers}
    plans={}; transactions=[]
    for op,plan in base.plans.items():
        phases=[]; reservations=list(plan.reservations); i=0
        while i<len(plan.phases):
            phase=plan.phases[i]
            # All generic moves are source-read / payload / destination-write.
            if i+2<len(plan.phases) and plan.phases[i+1].transfer is not None:
                read,move,write=plan.phases[i:i+3]; t=move.transfer
                if read.kind!='memory_read' or write.kind!='memory_write':
                    raise ValueError('Expected source-read/payload/destination-write movement')
                src,dst=stores[t.source_memory],stores[t.destination_memory]
                if src.kind!='sram' and dst.kind!='sram':
                    raise ValueError('Memory-to-memory DMA requires its own declared transaction policy')
                def control(source,destination):
                    index=len(phases)
                    phases.append(Phase('transfer',transfer=Transfer(t.data,source.id,destination.id,
                        compiled.endpoints[source.id],compiled.endpoints[destination.id],CONTROL_BYTES)))
                    return index
                start=len(phases); request=None; ack=None; ctrl=None
                if src.kind!='sram':
                    ctrl=controllers[src.controller]
                    request=control(dst,src)
                    phases.append(Phase('memory_read',(Demand(ctrl.id+'/command','bytes',CONTROL_BYTES),)))
                    phases.append(read)
                    phases.append(Phase('memory_read',(Demand(ctrl.id+'/channel','bytes',t.size_bytes),)))
                    payload=len(phases); phases.extend((move,write))
                elif dst.kind!='sram':
                    ctrl=controllers[dst.controller]
                    phases.append(read); payload=len(phases); phases.append(move)
                    phases.append(Phase('memory_write',(Demand(ctrl.id+'/command','bytes',CONTROL_BYTES),
                                                        Demand(ctrl.id+'/channel','bytes',t.size_bytes))))
                    phases.append(write)
                    ack=control(dst,src)
                else:
                    phases.append(read); payload=len(phases); phases.extend((move,write))
                if ctrl is not None:
                    reservations.append(Allocation(('controller-staging',op,str(i)),ctrl.id+'/buffer',t.size_bytes))
                transactions.append(dict(operation=op,data=t.data,bytes=t.size_bytes,
                    source=src.id,destination=dst.id,kind='read' if request is not None else 'write' if ack is not None else 'c2c',
                    request_phase=request,payload_phase=payload,ack_phase=ack,
                    first_phase=start,last_phase=len(phases)-1,controller=ctrl.id if ctrl else None))
                i+=3
            else:
                phases.append(phase);i+=1
        plans[op]=replace(plan,reservations=tuple(reservations),phases=tuple(phases))
    result=replace(base,memory=MappingProxyType({**base.memory,**{m.id:m for m in compiled.controller_buffers}}),
                   plans=MappingProxyType(plans))
    TimedTarget(result,compiled.timing)
    return result,transactions


def export_booksim(compiled, directory, seed=1):
    """Reuse the pinned native anynet interface, without any WoW placement."""
    from pathlib import Path
    from wafer_sim.adapters.online_booksim import prepare_online_config
    m=compiled.physical; directory=Path(directory)
    if any(l.bytes_per_cycle!=m.flit_bytes for l in m.connections):
        raise ValueError('Existing native adapter requires one flit/cycle on every physical link')
    relative=directory/'rapidchiplet/booksim2/src'
    for part in ('rc_configs','rc_topologies','rc_stats','rc_xy_info'):
        (relative/part).mkdir(parents=True,exist_ok=True)
    rows=[]
    for tile,router in compiled.router_ids.items():
        row=f'router {router}'
        for endpoint, attached in compiled.target.network.endpoint_routers:
            if attached==router: row+=f' node {endpoint} {m.access_latency_cycles}'
        for link in m.connections:
            if tile in (link.source,link.destination):
                other=link.destination if link.source==tile else link.source
                row+=f' router {compiled.router_ids[other]} {link.latency_cycles}'
        rows.append(row)
    (relative/'rc_topologies/network.anynet').write_text('\n'.join(rows)+'\n')
    inputs=dict(chiplets={'gateway':dict(router_latency=m.router_latency_cycles)},
        placement={'chiplets':[{'name':'gateway'} for _ in m.tiles]},routing_table={'type':'default'},
        booksim_config=dict(mode='trace',trace_file='none',ignore_cycles=0,repetitions=1,
            sim_count=1,trace_time_out=120,time_limit=120,precision=0.001,saturation_factor=2,
            traffic='uniform',packet_size=1,num_vcs=1,vc_buf_size=32,
            modular_routing_function='simple_cycle_breaking_set',modular_selection_function='adaptive',
            sample_period=100000,warmup_periods=0,wait_for_tail_credit=0,
            injection_rate_uses_flits=1,deadlock_warn_timeout=200000))
    return prepare_online_config(inputs,directory,seed)
