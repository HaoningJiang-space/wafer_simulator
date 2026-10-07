"""Complete declared A -> fanout B -> SUM allreduce -> C execution unit.

This is an analytical workload, not a truncated capture or a Llama benchmark.
Allreduce is explicitly lowered to root gather, one sum and two result copies.
The single reduction operation completes after both destination writes.
"""
from wafer_sim.workloads.spatial import DataObject, Operation, Workload

PROVENANCE = "Declared analytical execution unit; 4 float32 elements per tensor"


def workload():
    def data(name,producer=None,retain=False):
        return DataObject(name,16,producer,retain,PROVENANCE)
    def op(name,inputs,outputs,amount,unit="mac"):
        return Operation(name,inputs,outputs,((unit,amount),),0,(),PROVENANCE)
    return Workload((data("seed"),data("x","A"),data("b0","B0"),data("b1","B1"),
        data("sum0","AllReduce"),data("sum1","AllReduce"),
        data("out0","C0",True),data("out1","C1",True)), (
        op("A",("seed",),("x",),64),
        op("B0",("x",),("b0",),128),op("B1",("x",),("b1",),128),
        op("AllReduce",("b0","b1"),("sum0","sum1"),4,"scalar_add"),
        op("C0",("sum0",),("out0",),32),op("C1",("sum1",),("out1",),32)))
