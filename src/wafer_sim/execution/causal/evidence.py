"""Evidence consumers; exact service decisions do not read these containers.

Counters mode constructs no event dictionaries. Packet/source state remains
eager in R2.2; reducing that state is a separate, single-flow R3 option.
Compact schema 1 is decoded independently in analysis.causal_evidence.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field

STREAMS = ('service', 'inputs', 'credits', 'credit_sends', 'allocations',
           'injections', 'ejections', 'retired')
PRODUCER = 'Explicit causal core compact evidence'


def event_row(name, args):
    """Construct a recording row only when a consumer actually needs it."""
    if name == 'service':
        kind, router, flit, cycle, port = args
        row = dict(kind=kind, router=router, flit=flit, cycle=cycle)
        if port is not None:
            row['input'] = port
        return row
    if name == 'inputs':
        router, port, flit, cycle = args
        return dict(router=router, input=port, flit=flit, cycle=cycle)
    if name == 'credits':
        target, number, cycle, amount = args
        return dict(target=target, number=number, cycle=cycle, amount=amount)
    if name == 'credit_sends':
        router, port, cycle, amount = args
        return dict(router=router, input=port, cycle=cycle, amount=amount)
    if name == 'allocations':
        router, cycle, vc, sw, vp, sp, owner, credit, queues = args
        return dict(router=router, cycle=cycle, vc_requests=list(vc), sw_requests=list(sw),
            vc_pointer=vp, sw_pointer=sp, owner=owner, credit_slots=credit,
            occupancy=[len(q) for q in queues], heads=[q[0] if q else -1 for q in queues])
    if name in ('injections', 'ejections'):
        message, cycle = args
        return dict(message=message, cycle=cycle)
    if name == 'retired':
        return dict(deepcopy(args[0]), hops=len(args[0]['router_path']))
    raise ValueError('Unknown evidence stream')


@dataclass
class FullEvidence:
    """Default legacy-compatible tables; retired rows retain existing metadata."""
    injections: dict = field(default_factory=lambda: defaultdict(list))
    ejections: dict = field(default_factory=lambda: defaultdict(list))
    service: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    credits: list = field(default_factory=list)
    credit_sends: list = field(default_factory=list)
    allocations: list = field(default_factory=list)
    retired: list = field(default_factory=list)
    mode = 'full'

    def emit(self, name, *args):
        if name in ('injections', 'ejections'):
            getattr(self, name)[args[0]].append(args[1])
        elif name == 'retired':
            self.retired.append(args[0])
        else:
            getattr(self, name).append(event_row(name, args))

    def flits(self, message):
        return sorted((dict(deepcopy(row), hops=len(row['router_path']))
                       for row in self.retired if row['message'] == message),
                      key=lambda row: (row['ejected'], row['id']))


class CountersEvidence:
    """Completion summary only; not a flit/path audit or reconstructable record."""
    mode = 'counters'

    def emit(self, name, *args):
        pass


class CompactEvidence:
    """Raw prefix/tail rows and guarded affine repeats, without online expansion."""
    mode = 'compact'

    def __init__(self):
        self.segments = {name: [] for name in STREAMS}

    def emit(self, name, *args):
        row = event_row(name, args)
        segments = self.segments[name]
        if not segments or segments[-1]['kind'] != 'rows':
            segments.append(dict(kind='rows', rows=[]))
        segments[-1]['rows'].append(row)

    def repeat(self, templates, repetitions, period, flit_stride):
        if set(templates) != set(STREAMS) or repetitions <= 0:
            raise ValueError('Incomplete macro evidence template')
        for name, template in templates.items():
            if not template:
                raise ValueError('Empty macro evidence template')
            self.segments[name].append(dict(kind='repeat', period=period,
                flit_stride=flit_stride, repetitions=repetitions, template=deepcopy(template)))

    def record(self, summary):
        return deepcopy(dict(schema=1, producer=PRODUCER, summary=summary,
                             evidence=self.segments))


def make_evidence(mode):
    if mode == 'full':
        return FullEvidence()
    if mode == 'compact':
        return CompactEvidence()
    if mode == 'counters':
        return CountersEvidence()
    raise ValueError('Invalid causal evidence mode')
