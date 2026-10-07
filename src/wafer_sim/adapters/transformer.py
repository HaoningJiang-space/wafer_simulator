"""Place logical Transformer workers without embedding hardware in the DAG."""
from wafer_sim.execution.plan import Placement


def place_block(block, worker_endpoints):
    if (len(worker_endpoints) != block.dimensions["shards"] or
            any(type(e) is not int or e < 0 for e in worker_endpoints)):
        raise ValueError("One explicit target endpoint per logical worker required")
    return Placement(
        {op: f"compute-{worker_endpoints[r]}" for op,r in block.operation_workers.items()},
        {d: str(worker_endpoints[r]) for d,r in block.data_workers.items()})
