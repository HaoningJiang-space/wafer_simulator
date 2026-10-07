"""Shared orchestration for complete declared workloads and rate controls."""
from dataclasses import asdict
import json

from wafer_sim.adapters.declared_target import build_target
from wafer_sim.adapters.spatial import bind
from wafer_sim.analysis.timing import audit
from wafer_sim.execution.timing import execute

RATE_CASES = ("declared", "double_compute_rate", "double_memory_rate", "double_network_rate")


def run_bound_case(logical, config, placement, case):
    if case not in RATE_CASES:
        raise ValueError("Unregistered timing case")
    factors = tuple(2 if case == f"double_{kind}_rate" else 1
                    for kind in ("compute", "memory", "network"))
    target, timing = build_target(config, factors)
    binding = bind(logical, target, placement)
    result = json.loads(json.dumps(execute(binding, timing)))
    return dict(case=case, workload=asdict(logical), target=asdict(target), timing=asdict(timing),
                placement=asdict(placement), result=result, audit=audit(binding, timing, result))
