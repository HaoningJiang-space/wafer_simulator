"""One declared workload, fixed placement, and three separate rate interventions."""
from dataclasses import asdict
import json

from wafer_sim.architecture.spatial import Target, MemoryRegion, ComputeResource, Network
from wafer_sim.architecture.timing import Timing, Service, Link, Endpoint
from wafer_sim.adapters.spatial import bind
from wafer_sim.execution.plan import Placement
from wafer_sim.execution.timing import execute
from wafer_sim.analysis.timing import audit
from wafer_sim.workloads.timed_example import workload


def run_case(config, case):
    if case not in {"declared","double_compute_rate","double_memory_rate","double_network_rate"}:
        raise ValueError("Unregistered timing case")
    cf,mf,nf = (2 if case == "double_"+kind+"_rate" else 1 for kind in ("compute","memory","network"))
    evidence = config["scope"]
    endpoints = tuple(tuple(e) for e in config["endpoint_routers"])
    links = tuple(tuple(e) for e in config["router_links"])
    target = Target(tuple(MemoryRegion(str(e),e,config["region_capacity_bytes"],f"memory-{e}",f"memory-{e}",evidence)
                          for e,_ in endpoints),
        tuple(ComputeResource(f"compute-{e}",str(e),("mac","scalar_add"),evidence) for e,_ in endpoints),
        Network(endpoints,links,evidence))
    services = tuple(s for e,_ in endpoints for s in (
        Service(f"compute-{e}","mac",cf*config["macs_per_cycle"]),
        Service(f"compute-{e}","scalar_add",cf*config["scalar_adds_per_cycle"]),
        Service(f"memory-{e}","bytes",mf*config["memory_bytes_per_cycle"])))
    timing = Timing(services,tuple(Link(a,b,Service(f"link-{a}-{b}","bytes",nf*config["link_bytes_per_cycle"],
        latency_cycles=config["link_latency_cycles"])) for x,y in links for a,b in ((x,y),(y,x))),
        tuple(Endpoint(e,Service(f"inject-{e}","bytes",nf*config["endpoint_bytes_per_cycle"]),
                         Service(f"eject-{e}","bytes",nf*config["endpoint_bytes_per_cycle"])) for e,_ in endpoints),evidence)
    logical = workload()
    placement = Placement(config["operation_placement"],config["data_placement"])
    binding = bind(logical,target,placement)
    result = json.loads(json.dumps(execute(binding,timing)))
    checked = audit(binding,timing,result)
    return dict(case=case,workload=asdict(logical),target=asdict(target),timing=asdict(timing),
                collective=dict(operation="AllReduce",participants=[1,2],root=1,reduction="sum",
                    elements=4,element_bytes=4,algorithm="root gather, sum, broadcast",
                    completion="both output homes written before either C begins"),
                placement=asdict(placement),result=result,audit=checked)
