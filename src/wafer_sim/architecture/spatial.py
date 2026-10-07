"""Explicit target identities and capacities; timing calibration is separate."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryRegion:
    id: str
    endpoint: int
    capacity_bytes: int
    read_port: str
    write_port: str
    provenance: str


@dataclass(frozen=True)
class ComputeResource:
    id: str
    memory: str
    work_units: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class Network:
    endpoint_routers: tuple[tuple[int, int], ...]
    router_links: tuple[tuple[int, int], ...]  # bidirectional physical connectivity
    provenance: str


@dataclass(frozen=True)
class Target:
    memory: tuple[MemoryRegion, ...]
    compute: tuple[ComputeResource, ...]
    network: Network
