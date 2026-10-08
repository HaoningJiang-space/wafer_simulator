"""Complete two-GEMM-per-worker work; no captured time or traffic scaling."""
from wafer_sim.workloads.spatial import DataObject, Operation, Workload, validate, natural


def build(workers, rows, hidden):
    for name,value in (('workers',workers),('rows',rows),('hidden',hidden)):
        natural(value,name,positive=True)
    data=[]; ops=[]; operation_workers={}; data_roles={}; tensors={}
    def obj(name,shape,worker,role,producer=None,retain=False):
        size=4*shape[0]*shape[1]
        data.append(DataObject(name,size,producer,retain,'Declared dense float32 tensor'))
        tensors[name]=shape;data_roles[name]=dict(worker=worker,role=role)
    for i in range(workers):
        j=(i+1)%workers
        obj(f'x{i}',(rows,hidden),i,'input')
        obj(f'w{i}',(hidden,hidden),i,'first_weight',retain=True)
        obj(f'v{i}',(hidden,hidden),j,'second_weight',retain=True)
        obj(f'a{i}',(rows,hidden),i,'intermediate',f'first{i}')
        obj(f'y{i}',(rows,hidden),j,'output',f'second{i}',True)
        for name,inputs,out,tile in ((f'first{i}',(f'x{i}',f'w{i}'),f'a{i}',i),
                                     (f'second{i}',(f'a{i}',f'v{i}'),f'y{i}',j)):
            ops.append(Operation(name,inputs,(out,),(('mac',rows*hidden*hidden),),0,(),
                                 'Y = (X W) V; second GEMM on next logical tile'))
            operation_workers[name]=tile
    workload=Workload(tuple(data),tuple(ops));validate(workload)
    return workload,dict(tensors=tensors,operation_workers=operation_workers,data_roles=data_roles,
        terminal_objects=[f'y{i}' for i in range(workers)],
        dimensions=dict(workers=workers,rows=rows,hidden=hidden),
        macs=2*workers*rows*hidden*hidden,
        scope='Complete declared dense two-stage work, not Llama or measured training')
