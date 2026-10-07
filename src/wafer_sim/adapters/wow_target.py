"""Bind exported WoW geometry/network to explicit common compute/memory rates."""
from wafer_sim.adapters.declared_target import build_target
from wafer_sim.adapters.spatial import network_from_wow
from wafer_sim.architecture.spatial import Target
from wafer_sim.architecture.timing import Timing, Service, Link, Endpoint
from wafer_sim.io import object_digest
from wafer_sim.workloads.spatial import natural


def build_wow_target(export, compute_memory, flit_bytes):
    network = network_from_wow(export)
    natural(flit_bytes, "flit bytes", positive=True)
    resources = export["resources"]
    # The pinned author BookSim exports one flit/cycle on every channel.
    # A different or heterogeneous width needs a new native channel model.
    if (resources["link_bits_per_cycle"] != flit_bytes*8 or
            any(link["bandwidth"] != flit_bytes*8 for link in export["inputs"]["links"])):
        raise ValueError("Exported link bandwidth does not match one native flit per cycle")
    scaffold = dict(compute_memory, endpoint_routers=network.endpoint_routers,
                    router_links=network.router_links, link_bytes_per_cycle=flit_bytes,
                    endpoint_bytes_per_cycle=flit_bytes, link_latency_cycles=0)
    local, _ = build_target(scaffold)
    routers = export["inputs"]["placement"]["chiplets"]
    chiplets = export["inputs"]["chiplets"]
    router_latency = resources["router_latency_cycles"]
    if any(chiplets[r["name"]]["router_latency"] != router_latency for r in routers):
        raise ValueError("Heterogeneous router pipelines need an explicit native model")
    endpoints = []
    for node,router in network.endpoint_routers:
        access = chiplets[routers[router]["name"]]["unit_to_router_latency"]
        endpoints.append(Endpoint(node,
            Service(f"inject-{node}", "bytes", flit_bytes, latency_cycles=access),
            Service(f"eject-{node}", "bytes", flit_bytes, latency_cycles=access+router_latency)))
    links = tuple(Link(a,b,Service(f"link-{a}-{b}","bytes",link["bandwidth"],8,
                                  latency_cycles=link["latency"]+router_latency))
                  for link in export["inputs"]["links"]
                  for a,b in ((link["src"],link["dst"]),(link["dst"],link["src"])))
    target = Target(local.memory,local.compute,network)
    local_services = tuple(s for c in target.compute for s in (
        *(Service(c.id,unit,rate) for unit,rate in compute_memory["compute_rates"].items()),
        Service(f"memory-{c.memory}","bytes",compute_memory["memory_bytes_per_cycle"])))
    timing = Timing(local_services,links,tuple(endpoints),
                    "WoW export "+object_digest(export)+"; common analytical compute/memory")
    contract = dict(network_frequency_hz=resources["network_frequency_hz"], flit_bytes=flit_bytes,
        bytes_to_flits="ceil(payload_bytes/flit_bytes); padding consumes network only",
        native_channel="one flit per cycle; bandwidth/8 bytes per cycle",
        native_endpoint="one flit per cycle, author unit-to-router channel latency",
        native_router="author VC/switch/crossbar pipeline, counted inside BookSim only",
        coarse_model="whole-message hop service; source router latency per link, final router in ejection",
        compute_memory_calibrated=False, physical_cost_matched=False,
        compute_memory_parameters=compute_memory)
    return target,timing,contract
