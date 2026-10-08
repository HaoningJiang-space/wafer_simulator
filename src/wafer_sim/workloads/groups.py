"""Disjoint, identity-preserving copies of complete logical workloads."""
from dataclasses import replace

from wafer_sim.workloads.spatial import Workload, validate


def namespace(workload, group):
    if not isinstance(group, str) or not group.isalnum():
        raise ValueError('Group must be a nonempty alphanumeric identity')
    validate(workload)
    name = lambda value: group + '/' + value
    return Workload(
        tuple(replace(d, id=name(d.id), producer=name(d.producer) if d.producer else None)
              for d in workload.data),
        tuple(replace(op, id=name(op.id), inputs=tuple(map(name, op.inputs)),
              outputs=tuple(map(name, op.outputs)), control_deps=tuple(map(name, op.control_deps)),
              collective=replace(op.collective, id=name(op.collective.id)) if op.collective else None)
              for op in workload.operations))


def independent_groups(workload, groups):
    groups = tuple(groups)
    if not groups or len(set(groups)) != len(groups):
        raise ValueError('Unique nonempty groups required')
    copies = [namespace(workload, group) for group in groups]
    combined = Workload(tuple(d for w in copies for d in w.data),
                        tuple(op for w in copies for op in w.operations))
    validate(combined)
    return combined
