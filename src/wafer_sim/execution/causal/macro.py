"""Guarded period-two single-flow batching on the explicit exact engine.

No AST, exec, tracing, analysis or Native imports. The ordinary service engine
remains the only implementation of injection, ownership, switch and credits.
"""
from collections import deque
from copy import deepcopy
from .evidence import STREAMS, event_row, translated
from .source import SourceRange, LazyPackets
from .state import initialize, ScheduledEvent
from .transition import step_one_cycle, result, completion_summary, compact_record

PERIOD_COUNTS = dict(zip(STREAMS, (9, 3, 4, 3, 6, 1, 1, 1)))
SEQUENCE_STRIDE = 11  # Injection + three sends + three switch/credit pairs + sink credit.


def frozen(value):
    if isinstance(value, dict):
        return tuple((k, frozen(v)) for k, v in sorted(value.items()))
    if isinstance(value, (list, tuple, deque)):
        return tuple(frozen(v) for v in value)
    return value


class RecentEvents:
    """Bounded rule-recognition templates, separate from persistent evidence.

This observer is installed only when compression is enabled. It retains at
most eight cycles of primitive service evidence, not the whole flow history.
"""
    def __init__(self):
        self.rows = {name: deque() for name in STREAMS}

    def emit(self, name, *args):
        row = event_row(name, args)
        now = row['ejected'] if name == 'retired' else row['cycle']
        queue = self.rows[name]
        queue.append((now, row))
        while queue and queue[0][0] < now-8:
            queue.popleft()

    def window(self, start, end):
        return {name: [r for t, r in rows if start <= t < end] for name, rows in self.rows.items()}

    def clear(self):
        for queue in self.rows.values():
            queue.clear()


def active_flits(state):
    live = {f for router in state.routers for queue in router.queues for f in queue}
    live.update(e.payload['flit'] for events in state.events.pending.values()
                for e in events if 'flit' in e.payload)
    return live


def macro_key(state):
    """Bounded causal projection for this rule, not a full validation snapshot."""
    now, anchor = state.now, state.progress[0].injected
    routers = tuple((tuple(tuple(f-anchor for f in q) for q in r.queues), r.owner,
        None if r.sw_ready is None else r.sw_ready-now, r.credit, r.vc_pointer, r.sw_pointer,
        tuple(r.queue_peaks)) for r in state.routers)
    events = []
    for when, rows in sorted(state.events.pending.items()):
        if when < now:
            raise ValueError('Overdue causal event')
        normalized = []
        for event in rows:
            row = dict(event.payload)
            if 'flit' in row:
                row['flit'] -= anchor
            normalized.append((event.sequence-state.events.next_sequence, frozen(row)))
        events.append((when-now, tuple(normalized)))
    metadata = []
    for f in sorted(active_flits(state)):
        row = translated(state.work.data[f], -now, -anchor, 'retired')
        metadata.append((f-anchor, frozen(row)))
    p = state.progress[0]
    return (routers, tuple(s.credit for s in state.sources), tuple(events), tuple(metadata),
        tuple(tuple(s.pending) for s in state.sources), tuple(bool(s.issuing) for s in state.sources),
        state.next_flit, p.generated_at, p.first_inject, p.first_eject,
        None if p.last_inject is None else p.last_inject-now,
        None if p.last_eject is None else p.last_eject-now)


