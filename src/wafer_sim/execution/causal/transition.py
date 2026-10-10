"""Exact ordinary one-cycle transition for the declared bounded G1 contract.

No AST rewriting, dynamic compilation, macro recognition or analysis imports.
Order is inherited from the unchanged legacy reference, not redefined here.
"""
from copy import deepcopy
import heapq
from wafer_sim.architecture.causal_merge import PORTS, FORWARD, ENDPOINT_ROUTERS
from .state import initialize


def _upstream_credit(state, router, port):
    kind, number = PORTS[router][port].split('/')
    delay = state.contract['router_link_latency'] if kind == 'router' else state.contract['endpoint_link_latency']
    state.emit('credit_sends', router, port, state.now, 1)
    state.events.schedule(state.now+delay+1, 'credit', target=kind, number=int(number))


def step_one_cycle(state):
    """Consume boundary now, evaluate/update in G1 order, advance to now+1.

    A completed state cannot advance. Reaching the deadline without a full
    drain is incomplete, even if every destination message already arrived.
    """
    if state.complete:
        raise ValueError('Cannot advance completed causal state')
    if state.now >= state.cycle_limit:
        raise TimeoutError('Incomplete causal merge execution')
    now = state.now
    c = state.contract
    capacity = c['capacity_flits']
    edge, link = c['endpoint_link_latency'], c['router_link_latency']

    # ReadInputs and endpoint consumption precede generation and allocation.
    for scheduled in state.events.pop(now):
        event = scheduled.payload
        kind = event['kind']
        if kind == 'arrival':
            r, p, f = event['router'], event['input'], event['flit']
            router = state.routers[r]
            router.queues[p].append(f)
            state.work[f]['router_path'].append(r)
            state.emit('inputs', r, p, f, now)
            if len(router.queues[p]) > capacity:
                raise ValueError('Input capacity exceeded')
            router.queue_peaks[p] = max(router.queue_peaks[p], len(router.queues[p]))
            if len(state.work[f]['router_path']) == 1:
                state.work[f]['injection_router_arrival'] = now
            else:
                state.work[f]['link_arrivals'].append(dict(source=event['upstream'], destination=r, cycle=now, vc=0))
        elif kind == 'credit':
            number = event['number']
            if event['target'] == 'endpoint':
                state.sources[number].credit += 1
                value = state.sources[number].credit
            else:
                state.routers[number].credit += 1
                value = state.routers[number].credit
            if not 0 <= value <= capacity:
                raise ValueError('Credit capacity exceeded')
            state.emit('credits', event['target'], number, now, 1)
        elif kind == 'sink':
            f = event['flit']
            state.progress[state.work[f]['message']].receive(now)
            state.work[f]['ejected'] = now
            state.emit('ejections', state.work[f]['message'], now)
            state.emit('retired', state.work[f])
            state.retire_metadata(f)
            state.events.schedule(now+edge+1, 'credit', target='router', number=3)
        elif kind == 'send':
            r, f = event['router'], event['flit']
            state.emit('service', 'output_send', r, f, now, None)
            out_kind, number = PORTS[r][FORWARD[r]].split('/')
            number = int(number)
            if out_kind == 'router':
                port = PORTS[number].index(f'router/{r}')
                state.events.schedule(now+link+1, 'arrival', router=number, input=port, upstream=r, flit=f)
            else:
                state.events.schedule(now+edge+1, 'sink', flit=f)
        else:
            raise ValueError('Unknown internal event')

    # A source generates the next entire message only when its issuing queue empties.
    for source, sending in enumerate(state.sources):
        if not sending.issuing and sending.pending and sending.pending[0][0] <= now:
            _, mid = heapq.heappop(sending.pending)
            message = state.demand[mid]
            state.progress[mid].generated_at = now
            state.generate_message(source, message, now)
        if sending.issuing and sending.credit:
            f = sending.issuing.popleft()
            sending.credit -= 1
            state.work[f]['injected'] = now
            state.progress[state.work[f]['message']].inject(now)
            state.emit('injections', state.work[f]['message'], now)
            router = ENDPOINT_ROUTERS[source]
            port = PORTS[router].index(f'endpoint/{source}')
            state.events.schedule(now+edge+1, 'arrival', router=router, input=port, flit=f)
        elif sending.issuing:
            sending.stall_cycles += 1

    # Evaluate uses pre-update ownership. Switch release does not enable a VC
    # request earlier in the same cycle. Preserve router iteration order as well.
    for r, router in enumerate(state.routers):
        queues, owner = router.queues, router.owner
        pending = [p for p, q in enumerate(queues) if q and p != owner]
        vc_requests = pending if owner is None else []
        sw_requests = [owner] if owner is not None and router.sw_ready <= now and router.credit else []
        vg = min(vc_requests, key=lambda p: (p-router.vc_pointer) % len(queues)) if vc_requests else -1
        sg = sw_requests[0] if sw_requests else -1
        if pending or owner is not None:
            state.emit('allocations', r, now, vc_requests, sw_requests,
                router.vc_pointer, router.sw_pointer, owner, router.credit, queues)
        if owner is not None and router.sw_ready <= now and not router.credit:
            router.credit_stall_cycles += 1
        if vg >= 0:
            f = queues[vg][0]
            router.vc_pointer = (vg+1) % len(queues)
            state.emit('service', 'vc_commit', r, f, now, vg)
        if sg >= 0:
            f = queues[sg].popleft()
            router.sw_pointer = (sg+1) % len(queues)
            router.credit -= 1
            router.owner = None
            router.sw_ready = None
            state.emit('service', 'sw_commit', r, f, now, sg)
            _upstream_credit(state, r, sg)
            state.events.schedule(now+c['crossbar_delay'], 'send', router=r, flit=f)
        if vg >= 0:
            router.owner = vg
            router.sw_ready = now+1

    state.now = now+1
    state.complete = (all(state.progress[m['id']].received == m['flits'] for m in state.demand)
        and not state.events and all(not s.issuing and not s.pending for s in state.sources)
        and all(r.owner is None and not any(r.queues) and r.credit == capacity for r in state.routers)
        and all(s.credit == capacity for s in state.sources))
    return state


