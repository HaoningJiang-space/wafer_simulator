"""Complete two-GEMM-per-worker work; no captured time or traffic scaling."""
from wafer_sim.workloads.spatial import DataObject, Operation, Workload, validate, natural
from wafer_sim.execution.plan import Placement


def build(workers, rows, hidden):
    for name,value in (('workers',workers),('rows',rows),('hidden',hidden)):
        natural(value,name,positive=True)
    data=[]; ops=[]; compute={}; homes={}; tensors={}
    def obj(name,shape,home,producer=None,retain=False):
        size=4*shape[0]*shape[1]
        data.append(DataObject(name,size,producer,retain,'Declared dense float32 tensor'))
        tensors[name]=shape;homes[name]=home
    for i in range(workers):
        j=(i+1)%workers
        obj(f'x{i}',(rows,hidden),'host-memory' if i==0 else f'sram-{i}')
        obj(f'w{i}',(hidden,hidden),f'dram-{i}-0',retain=True)
        obj(f'v{i}',(hidden,hidden),f'dram-{j}-1',retain=True)
        obj(f'a{i}',(rows,hidden),f'sram-{i}',f'first{i}')
        obj(f'y{i}',(rows,hidden),f'dram-{j}-0',f'second{i}',True)
        for name,inputs,out,tile in ((f'first{i}',(f'x{i}',f'w{i}'),f'a{i}',i),
                                     (f'second{i}',(f'a{i}',f'v{i}'),f'y{i}',j)):
            ops.append(Operation(name,inputs,(out,),(('mac',rows*hidden*hidden),),0,(),
                                 'Y = (X W) V; second GEMM on next logical tile'))
            compute[name]=f'c{tile}'
    workload=Workload(tuple(data),tuple(ops));validate(workload)
    return workload,Placement(compute,homes),dict(tensors=tensors,
        terminal_objects=[f'y{i}' for i in range(workers)],
        dimensions=dict(workers=workers,rows=rows,hidden=hidden),
        macs=2*workers*rows*hidden*hidden,
        scope='Complete declared dense two-stage work, not Llama or measured training')


def place_data(placement,workers,mode):
    """Fixed data-home alternatives; task placement and logical work unchanged."""
    if mode not in {'near','opposite','single_controller'}:
        raise ValueError('Unknown declared data placement')
    homes=dict(placement.data)
    for name,home in homes.items():
        if home.startswith('dram-'):
            _,tile,bank=home.split('-')
            if mode=='opposite':tile=str((int(tile)+workers//2)%workers)
            if mode=='single_controller':tile='0'
            homes[name]=f'dram-{tile}-{bank}'
    return Placement(dict(placement.compute),homes)