class SingleFlowPeriod2Rule:
    """One concrete rule with explicit recognition, bounds and state update."""
    def __init__(self):
        self.history = {}
        self.batches = []
        self.skipped = 0
        self.authorization = None

    def progress(self, state):
        p = state.progress[0]
        return (p.injected, p.received, tuple(s.stall_cycles for s in state.sources),
            tuple(r.credit_stall_cycles for r in state.routers),
            tuple(state.event_counts[name] for name in STREAMS), state.events.next_sequence)

    def guard(self, state):
        p = state.progress[0]
        return (isinstance(state.work, LazyPackets) and isinstance(state.sources[0].issuing, SourceRange)
            and p.generated_at == state.demand[0]['ready'] and not any(s.pending for s in state.sources)
            and len(state.sources[0].issuing) > 3 and state.demand[0]['flits']-p.received > 3
            and p.injected+len(state.sources[0].issuing) == state.demand[0]['flits']
            and all(r.credit > 0 for r in state.routers)
            and not state.sources[1].issuing and not state.sources[2].issuing
            and all(not q for r, router in enumerate(state.routers) for port, q in enumerate(router.queues)
                    if (r, port) not in ((0, 0), (2, 0), (3, 1)))
            and set(state.work.data) == active_flits(state))

    def recognize(self, state):
        self.authorization = None
        if not self.guard(state):
            return None
        progress = self.progress(state)
        key = macro_key(state)
        prior = self.history.get(state.now % 2)
        current = dict(now=state.now, key=key, progress=progress, confirmations=0, pattern=None)
        self.history[state.now % 2] = current
        if prior is None or prior['now'] != state.now-2 or prior['key'] != key:
            return None
        before = prior['progress']
        delta = (progress[0]-before[0], progress[1]-before[1],
            tuple(b-a for a, b in zip(before[2], progress[2])),
            tuple(b-a for a, b in zip(before[3], progress[3])),
            tuple(b-a for a, b in zip(before[4], progress[4])), progress[5]-before[5])
        if delta != (1, 1, (1, 0, 0), (0, 0, 0, 0), tuple(PERIOD_COUNTS.values()), SEQUENCE_STRIDE):
            return None
        templates = state.observer.window(state.now-2, state.now)
        pattern = []
        for name, rows in templates.items():
            normalized = []
            for row in rows:
                out = translated(row, -(state.now-2), -before[0], name)
                if 'heads' in row:
                    out['heads'] = [v-before[0] if v >= 0 else None for v in row['heads']]
                normalized.append(frozen(out))
            pattern.append((name, tuple(normalized)))
        pattern = tuple(pattern)
        current['pattern'] = pattern
        current['confirmations'] = prior['confirmations']+1 if prior['pattern'] == pattern else 1
        if current['confirmations'] >= 3:
            self.authorization = (state.now, key, progress, frozen(templates))
            return templates
        return None

    def max_safe_repeats(self, state):
        return min(len(state.sources[0].issuing)-1,
            state.demand[0]['flits']-state.progress[0].received-1, (state.cycle_limit-state.now-1)//2)

    def apply(self, state, templates, repeats):
        if (not self.guard(state) or type(repeats) is not int or repeats <= 0
                or repeats > self.max_safe_repeats(state)
                or set(templates) != set(STREAMS)
                or any(len(templates[name]) != PERIOD_COUNTS[name] for name in STREAMS)
                or self.authorization != (state.now, macro_key(state), self.progress(state), frozen(templates))):
            raise ValueError('Unsafe single-flow macro transition')
        start = state.now
        cycles, stride = 2*repeats, repeats
        for router in state.routers:
            router.queues = [deque(f+stride for f in q) for q in router.queues]
            if router.sw_ready is not None:
                router.sw_ready += cycles
        pending = {when+cycles: [ScheduledEvent(e.sequence+SEQUENCE_STRIDE*repeats,
                    dict(e.payload, **({'flit': e.payload['flit']+stride} if 'flit' in e.payload else {})))
                    for e in rows] for when, rows in state.events.pending.items()}
        state.events.pending.clear(); state.events.pending.update(pending)
        state.events.next_sequence += SEQUENCE_STRIDE*repeats
        data = {f: translated(state.work.data[f-stride], cycles, stride, 'retired')
                for f in active_flits(state)}
        state.work.data.clear(); state.work.data.update(data)
        state.sources[0].issuing.skip(stride)
        state.sources[0].stall_cycles += repeats
        p = state.progress[0]
        p.injected += repeats; p.received += repeats
        p.last_inject += cycles; p.last_eject += cycles
        for name in STREAMS:
            state.event_counts[name] += PERIOD_COUNTS[name]*repeats
        state.evidence.repeat(templates, repeats, 2, 1)
        state.now += cycles
        self.skipped += cycles
        self.batches.append(dict(start=start, end=state.now, period=2, repetitions=repeats,
            flit_stride=1, sequence_stride=SEQUENCE_STRIDE,
            source_remaining_after=len(state.sources[0].issuing),
            receiver_remaining_after=state.demand[0]['flits']-p.received, confirmations=3))
        self.history.clear(); state.observer.clear(); self.authorization = None


class MacroExecution:
    def __init__(self, state, rule, updates, checkpoints):
        self.state, self.rule, self.updates, self.checkpoints = state, rule, updates, checkpoints
        self.final_cycle = state.now

    def compact(self):
        return completion_summary(self.state)

    def record(self):
        return compact_record(self.state)

    def metrics(self):
        return deepcopy(dict(physical_cycle_updates=self.updates, logical_cycles=self.state.now,
            skipped_cycles=self.rule.skipped, macros=len(self.rule.batches), batches=self.rule.batches,
            evidence_mode=self.state.evidence.mode, expanded_during_execution=False,
            checkpoints=self.checkpoints, next_event_sequence=self.state.events.next_sequence))


def run(contract, messages, cycle_limit=200000, *, compress=True, evidence='compact', checkpoints=False):
    state = initialize(contract, messages, cycle_limit, evidence=evidence)
    c = state.contract
    if (c['capacity_flits'] != 32 or c['router_link_latency'] != 17 or c['endpoint_link_latency'] != 1
            or c['crossbar_delay'] != 2 or c['flit_bytes'] != 64 or len(messages) != 1
            or messages[0]['source'] != 0 or messages[0]['destination'] != 3):
        raise ValueError('Outside R3 single-flow primary contract')
    if type(compress) is not bool or type(checkpoints) is not bool:
        raise ValueError('Invalid macro execution options')
    state.sources[0].issuing = SourceRange()
    state.work = LazyPackets()
    rule = SingleFlowPeriod2Rule()
    if compress:
        state.observer = RecentEvents()
    updates, checks = 0, []
    while not state.complete:
        templates = rule.recognize(state) if compress else None
        if templates is not None and rule.max_safe_repeats(state) > 0:
            if checkpoints:
                checks.append(dict(role='entry', state=state.snapshot().to_record(),
                                   progress=state.progress_snapshot().to_record()))
            rule.apply(state, templates, rule.max_safe_repeats(state))
            if checkpoints:
                checks.append(dict(role='exit', state=state.snapshot().to_record(),
                                   progress=state.progress_snapshot().to_record()))
        step_one_cycle(state); updates += 1
    if updates+rule.skipped != state.now:
        raise ValueError('Physical/logical progress mismatch')
    return MacroExecution(state, rule, updates, checks)
