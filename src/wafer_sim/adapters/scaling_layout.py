"""Predetermined locality/load tradeoff; never search measured performance."""
from collections import Counter
from wafer_sim.adapters.memory_machine_workload import place
from wafer_sim.execution.plan import Placement


def place_scaled(metadata, side, layout):
    if metadata['dimensions']['workers'] != side*side or layout not in {'local', 'remote_balanced', 'clustered_local'}:
        raise ValueError('Invalid square-work placement')
    baseline = place(metadata, 'near')
    homes = dict(baseline.data)
    for name, info in metadata['data_roles'].items():
        if info['role'] not in {'first_weight', 'second_weight', 'output'}: continue
        row, col = divmod(info['worker'], side)
        if layout == 'remote_balanced': row = (row+side//2) % side
        elif layout == 'clustered_local': row, col = 2*(row//2), 2*(col//2)
        bank = 1 if info['role'] == 'second_weight' else 0
        homes[name] = f'dram-{row*side+col}-{bank}'
    return Placement(baseline.compute, homes)


def capacity_bound(binding):
    """Even reserving every operation at once fits: staging cannot be a bottleneck."""
    total = Counter()
    for data in binding.graph.data.values():
        if data.producer is None and (data.retain or binding.graph.consumers[data.id]):
            total[binding.homes[data.id]] += data.size_bytes
    for plan in binding.plans.values():
        for a in plan.reservations: total[a.memory] += a.size_bytes
    if any(n > binding.memory[m].capacity_bytes for m, n in total.items()):
        raise ValueError('All-operation capacity bound exceeds the fixed physical budget')
    return dict(passed=True, all_live_upper_bytes=dict(total),
                limits={k: v.capacity_bytes for k, v in binding.memory.items()})
