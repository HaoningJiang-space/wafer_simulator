"""Explicit resource service parameters, separate from workload and scheduling."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    resource: str
    unit: str
    rate_numerator: int
    rate_denominator: int = 1
    latency_cycles: int = 0


@dataclass(frozen=True)
class Link:
    source: int
    destination: int
    service: Service  # directed serialization resource, bytes per cycle


@dataclass(frozen=True)
class Endpoint:
    endpoint: int
    injection: Service
    ejection: Service


@dataclass(frozen=True)
class Timing:
    services: tuple[Service, ...]  # compute units and memory ports
    links: tuple[Link, ...]
    endpoints: tuple[Endpoint, ...]
    provenance: str
