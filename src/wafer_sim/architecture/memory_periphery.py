"""Explicit storage partition attachment; no transaction/scheduling policy."""
from dataclasses import dataclass

from wafer_sim.architecture.spatial import Target


@dataclass(frozen=True)
class NetworkInterface:
    id: str
    endpoint: int
    memory_regions: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class PeripheryTarget(Target):
    # Ordinary Target remains byte-for-byte serializable as the original v1.
    network_interfaces: tuple[NetworkInterface, ...]
