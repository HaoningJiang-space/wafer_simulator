"""Explicit projections of one machine; never alter its physical declaration.

U0 pools DRAM service/capacity but retains physical controller staging guards.
U1 retains storage resources. Both replace only DRAM communication by the same
independent one-HB cost. Neither projection certifies omitted spatial resources.
"""
from dataclasses import replace
from fractions import Fraction
from types import MappingProxyType

from wafer_sim.architecture.spatial import MemoryRegion
from wafer_sim.architecture.timing import Service


def contract(compiled, model):
    if model not in {'U0', 'U1', 'S'}:
        raise ValueError('Unknown memory abstraction')
    m = compiled.physical
    banks = [s for s in m.stores if s.kind == 'dram']
    controllers = [c for c in m.controllers if c.id in {s.controller for s in banks}]
    hb = {c.latency_cycles for c in m.connections if c.kind == 'hb'}
    latencies = {s.latency_cycles for s in banks}
    if not banks or len(hb) != 1 or len(latencies) != 1:
        raise ValueError('Initial uniform reference requires homogeneous bank latency and HB latency')
    command_rate = sum((Fraction(16, c.command_cycles) for c in controllers), Fraction())
    return dict(model=model, dram_regions=[s.id for s in banks],
        flit_bytes=m.flit_bytes,
        uniform_startup_cycles=2*m.access_latency_cycles+2*m.router_latency_cycles+next(iter(hb)),
        formula='ceil(payload_bytes / flit_bytes) + 2*access + 2*router + HB',
        communication='independent unloaded one-HB cost; no DRAM path/endpoint sharing' if model != 'S' else 'native BookSim',
        staging='unchanged per-controller reservations held until whole-operation retirement',
        pools=dict(capacity_bytes=sum(s.capacity_bytes for s in banks),
            bank_bytes_per_cycle=sum(s.bytes_per_cycle for s in banks),
            bank_latency_cycles=next(iter(latencies)),
            channel_bytes_per_cycle=sum(c.channel_bytes_per_cycle for c in controllers),
            command_rate_numerator=command_rate.numerator,
            command_rate_denominator=command_rate.denominator),
        resource_map={**{s.id+'/port': 'uniform/bank' for s in banks},
            **{c.id+'/command': 'uniform/command' for c in controllers},
            **{c.id+'/channel': 'uniform/channel' for c in controllers}})


def project(compiled, binding, model):
    spec = contract(compiled, model)
    if model != 'U0':
        return binding, compiled.timing, spec
    banks, names, pool = set(spec['dram_regions']), spec['resource_map'], spec['pools']
    regions = {k: v for k, v in binding.memory.items() if k not in banks}
    regions['uniform/dram'] = MemoryRegion('uniform/dram', binding.memory[spec['dram_regions'][0]].endpoint,
        pool['capacity_bytes'], 'uniform/bank', 'uniform/bank', 'U0 capacity projection, not a physical store')
    plans = {}
    for op, plan in binding.plans.items():
        plans[op] = replace(plan,
            reservations=tuple(replace(a, memory='uniform/dram') if a.memory in banks else a
                               for a in plan.reservations),
            phases=tuple(replace(p, demands=tuple(replace(d, resource=names.get(d.resource, d.resource))
                                                  for d in p.demands)) for p in plan.phases))
    services = tuple(s for s in compiled.timing.services if s.resource not in names) + (
        Service('uniform/bank', 'bytes', pool['bank_bytes_per_cycle'], latency_cycles=pool['bank_latency_cycles']),
        Service('uniform/channel', 'bytes', pool['channel_bytes_per_cycle']),
        Service('uniform/command', 'bytes', pool['command_rate_numerator'], pool['command_rate_denominator']))
    return replace(binding, memory=MappingProxyType(regions), plans=MappingProxyType(plans),
        homes=MappingProxyType({d: 'uniform/dram' if home in banks else home for d, home in binding.homes.items()})), \
        replace(compiled.timing, services=services), spec
