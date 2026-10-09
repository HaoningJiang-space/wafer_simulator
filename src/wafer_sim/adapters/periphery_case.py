"""Public ordinary-operation periphery cases, independent of study/server setup.

Compilation consumes explicit machine/work/placement/policy objects. Readback
restores the supplied plan rather than lowering an application again; physical
target consistency is checked by the existing machine compiler. No backend is
started, no repository is read and no experiment configuration is consulted.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from types import MappingProxyType

from wafer_sim.adapters.memory_periphery import compile_periphery, bind_periphery, TransactionPolicy
from wafer_sim.adapters.wafer_machine import compile_machine
from wafer_sim.adapters.spatial import validate_target
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.architecture.wafer_machine import WaferMachine, Layer, Tile, Connection, Store, Controller
from wafer_sim.execution.plan import (Placement, Binding, OperationPlan, Allocation, Phase, Demand, Transfer)
from wafer_sim.io import object_digest
from wafer_sim.workloads.spatial import DataObject, Operation, Workload, validate


@dataclass(frozen=True)
class PeripheryCase:
    compiled: object
    workload: Workload
    placement: Placement
    binding: Binding
    transactions: list
    policy: TransactionPolicy

    def to_record(self, *, condition=None, layout=None, component=None, include_capacity_bound=False):
        """Portable JSON input; labels do not select a machine or timing policy.

        Preserve the accepted input layout for existing archived runs. The
        optional all-operation capacity upper bound is a study check, not a
        requirement for ordinary execution with finite capacity admission.
        """
        record = dict(condition=condition, layout=layout, component=component,
            physical=dict(inventory=asdict(self.compiled.physical), target=asdict(self.compiled.target),
                          timing=asdict(self.compiled.timing)),
            workload=asdict(self.workload), placement=asdict(self.placement),
            transaction_policy=asdict(self.policy), transactions=deepcopy(self.transactions),
            plans={op: asdict(plan) for op, plan in self.binding.plans.items()})
        if include_capacity_bound:
            from wafer_sim.adapters.scaling_layout import capacity_bound
            record['capacity_bound'] = capacity_bound(self.binding)
        return record


def compile_case(machine, workload, placement, policy, *, interface_organization='controller'):
    """Compile a declared case using unchanged bank/controller NIC semantics."""
    if interface_organization not in {'bank', 'controller'}:
        raise ValueError('Interface organization must be bank or controller')
    compiled = compile_machine(machine) if interface_organization == 'bank' else compile_periphery(machine)
    binding, transactions = bind_periphery(workload, compiled, placement, policy)
    return PeripheryCase(compiled, workload, placement, binding, transactions, policy)


def _machine(inventory):
    values = dict(inventory)
    for field, cls in (('layers', Layer), ('tiles', Tile), ('connections', Connection),
                       ('stores', Store), ('controllers', Controller)):
        values[field] = tuple(cls(**row) for row in values[field])
    values['compute_rates'] = tuple(tuple(row) for row in values['compute_rates'])
    return WaferMachine(**values)


def _workload(record):
    operations = []
    for row in record['operations']:
        if row.get('collective') is not None:
            raise ValueError('Periphery input supports ordinary operations only')
        values = dict(row)
        for field in ('inputs', 'outputs', 'control_deps'):
            values[field] = tuple(values[field])
        values['work'] = tuple(tuple(entry) for entry in values['work'])
        operations.append(Operation(**values))
    return Workload(tuple(DataObject(**row) for row in record['data']), tuple(operations))


def _plan(record):
    values = dict(record)
    values['reservations'] = tuple(Allocation(**dict(row, key=tuple(row['key']))) for row in values['reservations'])
    values['phases'] = tuple(Phase(row['kind'], tuple(Demand(**d) for d in row['demands']),
                                  Transfer(**row['transfer']) if row['transfer'] is not None else None)
                             for row in values['phases'])
    if values.get('dependencies') is not None:
        values['dependencies'] = tuple(tuple(row) for row in values['dependencies'])
    values['action_ids'] = tuple(values.get('action_ids', ()))
    values['output_requirements'] = tuple((name, tuple(phases)) for name, phases in values.get('output_requirements', ()))
    return OperationPlan(**values)


def case_from_record(record):
    """Restore given inputs/plans for execution or independent audit.

    Do not call bind_periphery(), bind_machine() or a workload generator here.
    The supplied plan remains visible to the independent policy audit, including
    a malformed output publication plan. A record is input, not an acceptance
    certificate; callers must audit the resulting/saved execution.
    """
    required = {'condition', 'layout', 'component', 'physical', 'workload', 'placement',
                'transaction_policy', 'transactions', 'plans'}
    if not required <= set(record) or set(record) - required - {'capacity_bound'}:
        raise ValueError('Unknown or missing periphery input fields')
    try:
        machine = _machine(record['physical']['inventory'])
        shared = 'network_interfaces' in record['physical']['target']
        compiled = compile_periphery(machine) if shared else compile_machine(machine)
        physical = dict(inventory=asdict(machine), target=asdict(compiled.target), timing=asdict(compiled.timing))
        if object_digest(physical) != object_digest(record['physical']):
            raise ValueError('Stored target/timing differs from declared physical inventory')
        workload = _workload(record['workload']); graph = validate(workload)
        placement = Placement(**record['placement']); policy = TransactionPolicy(**record['transaction_policy'])
        memory, compute, _, _ = validate_target(compiled.target)
        if set(placement.data) != set(graph.data) or set(placement.compute) != set(graph.operations):
            raise ValueError('Placement must cover all and only logical objects/operations')
        if any(m not in memory for m in placement.data.values()) or any(c not in compute for c in placement.compute.values()):
            raise ValueError('Placement refers to an absent resource')
        for data in graph.data.values():
            if data.size_bytes > memory[placement.data[data.id]].capacity_bytes:
                raise ValueError('Data object cannot fit in its home region')
        for op in graph.operations.values():
            if any(unit not in compute[placement.compute[op.id]].work_units for unit, _ in op.work):
                raise ValueError('Target compute resource cannot serve declared work')
        if set(record['plans']) != set(graph.operations):
            raise ValueError('Missing or extra operation plan')
        # JSON object keys may be sorted; the lowering follows graph.order.
        plans = {op: _plan(record['plans'][op]) for op in graph.order}
        binding = Binding(graph, MappingProxyType({**memory, **{m.id: m for m in compiled.controller_buffers}}),
                          MappingProxyType(dict(placement.data)), MappingProxyType(plans), compiled.target.network)
        TimedTarget(binding, compiled.timing)
        case = PeripheryCase(compiled, workload, placement, binding, deepcopy(record['transactions']), policy)
        # This also rejects fields discarded by nested decoding. It validates
        # an optional archived capacity bound without imposing one on all users.
        rebuilt = case.to_record(condition=record['condition'], layout=record['layout'], component=record['component'],
                                 include_capacity_bound='capacity_bound' in record)
        if object_digest(rebuilt) != object_digest(record):
            raise ValueError('Input record changed during plan restoration')
        return case
    except (KeyError, TypeError) as error:
        raise ValueError('Malformed periphery input record') from error
