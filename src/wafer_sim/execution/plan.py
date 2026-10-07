"""Resource demands and reservations consumed by execution state/backends."""
from dataclasses import dataclass
from collections.abc import Mapping

from wafer_sim.architecture.spatial import MemoryRegion, Network
from wafer_sim.workloads.spatial import LogicalGraph


@dataclass(frozen=True)
class Placement:
    compute: Mapping[str, str]  # operation -> compute resource
    data: Mapping[str, str]  # data -> home memory region


@dataclass(frozen=True)
class Allocation:
    key: tuple[str, ...]
    memory: str
    size_bytes: int


@dataclass(frozen=True)
class Demand:
    resource: str
    unit: str
    amount: int


@dataclass(frozen=True)
class Transfer:
    data: str
    source_memory: str
    destination_memory: str
    source_endpoint: int
    destination_endpoint: int
    size_bytes: int


@dataclass(frozen=True)
class Phase:
    kind: str
    demands: tuple[Demand, ...] = ()
    transfer: Transfer | None = None


@dataclass(frozen=True)
class ExecutionPolicy:
    collective_algorithm: str = "direct_exchange_rank_order_sum"
    collective_completion: str = "rank_local"

    def __post_init__(self):
        if self.collective_algorithm != "direct_exchange_rank_order_sum":
            raise ValueError("Unsupported collective algorithm")
        if self.collective_completion not in {"rank_local", "global_retirement"}:
            raise ValueError("Unsupported collective completion policy")


@dataclass(frozen=True)
class OperationPlan:
    reservations: tuple[Allocation, ...]
    phases: tuple[Phase, ...]
    # None retains sequential phases. Collective actions have an explicit DAG.
    dependencies: tuple[tuple[int, ...], ...] | None = None
    action_ids: tuple[str, ...] = ()
    policy: str = ""
    # Empty means ordinary operation outputs publish at retirement. Explicit
    # collective requirements name the writes that make each local value ready.
    output_requirements: tuple[tuple[str, tuple[int, ...]], ...] = ()

    def predecessors(self, index):
        return self.dependencies[index] if self.dependencies is not None else ((index-1,) if index else ())

    def output_phases(self, data):
        return dict(self.output_requirements)[data] if self.output_requirements else tuple(range(len(self.phases)))


@dataclass(frozen=True)
class Binding:
    graph: LogicalGraph
    memory: Mapping[str, MemoryRegion]
    homes: Mapping[str, str]
    plans: Mapping[str, OperationPlan]
    network: Network
