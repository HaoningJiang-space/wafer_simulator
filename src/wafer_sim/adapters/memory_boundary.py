"""Fuse exclusive read/transfer/write chains; preserve all other dependencies."""
from dataclasses import replace
from types import MappingProxyType

from wafer_sim.execution.plan import Phase, OperationPlan


def reserve_endpoint_storage(binding, flit_bytes, tx_slots, rx_slots):
    if any(type(v) is not int or v<=0 for v in (flit_bytes,tx_slots,rx_slots)):
        raise ValueError('Positive integral endpoint capacities required')
    budget=(tx_slots+rx_slots)*flit_bytes
    if any(m.capacity_bytes<=budget for m in binding.memory.values()):
        raise ValueError('Endpoint buffers exhaust SRAM budget')
    return replace(binding,memory=MappingProxyType({k:replace(m,capacity_bytes=m.capacity_bytes-budget)
                                                   for k,m in binding.memory.items()}))


def fuse_movements(binding):
    plans={}; source_map={}
    for op,plan in binding.plans.items():
        successors={i:[] for i in range(len(plan.phases))}
        for i in successors:
            for p in plan.predecessors(i): successors[p].append(i)
        groups={}; consumed=set()
        for i,phase in enumerate(plan.phases):
            if phase.transfer is None: continue
            deps=plan.predecessors(i)
            if len(deps)!=1 or len(successors[i])!=1:
                raise ValueError('Movement requires exclusive read/transfer/write chain')
            r,w=deps[0],successors[i][0]
            read,write=plan.phases[r],plan.phases[w];t=phase.transfer
            src,dst=binding.memory[t.source_memory],binding.memory[t.destination_memory]
            if (successors[r]!=[i] or plan.predecessors(w)!=(i,) or
                read.kind!='memory_read' or write.kind!='memory_write' or
                len(read.demands)!=1 or len(write.demands)!=1 or
                [(d.resource,d.unit,d.amount) for d in (*read.demands,*write.demands)]!=
                [(src.read_port,'bytes',t.size_bytes),(dst.write_port,'bytes',t.size_bytes)] or
                consumed.intersection((r,i,w))):
                raise ValueError('Cannot fuse shared, partial or ambiguous memory demand')
            # No output may become visible at an internal read/transfer boundary.
            if any(r in ds or i in ds for _,ds in plan.output_requirements):
                raise ValueError('Intermediate publication prevents movement fusion')
            groups[r]=(i,w);consumed.update((r,i,w))
        phases=[]; deps=[]; names=[];mapping={};origins={}
        for old,phase in enumerate(plan.phases):
            if old in consumed and old not in groups: continue
            new=len(phases);mapping[old]=new
            if old in groups:
                i,w=groups[old];mapping[i]=new;mapping[w]=new
                phase=Phase('memory_network',(*phase.demands,*plan.phases[w].demands),plan.phases[i].transfer)
                origins[new]=dict(read=old,transfer=i,write=w)
            phases.append(phase);deps.append(plan.predecessors(old))
            names.append(f'{op}/original-phase/{old}')
        deps=tuple(tuple(sorted({mapping[p] for p in ds})) for ds in deps)
        if any(p>=i for i,ds in enumerate(deps) for p in ds): raise ValueError('Fusion would reorder a dependency')
        output=tuple((d,tuple(sorted({mapping[p] for p in plan.output_phases(d)})))
                     for d in binding.graph.operations[op].outputs)
        plans[op]=OperationPlan(plan.reservations,tuple(phases),deps,tuple(names),plan.policy,output)
        source_map[op]=origins
    return replace(binding,plans=MappingProxyType(plans)),source_map
