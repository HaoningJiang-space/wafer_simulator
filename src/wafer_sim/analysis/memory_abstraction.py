"""Independent readback of memory projection, work and model-selection errors."""
from collections import Counter
from dataclasses import asdict
from fractions import Fraction
from itertools import combinations

from wafer_sim.analysis.online_network import audit_messages


def audit_network(network, result):
    spec = result['uniform_memory_contract']
    if spec['model'] not in {'U0', 'U1'}:
        raise ValueError('Unexpected uniform contract')
    raw = result['native_network_messages']
    audit_messages(network, raw)
    native = {m['token']: m for m in raw}
    seen, identities, forwarded = set(), set(), set()
    attachments = dict(network.endpoint_routers)
    fields = ('token', 'ready', 'finish', 'bytes', 'source', 'destination', 'data', 'source_memory', 'destination_memory')
    for m in result['network_messages']:
        if m['token'] in seen or m['id'] in identities:
            raise ValueError('Duplicate projected message')
        seen.add(m['token']); identities.add(m['id'])
        if any(type(m[k]) is not int or m[k] < 0 for k in ('ready', 'finish', 'id', 'bytes')) or m['bytes'] == 0:
            raise ValueError('Invalid projected clock/payload')
        if m['source'] not in attachments or m['destination'] not in attachments or m['source'] == m['destination']:
            raise ValueError('Invalid projected endpoints')
        uniform = m['source_memory'] in spec['dram_regions'] or m['destination_memory'] in spec['dram_regions']
        if uniform:
            width = spec['flit_bytes']
            duration = (m['bytes']+width-1)//width+spec['uniform_startup_cycles']
            if m['engine'] != 'uniform' or m['finish'] != m['ready']+duration or m['token'] in native or 'flits' in m:
                raise ValueError('Uniform cost, classification or evidence violation')
        else:
            n = native.get(m['token'])
            if not n or m['engine'] != 'booksim' or m.get('native_id') != n['id'] or any(m[k] != n[k] for k in fields):
                raise ValueError('Native passthrough differs')
            forwarded.add(m['token'])
    if identities != set(range(len(seen))) or forwarded != set(native):
        raise ValueError('Missing projected/native message')
    return dict(passed=True, native_messages=len(raw), uniform_messages=len(seen)-len(raw))


def audit_projection(compiled, base, binding, timing, spec):
    """Check expected physical totals without using the projection generator."""
    machine = compiled.physical
    banks = {s.id: s for s in machine.stores if s.kind == 'dram'}
    controllers = {c.id: c for c in machine.controllers if c.id in {s.controller for s in banks.values()}}
    startup = 2*machine.access_latency_cycles+2*machine.router_latency_cycles
    hb = {c.latency_cycles for c in machine.connections if c.kind == 'hb'}
    if len(hb) != 1 or spec['uniform_startup_cycles'] != startup+next(iter(hb)) or spec['flit_bytes'] != machine.flit_bytes:
        raise ValueError('Uniform cost does not derive from the fixed machine')
    if set(spec['dram_regions']) != set(banks):
        raise ValueError('Changed DRAM identities')
    resource_map = {**{k+'/port': 'uniform/bank' for k in banks},
                    **{k+'/'+kind: 'uniform/'+kind for k in controllers for kind in ('command', 'channel')}}
    if spec['resource_map'] != resource_map:
        raise ValueError('Wrong resource projection')
    pooled = spec['model'] == 'U0'
    if spec['model'] not in {'U0', 'U1', 'S'}:
        raise ValueError('Unknown model')
    if binding.graph != base.graph or binding.network != base.network or set(binding.plans) != set(base.plans):
        raise ValueError('Changed work or physical graph')
    expected_homes = {d: 'uniform/dram' if pooled and h in banks else h for d, h in base.homes.items()}
    if dict(binding.homes) != expected_homes:
        raise ValueError('Changed logical object homes outside declared pooling')
    for op, original in base.plans.items():
        before, after = asdict(original), asdict(binding.plans[op])
        if pooled:
            for allocation in before['reservations']:
                if allocation['memory'] in banks: allocation['memory'] = 'uniform/dram'
            for phase in before['phases']:
                for demand in phase['demands']:
                    demand['resource'] = resource_map.get(demand['resource'], demand['resource'])
        if before != after:
            raise ValueError('Changed work, protocol, staging guard or retirement policy')
    expected_services = {(s.resource, s.unit): s for s in compiled.timing.services}
    actual = {(s.resource, s.unit): s for s in timing.services}
    if len(actual) != len(timing.services): raise ValueError('Duplicated shared resource')
    if pooled:
        for key in resource_map: expected_services.pop((key, 'bytes'))
        rates = {'uniform/bank': sum(Fraction(s.bytes_per_cycle) for s in banks.values()),
                 'uniform/channel': sum(Fraction(c.channel_bytes_per_cycle) for c in controllers.values()),
                 'uniform/command': sum(Fraction(16, c.command_cycles) for c in controllers.values())}
        latency = {s.latency_cycles for s in banks.values()}
        if len(latency) != 1: raise ValueError('Unequal bank latencies')
        for name, rate in rates.items():
            s = actual.pop((name, 'bytes'))
            if Fraction(s.rate_numerator, s.rate_denominator) != rate or s.latency_cycles != (next(iter(latency)) if name == 'uniform/bank' else 0):
                raise ValueError('Pooled service budget changed')
        memory = dict(binding.memory)
        pool = memory.pop('uniform/dram')
        if pool.capacity_bytes != sum(s.capacity_bytes for s in banks.values()):
            raise ValueError('Pooled capacity budget changed')
        if memory != {k: v for k, v in base.memory.items() if k not in banks}:
            raise ValueError('Changed non-DRAM capacity or physical staging')
    elif dict(binding.memory) != dict(base.memory):
        raise ValueError('Changed physical capacities')
    if actual != expected_services or timing.links != compiled.timing.links or timing.endpoints != compiled.timing.endpoints:
        raise ValueError('Changed unprojected services or fabric')
    return dict(passed=True, physical_staging_preserved=True, logical_work_preserved=True)