def completion_summary(state):
    """Detached semantic completion/counter projection, independent of recording."""
    if not state.complete:
        raise ValueError('Incomplete causal state cannot produce a complete result')
    messages = []
    for m in state.demand:
        mid = m['id']
        progress = state.progress[mid]
        messages.append(dict(id=mid, source=m['source'], destination=3, ready=m['ready'],
            generated=progress.generated_at, first_inject=progress.first_inject,
            last_inject=progress.last_inject, first_eject=progress.first_eject,
            last_eject=progress.last_eject, finish=progress.last_eject+1, flits=m['flits']))
    return deepcopy(dict(complete=True, drained=True, final_cycle=state.now,
        messages=messages, event_counts=state.event_counts,
        source_stall_cycles=[s.stall_cycles for s in state.sources],
        router_credit_stall_cycles=[r.credit_stall_cycles for r in state.routers],
        queue_peaks=[r.queue_peaks for r in state.routers], native_boundary_inputs=False))


def compact_record(state):
    if state.evidence.mode != 'compact':
        raise ValueError('Reconstructable evidence requires Compact mode')
    return state.evidence.record(completion_summary(state))


def result(state):
    """Full remains legacy-compatible; other modes explicitly provide a summary."""
    summary = completion_summary(state)
    log = state.evidence
    if log.mode != 'full':
        return dict(summary, evidence_mode=log.mode, full_flit_audit=False)
    messages = [dict(m, flits=log.flits(m['id'])) for m in summary['messages']]
    return deepcopy(dict(complete=True, drained=True, final_cycle=state.now,
        messages=messages, service=log.service, input_arrivals=log.inputs,
        credit_returns=log.credits, credit_sends=log.credit_sends, allocations=log.allocations,
        source_stall_cycles=[s.stall_cycles for s in state.sources],
        router_credit_stall_cycles=[r.credit_stall_cycles for r in state.routers],
        queue_peaks=[r.queue_peaks for r in state.routers], native_boundary_inputs=False,
        processed_cycles=state.now,
        scope='Independent bounded four-router G1 prediction; no service compression'))


def run(contract, messages, cycle_limit=200000, *, evidence='full'):
    state = initialize(contract, messages, cycle_limit, evidence=evidence)
    while not state.complete:
        step_one_cycle(state)
    return result(state)
