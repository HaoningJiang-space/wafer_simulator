"""Validate target service rates and lower phases to explicit service steps.

Network policy: deterministic minimum-hop paths, lowest router ID on ties;
whole-message store-and-forward. Each endpoint/link serializes bytes, then
propagation latency elapses without retaining the serialization resource.
This coarse timing model is not BookSim's flit/credit model.
"""
from collections import deque
from dataclasses import dataclass

from wafer_sim.workloads.spatial import identifier, natural


@dataclass(frozen=True)
class Step:
    resource: str
    unit: str
    amount: int
    category: str


class TimedTarget:
    def __init__(self, binding, timing):
        identifier(timing.provenance, "Timing provenance")
        self.binding, self.timing = binding, timing
        self.services = {}
        self.links = {(link.source, link.destination): link.service for link in timing.links}
        self.endpoints = {e.endpoint:e for e in timing.endpoints}
        if len(self.links) != len(timing.links) or len(self.endpoints) != len(timing.endpoints):
            raise ValueError("Duplicate timing link or endpoint")
        attachments = dict(binding.network.endpoint_routers)
        physical = {edge for a,b in binding.network.router_links for edge in ((a,b),(b,a))}
        if set(self.links) != physical or set(self.endpoints) != set(attachments):
            raise ValueError("Timing must cover the exact physical links and endpoints")
        all_services = [*timing.services, *(l.service for l in timing.links),
                        *(s for e in timing.endpoints for s in (e.injection,e.ejection))]
        network_ids = {s.resource for s in all_services[len(timing.services):]}
        if network_ids & {s.resource for s in timing.services}:
            raise ValueError("Network and compute/memory service IDs must be distinct")
        for service in all_services:
            identifier(service.resource, "Timed resource")
            identifier(service.unit, "Service unit")
            natural(service.rate_numerator, "Service rate numerator", positive=True)
            natural(service.rate_denominator, "Service rate denominator", positive=True)
            natural(service.latency_cycles, "Service latency")
            key = service.resource, service.unit
            if key in self.services and self.services[key] != service:
                raise ValueError("Conflicting shared-resource service definition")
            self.services[key] = service
        if any(s.unit != "bytes" for s in all_services[len(timing.services):]):
            raise ValueError("Network services must serialize bytes")
        self.attachments = attachments
        self.neighbors = {}
        for a,b in physical:
            self.neighbors.setdefault(a, []).append(b)
        for neighbors in self.neighbors.values(): neighbors.sort()
        self.paths = {}
        # Validate all demands before starting execution, including late phases.
        for plan in binding.plans.values():
            for phase in plan.phases: self.steps(phase)

    def route(self, source, destination):
        key = source,destination
        if key not in self.paths:
            if source not in self.attachments or destination not in self.attachments:
                raise ValueError("Transfer endpoint absent from target")
            start, end = self.attachments[source],self.attachments[destination]
            parents, pending = {start:None},deque([start])
            while pending and end not in parents:
                current = pending.popleft()
                for neighbor in self.neighbors.get(current, ()):
                    if neighbor not in parents:
                        parents[neighbor] = current
                        pending.append(neighbor)
            if end not in parents: raise ValueError("No physical transfer path")
            path, current = [],end
            while current is not None:
                path.append(current); current = parents[current]
            self.paths[key] = tuple(reversed(path))
        return self.paths[key]

    def steps(self, phase):
        if phase.transfer is not None:
            if phase.demands or phase.kind != "transfer":
                raise ValueError("Transfer cannot hide compute/memory demands")
            transfer = phase.transfer
            natural(transfer.size_bytes, "Transfer bytes", positive=True)
            path = self.route(transfer.source_endpoint, transfer.destination_endpoint)
            services = [self.endpoints[transfer.source_endpoint].injection,
                        *(self.links[a,b] for a,b in zip(path,path[1:])),
                        self.endpoints[transfer.destination_endpoint].ejection]
            return tuple(Step(s.resource, "bytes", transfer.size_bytes, "network") for s in services)
        if phase.kind not in {"compute", "memory_read", "memory_write"} or not phase.demands:
            raise ValueError("Expected a nonempty compute or memory phase")
        result = []
        for demand in phase.demands:
            natural(demand.amount, "Service work", positive=True)
            if (demand.resource,demand.unit) not in self.services:
                raise ValueError("Missing target service rate")
            result.append(Step(demand.resource,demand.unit,demand.amount,
                               "compute" if phase.kind == "compute" else "memory"))
        return tuple(result)
