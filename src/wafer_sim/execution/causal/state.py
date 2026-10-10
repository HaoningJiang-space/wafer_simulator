"""Mutable causal state, ordered channel events and immutable boundary snapshots.

No analysis, Native, experiments, tracing or filesystem dependencies. Full
evidence remains the sole R1 format; evidence sinks are a later migration.
"""
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
import heapq
from wafer_sim.architecture.causal_merge import PORTS, validate


@dataclass(frozen=True)
class FrozenMap:
    items: tuple


def freeze(value):
    if isinstance(value, dict):
        return FrozenMap(tuple((k, freeze(v)) for k, v in sorted(value.items())))
    if isinstance(value, (list, tuple, deque)):
        return tuple(freeze(v) for v in value)
    return value


def thaw(value):
    if isinstance(value, FrozenMap):
        return {k: thaw(v) for k, v in value.items}
    if isinstance(value, tuple):
        return [thaw(v) for v in value]
    return value


def issuing_work(queue, work):
    """Losslessly group contiguous IDs with identical uninjected metadata.

    Check every queued record. A changed message/source/epoch/field forms a new
    segment rather than being inferred from the head or hidden until injection.
    Segmentation reduces snapshot copies only; source execution remains a deque.
    """
    segments = []
    baseline = None
    expected = None
    for flit in queue:
        row = work[flit]
        if expected is not None:
            expected['id'] = flit+segments[-1][2]
        if expected is not None and row == expected and flit == segments[-1][1]:
            segments[-1][1] += 1
        else:
            baseline = dict(row)
            packet_id = baseline.pop('id')
            segments.append([flit, flit+1, packet_id-flit, baseline])
            expected = dict(row)
    return segments


@dataclass(frozen=True)
class CausalSnapshot:
    """Detached read-only logical state; to_record returns a detached JSON tree."""
    payload: FrozenMap

    def to_record(self):
        return thaw(self.payload)


@dataclass
class SourceState:
    credit: int
    issuing: deque = field(default_factory=deque)
    pending: list = field(default_factory=list)  # Exact (ready, message) heap order.
    stall_cycles: int = 0


@dataclass
class RouterState:
    queues: list
    credit: int
    queue_peaks: list
    owner: int | None = None
    sw_ready: int | None = None
    vc_pointer: int = 0
    sw_pointer: int = 0
    credit_stall_cycles: int = 0


@dataclass(frozen=True)
class ScheduledEvent:
    sequence: int
    payload: dict


class EventQueue:
    """Clock first, insertion sequence second; never sort by event kind.

    G1 consumes all events for a boundary before performing allocation. Its
    positive channel delays prevent scheduling an event into the consumed clock.
    """
    def __init__(self):
        self.pending = defaultdict(list)
        self.next_sequence = 0

    def schedule(self, when, kind, **row):
        event = ScheduledEvent(self.next_sequence, dict(kind=kind, **row))
        self.next_sequence += 1
        self.pending[when].append(event)

    def pop(self, now):
        return self.pending.pop(now, [])

    def __bool__(self):
        return bool(self.pending)

    def snapshot(self):
        return [[when, [[e.sequence, e.payload] for e in events]]
                for when, events in sorted(self.pending.items())]


@dataclass
class FullEvidence:
    injections: dict = field(default_factory=lambda: defaultdict(list))
    ejections: dict = field(default_factory=lambda: defaultdict(list))
    service: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    credits: list = field(default_factory=list)
    credit_sends: list = field(default_factory=list)
    allocations: list = field(default_factory=list)


@dataclass
class CausalState:
    contract: dict
    demand: list
    cycle_limit: int
    sources: list
    routers: list
    events: EventQueue = field(default_factory=EventQueue)
    generated: dict = field(default_factory=dict)
    work: dict = field(default_factory=dict)
    evidence: FullEvidence = field(default_factory=FullEvidence)
    now: int = 0  # The next boundary to consume; step advances exactly one.
    next_flit: int = 0
    complete: bool = False

    def snapshot(self, include_history=False):
        """Exact future-affecting state and progress, without copying retired logs.

        Issuing IDs are retained in full, not coalesced. Live packet metadata
        includes path/timing evidence needed for eventual records. Uninjected
        metadata is represented losslessly by checked homogeneous ID segments;
        retired records are history, independently compared in the full result.
        include_history=True additionally copies all work and evidence. Neither
        snapshot form participates in execution decisions.
        """
        live = {f for r in self.routers for q in r.queues for f in q}
        live.update(e.payload['flit'] for events in self.events.pending.values()
                    for e in events if 'flit' in e.payload)
        log = self.evidence
        record = dict(schema=1, cycle=self.now, complete=self.complete,
            cycle_limit=self.cycle_limit, contract=self.contract, demand=self.demand,
            sources=[dict(credit=s.credit, issuing=list(s.issuing),
                          issuing_work=issuing_work(s.issuing, self.work), pending=s.pending,
                          stall_cycles=s.stall_cycles) for s in self.sources],
            routers=[dict(queues=[list(q) for q in r.queues], owner=r.owner,
                sw_ready=r.sw_ready, credit=r.credit, vc_pointer=r.vc_pointer,
                sw_pointer=r.sw_pointer, credit_stall_cycles=r.credit_stall_cycles,
                queue_peaks=r.queue_peaks) for r in self.routers],
            events=self.events.snapshot(), next_event_sequence=self.events.next_sequence,
            generated=self.generated, next_flit=self.next_flit,
            live_work=[[f, self.work[f]] for f in sorted(live)],
            remaining=[[m['flits']-len(log.injections.get(m['id'], ())),
                        m['flits']-len(log.ejections.get(m['id'], ()))] for m in self.demand],
            message_progress=[dict(injected=len(log.injections.get(m['id'], ())),
                ejected=len(log.ejections.get(m['id'], ()))) for m in self.demand],
            evidence_counts={name: len(getattr(log, name)) for name in
                             ('service', 'inputs', 'credits', 'credit_sends', 'allocations')})
        if include_history:
            record['all_work'] = [[f, w] for f, w in sorted(self.work.items())]
            record['full_evidence'] = {name: getattr(log, name) for name in vars(log)}
        return CausalSnapshot(freeze(record))


def initialize(contract, messages, cycle_limit=200000):
    c = validate(contract)
    if type(cycle_limit) is not int or cycle_limit <= 0:
        raise ValueError('Invalid cycle limit')
    if not messages:
        raise ValueError('No external demand')
    demand = []
    for mid, message in enumerate(messages):
        if (set(message) != {'source', 'destination', 'flits', 'ready'} or
                any(type(message[k]) is not int for k in message) or
                not 0 <= message['source'] < 3 or message['destination'] != 3 or
                message['flits'] <= 0 or message['ready'] < 0):
            raise ValueError('Invalid external demand')
        demand.append(dict(message, id=mid))
    sources = [SourceState(c['capacity_flits']) for _ in range(3)]
    for m in demand:
        heapq.heappush(sources[m['source']].pending, (m['ready'], m['id']))
    routers = [RouterState([deque() for _ in ports], c['capacity_flits'], [0]*len(ports))
               for ports in PORTS]
    return CausalState(deepcopy(c), demand, cycle_limit, sources, routers)
