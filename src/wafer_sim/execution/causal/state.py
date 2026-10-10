"""Mutable causal state, ordered channel events and immutable boundary snapshots.

No analysis, Native, experiments, tracing or filesystem dependencies. Message
progress and event counts are semantic/diagnostic state independent of sinks.
"""
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass, field
import heapq
from wafer_sim.architecture.causal_merge import PORTS, validate
from .evidence import FullEvidence, STREAMS, make_evidence


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
        row = work.peek(flit) if hasattr(work, 'peek') else work[flit]
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
class MessageProgress:
    """Per-message semantic counters/times; no event-list dependency."""
    generated_at: int | None = None
    injected: int = 0
    received: int = 0
    first_inject: int | None = None
    last_inject: int | None = None
    first_eject: int | None = None
    last_eject: int | None = None

    def inject(self, now):
        self.injected += 1
        if self.first_inject is None:
            self.first_inject = now
        self.last_inject = now

    def receive(self, now):
        self.received += 1
        if self.first_eject is None:
            self.first_eject = now
        self.last_eject = now

    def record(self):
        return dict(generated_at=self.generated_at, injected=self.injected,
            received=self.received, first_inject=self.first_inject,
            last_inject=self.last_inject, first_eject=self.first_eject,
            last_eject=self.last_eject)


@dataclass
class CausalState:
    contract: dict
    demand: list
    cycle_limit: int
    sources: list
    routers: list
    progress: list
    events: EventQueue = field(default_factory=EventQueue)
    work: dict = field(default_factory=dict)
    evidence: FullEvidence = field(default_factory=FullEvidence)
    event_counts: dict = field(default_factory=lambda: dict.fromkeys(STREAMS, 0))
    observer: object = None  # Optional bounded macro observer, never read by step.
    now: int = 0  # The next boundary to consume; step advances exactly one.
    next_flit: int = 0
    complete: bool = False

    def emit(self, name, *args):
        self.event_counts[name] += 1
        self.evidence.emit(name, *args)
        if self.observer is not None:
            self.observer.emit(name, *args)

    def generate_message(self, source, message, now):
        """Storage-specific label creation; eligibility/order is decided by step."""
        queue = self.sources[source].issuing
        if hasattr(self.work, 'register'):
            self.work.register(message, self.next_flit, now)
            queue.reset(self.next_flit, message['flits'])
            self.next_flit += message['flits']
        else:
            for _ in range(message['flits']):
                f = self.next_flit
                self.next_flit += 1
                queue.append(f)
                self.work[f] = dict(id=f, message=message['id'], source=source, destination=3,
                    generated=now, router_path=[], link_arrivals=[])

    def retire_metadata(self, flit):
        if hasattr(self.work, 'retire'):
            self.work.retire(flit)

    @property
    def generated(self):
        """Detached legacy-compatible view, derived from semantic generation."""
        return {mid: p.generated_at for mid, p in enumerate(self.progress)
                if p.generated_at is not None}

    def progress_snapshot(self):
        """Detached semantic progress, including times absent from R1 schema 1."""
        return CausalSnapshot(freeze(dict(schema=1,
            messages=[p.record() for p in self.progress])))

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
            remaining=[[m['flits']-self.progress[m['id']].injected,
                        m['flits']-self.progress[m['id']].received] for m in self.demand],
            message_progress=[dict(injected=p.injected, ejected=p.received) for p in self.progress],
            evidence_counts={name: self.event_counts[name] for name in
                             ('service', 'inputs', 'credits', 'credit_sends', 'allocations')})
        if include_history:
            if self.evidence.mode != 'full':
                raise ValueError('Full history requires Full evidence')
            record['all_work'] = [[f, w] for f, w in sorted(self.work.items())]
            record['full_evidence'] = {name: getattr(self.evidence, name) for name in
                ('injections', 'ejections', 'service', 'inputs', 'credits', 'credit_sends', 'allocations')}
        return CausalSnapshot(freeze(record))


def initialize(contract, messages, cycle_limit=200000, *, evidence='full'):
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
    return CausalState(deepcopy(c), demand, cycle_limit, sources, routers,
                       [MessageProgress() for _ in demand], evidence=make_evidence(evidence))