def audit(compiled, base, binding, timing, spec, result):
    from wafer_sim.analysis.timing import audit as audit_timing
    projection = audit_projection(compiled, base, binding, timing, spec)
    if spec['model'] != 'S' and result['uniform_memory_contract'] != spec:
        raise ValueError('Result uses another model contract')
    execution = audit_timing(binding, timing, result)
    return dict(passed=True, projection=projection, execution=execution,
        status=dict(execution_completed=True, semantic_audit_passed=True,
            aggregate_capacity='feasible', controller_staging_capacity='feasible',
            per_bank_capacity='unmodeled' if spec['model'] == 'U0' else 'feasible',
            dram_spatial_contention='modeled' if spec['model'] == 'S' else 'unmodeled',
            hardware_calibration='declared assumptions; not hardware measurement',
            streaming_rx_capacity='unmodeled'),
        logical_message_bytes=sum(m['bytes'] for m in result['network_messages']),
        logical_messages=len(result['network_messages']),
        work_by_unit=dict(sum((Counter({e['unit']: e['amount']}) for e in result['services']), Counter())))


def selection(rows, tolerance):
    """Do not resolve ties lexically: report the reference regret of every choice."""
    lookup = {(r['model'], r['layout']): r['application_cycles'] for r in rows}
    layouts = sorted({r['layout'] for r in rows})
    reference_best = min(lookup['S', p] for p in layouts)
    pairs, choices = [], []
    relation = lambda gap: 'tie' if abs(gap) <= tolerance else ('first' if gap < 0 else 'second')
    for model in ('U0', 'U1', 'S'):
        best = min(lookup[model, p] for p in layouts)
        candidates = [p for p in layouts if lookup[model, p] <= best+tolerance]
        regrets = [lookup['S', p]-reference_best for p in candidates]
        choices.append(dict(model=model, candidates=candidates, reference_regret_min_cycles=min(regrets),
                            reference_regret_max_cycles=max(regrets)))
        for a, b in combinations(layouts, 2):
            gap = lookup[model, a]-lookup[model, b]
            ref = lookup['S', a]-lookup['S', b]
            pairs.append(dict(model=model, first=a, second=b, gap_cycles=gap, reference_gap_cycles=ref,
                gap_error_cycles=gap-ref, predicted_relation=relation(gap), reference_relation=relation(ref),
                selection_disagreement=relation(gap) != relation(ref)))
    return dict(tie_tolerance_cycles=tolerance, pairs=pairs, choices=choices)
