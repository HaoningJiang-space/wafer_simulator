"""Place independent copies on fixed disjoint endpoints; no scheduler changes."""
from wafer_sim.adapters.transformer import place_block
from wafer_sim.execution.plan import Placement
from wafer_sim.workloads.groups import independent_groups


def place_groups(block, worker_endpoints):
    endpoints = [e for values in worker_endpoints.values() for e in values]
    if len(endpoints) != len(set(endpoints)):
        raise ValueError('This study requires disjoint compute/memory endpoints')
    work = independent_groups(block.workload, worker_endpoints)
    compute, data = {}, {}
    for group, endpoints in worker_endpoints.items():
        placement = place_block(block, endpoints)
        compute.update({group+'/'+k: v for k, v in placement.compute.items()})
        data.update({group+'/'+k: v for k, v in placement.data.items()})
    return work, Placement(compute, data)
