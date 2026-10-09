"""Small declared cases for API equivalence, never application performance data."""
from dataclasses import replace
from pathlib import Path

from wafer_sim.architecture.wafer_machine import from_config
from wafer_sim.execution.plan import Placement
from wafer_sim.io import read_json
from wafer_sim.workloads.spatial import DataObject, Operation, Workload

NAMES = ('bank_whole_read', 'controller_whole_read', 'controller_pipeline_read',
         'controller_pipeline_write', 'controller_pipeline_two_bank',
         'controller_pipeline_two_operands', 'controller_pipeline_external',
         'controller_pipeline_consumer', 'controller_pipeline_blocked', 'controller_pipeline_plan_order')


def inputs(name, repo=None):
    if name not in NAMES:
        raise ValueError('Unknown public regression case')
    repo = Path(repo) if repo is not None else Path(__file__).resolve().parents[1]
    cfg = read_json(repo/'configs/wafer_machine.json'); cfg['array'] = [2, 2]
    machine = from_config(cfg)
    shared = name.startswith('controller_')
    kind = 'pipeline' if '_pipeline_' in name else 'whole'
    size = 5*4096+1  # remainder and window reuse, without a native binary
    write = name.endswith('_write')
    count = 2 if name.endswith(('_two_bank', '_plan_order')) else 1
    data, operations, homes, compute = [], [], {}, {}
    for i in range(count):
        x, y = f'x{i}', f'y{i}'
        op = ('f2', 'f10')[i] if name.endswith('_plan_order') else f'f{i}'
        data.extend((DataObject(x, 64 if write else size, None, False, 'Public fixture'),
                     DataObject(y, size if write else 64, op, True, 'Public fixture')))
        operations.append(Operation(op, (x,), (y,), (('mac', 256),), 0, (), 'Public fixture'))
        compute[op] = f'c{i}'
        homes[x] = f'sram-{i}' if write else (f'dram-0-{i}' if count == 2 else 'dram-3-0')
        homes[y] = 'dram-3-1' if write else f'sram-{i}'
    if name.endswith('_external'):
        homes['x0'] = 'host-memory'
    if name.endswith('_two_operands'):
        data.append(DataObject('z', size, None, False, 'Public fixture'))
        homes['z'] = 'dram-3-1'
        operations[0] = replace(operations[0], inputs=('x0', 'z'))
    if name.endswith('_consumer'):
        data.append(DataObject('z', 64, 'g', True, 'Public fixture')); homes['z'] = 'sram-0'
        operations.append(Operation('g', ('y0',), ('z',), (('mac', 2560000),), 0, (), 'Public fixture'))
        compute['g'] = 'c0'
    if name.endswith('_blocked'):
        homes['x0'] = 'dram-0-0'
        machine = replace(machine, controllers=tuple(
            replace(c, buffer_bytes=1) if c.id == 'controller-0' else c for c in machine.controllers))
    return machine, Workload(tuple(data), tuple(operations)), Placement(compute, homes), shared, kind
