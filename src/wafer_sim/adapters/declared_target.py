"""Build an explicit analytical machine; no inferred WoW calibration."""
from wafer_sim.architecture.spatial import Target, MemoryRegion, ComputeResource, Network
from wafer_sim.architecture.timing import Timing, Service, Link, Endpoint
from wafer_sim.workloads.spatial import natural


def build_target(config, multipliers=(1, 1, 1)):
    """One memory region and one compute server per endpoint, shared R/W port."""
    cf, mf, nf = multipliers
    for value in multipliers:
        natural(value, "service rate multiplier", positive=True)
    rates = config["compute_rates"]
    if not rates:
        raise ValueError("Explicit compute rates required")
    for value in rates.values():
        natural(value, "compute rate", positive=True)
    for key in ("memory_bytes_per_cycle", "link_bytes_per_cycle", "endpoint_bytes_per_cycle"):
        natural(config[key], key, positive=True)
    evidence = config["scope"]
    endpoints = tuple(tuple(e) for e in config["endpoint_routers"])
    links = tuple(tuple(e) for e in config["router_links"])
    target = Target(
        tuple(MemoryRegion(str(e), e, config["region_capacity_bytes"],
                           f"memory-{e}", f"memory-{e}", evidence) for e, _ in endpoints),
        tuple(ComputeResource(f"compute-{e}", str(e), tuple(rates), evidence) for e, _ in endpoints),
        Network(endpoints, links, evidence))
    services = tuple(s for e, _ in endpoints for s in (
        *(Service(f"compute-{e}", unit, cf*rate) for unit, rate in rates.items()),
        Service(f"memory-{e}", "bytes", mf*config["memory_bytes_per_cycle"])))
    timing = Timing(services,
        tuple(Link(a, b, Service(f"link-{a}-{b}", "bytes", nf*config["link_bytes_per_cycle"],
                                latency_cycles=config["link_latency_cycles"]))
              for x, y in links for a, b in ((x, y), (y, x))),
        tuple(Endpoint(e, Service(f"inject-{e}", "bytes", nf*config["endpoint_bytes_per_cycle"]),
                          Service(f"eject-{e}", "bytes", nf*config["endpoint_bytes_per_cycle"]))
              for e, _ in endpoints), evidence)
    return target, timing
