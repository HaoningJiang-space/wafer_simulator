"""Fixed logical Transformer block and mapping; separate resource-rate controls."""
from collections import Counter

from wafer_sim.adapters.transformer import place_block
from wafer_sim.experiments.target_execution import run_bound_case
from wafer_sim.workloads.transformer import build_block


def run_case(config, case):
    block = build_block(**config["block"])
    placement = place_block(block, config["worker_endpoints"])
    record = run_bound_case(block.workload, config, placement, case)
    work = Counter()
    for op in block.workload.operations:
        work.update(dict(op.work))
    record.update(collective=block.collectives, tensors=block.tensors, operators=block.operators,
                  dimensions=block.dimensions,
                  logical_summary=dict(operations=len(block.workload.operations),
                      data_objects=len(block.workload.data), work=dict(work),
                      parameter_bytes=sum(d.size_bytes for d in block.workload.data
                                          if block.tensors[d.id]["role"] == "parameter"),
                      retained_output_bytes=sum(d.size_bytes for d in block.workload.data
                          if d.retain and d.producer is not None)),
                  scope="Complete analytical Transformer block forward, not Llama or training")
    return record
