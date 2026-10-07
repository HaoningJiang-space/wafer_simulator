"""One declared workload, fixed placement, and three separate rate interventions."""
from wafer_sim.execution.plan import Placement
from wafer_sim.experiments.target_execution import run_bound_case
from wafer_sim.workloads.timed_example import workload


def run_case(config, case):
    machine = dict(config, compute_rates={"mac":config["macs_per_cycle"],
                                           "scalar_add":config["scalar_adds_per_cycle"]})
    placement = Placement(config["operation_placement"],config["data_placement"])
    record = run_bound_case(workload(), machine, placement, case)
    record["collective"] = dict(operation="AllReduce",participants=[1,2],root=1,reduction="sum",
                    elements=4,element_bytes=4,algorithm="root gather, sum, broadcast",
                    completion="both output homes written before either C begins")
    return record
