"""Logical immutable data/work, without source durations or target placement.

Version 1 supports whole, non-aliasing data objects and already-lowered
collectives. Provenance labels describe evidence, not an accuracy certificate.
"""
from dataclasses import dataclass
from types import MappingProxyType

from wafer_sim.workloads.dag import validate as validate_dag


def identifier(value, label):
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} needs a nonempty string identity")


def natural(value, label, positive=False):
    if type(value) is not int or value < int(positive):
        raise ValueError(f"Invalid {label}: expected {'positive' if positive else 'nonnegative'} integer")


@dataclass(frozen=True)
class DataObject:
    id: str
    size_bytes: int
    producer: str | None
    retain: bool
    provenance: str


@dataclass(frozen=True)
class Operation:
    id: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    work: tuple[tuple[str, int], ...]
    scratch_bytes: int
    control_deps: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class Workload:
    data: tuple[DataObject, ...]
    operations: tuple[Operation, ...]


@dataclass(frozen=True)
class LogicalGraph:
    data: object
    operations: object
    predecessors: object
    consumers: object
    order: tuple[str, ...]


def validate(workload):
    """Validate declared semantics; reuse the existing completion-DAG checker."""
    if type(workload.data) is not tuple or type(workload.operations) is not tuple:
        raise ValueError("Logical collections must be immutable tuples")
    data = {d.id: d for d in workload.data}
    operations = {op.id: op for op in workload.operations}
    if not operations or len(data) != len(workload.data) or len(operations) != len(workload.operations):
        raise ValueError("Empty operations or duplicate logical identities")
    produced = {op: set() for op in operations}
    for d in data.values():
        identifier(d.id, "Data")
        identifier(d.provenance, "Data provenance")
        natural(d.size_bytes, "data size", positive=True)
        if type(d.retain) is not bool:
            raise ValueError("Data retention must be explicit")
        if d.producer is not None and d.producer not in operations:
            raise ValueError("Missing data producer")
        if d.producer is not None:
            produced[d.producer].add(d.id)
    parents, consumers = {}, {d: set() for d in data}
    for op in operations.values():
        identifier(op.id, "Operation")
        identifier(op.provenance, "Operation provenance")
        natural(op.scratch_bytes, "scratch bytes")
        for values in (op.inputs, op.outputs, op.control_deps):
            if type(values) is not tuple or len(values) != len(set(values)):
                raise ValueError("Operation references must be unique immutable tuples")
        if any(d not in data for d in op.inputs + op.outputs):
            raise ValueError("Missing data object")
        if any(dep not in operations for dep in op.control_deps):
            raise ValueError("Missing control dependency")
        if set(op.outputs) != produced[op.id]:
            raise ValueError("Outputs and declared producer disagree")
        if type(op.work) is not tuple or not op.work:
            raise ValueError("Explicit operation work is required; durations are not work")
        units = set()
        for entry in op.work:
            if type(entry) is not tuple or len(entry) != 2:
                raise ValueError("Work entries must be immutable (unit, amount) pairs")
            unit, amount = entry
            identifier(unit, "Work unit")
            natural(amount, "work amount", positive=True)
            if unit in units or unit in {"cycles", "ns", "us", "ms", "seconds"}:
                raise ValueError("Duplicate work unit or timing substituted for work")
            units.add(unit)
        dependencies = set(op.control_deps)
        for d in op.inputs:
            consumers[d].add(op.id)
            if data[d].producer is not None:
                dependencies.add(data[d].producer)
        parents[op.id] = frozenset(dependencies)
    ids = {name: i for i, name in enumerate(operations)}
    shadow = dict(ranks=1, nodes=[dict(id=ids[name], rank=0, kind="join",
        duration_cycles=0, bytes=0, release_cycle=0,
        deps=sorted(ids[dep] for dep in parents[name])) for name in operations])
    order, _ = validate_dag(shadow)
    names = tuple(operations)
    return LogicalGraph(MappingProxyType(data), MappingProxyType(operations),
        MappingProxyType(parents), MappingProxyType({d: frozenset(cs) for d, cs in consumers.items()}),
        tuple(names[i] for i in order))
