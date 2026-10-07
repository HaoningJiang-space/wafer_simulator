"""Complete declared transfer-and-consume units for endpoint mechanism checks."""
from wafer_sim.workloads.spatial import DataObject,Operation,Workload
from wafer_sim.execution.plan import Placement


def build(flows):
    data=[];ops=[];homes={};compute={}
    evidence='Declared vector SUM after remote read; every element and dependency retained'
    for i,(src,dst,size) in enumerate(flows):
        if size%4 or size<8 or src==dst:raise ValueError('Expected distinct endpoints and float32 vector')
        seed,out,name=f'x{i}',f'y{i}',f'consume{i}'
        data.extend((DataObject(seed,size,None,False,evidence),DataObject(out,4,name,True,evidence)))
        ops.append(Operation(name,(seed,),(out,),(('scalar_add',size//4-1),),0,(),evidence))
        homes[seed]=str(src);homes[out]=str(dst);compute[name]=f'compute-{dst}'
    return Workload(tuple(data),tuple(ops)),Placement(compute,homes)
