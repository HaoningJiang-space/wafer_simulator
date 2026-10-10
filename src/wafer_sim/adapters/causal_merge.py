"""Independent bounded G1 component solver; no Native events are model inputs.

Single-flit packets, one forward output per router, private single-VC buffers.
This cycle-level composition establishes closure; it is not a compressed backend.
"""
from collections import defaultdict, deque
import heapq
from wafer_sim.architecture.causal_merge import validate, PORTS, FORWARD, ENDPOINT_ROUTERS


def simulate(contract, messages, cycle_limit=200000):
    c = validate(contract)
    if type(cycle_limit) is not int or cycle_limit <= 0: raise ValueError('Invalid cycle limit')
    if not messages: raise ValueError('No external demand')
    demand = []
    for mid, m in enumerate(messages):
        if (set(m) != {'source', 'destination', 'flits', 'ready'} or
                any(type(m[k]) is not int for k in m) or
                not 0 <= m['source'] < 3 or m['destination'] != 3 or
                m['flits'] <= 0 or m['ready'] < 0):
            raise ValueError('Invalid external demand')
        demand.append(dict(m, id=mid))
    capacity = c['capacity_flits']; edge = c['endpoint_link_latency']; link = c['router_link_latency']
    states = [dict(queues=[deque() for _ in peers], owner=None, sw_ready=None,
                  credit=capacity, vc_pointer=0, sw_pointer=0) for peers in PORTS]
    issuing = [deque() for _ in range(3)]; source_credits = [capacity]*3
    todo = [[] for _ in range(3)]
    for m in demand: heapq.heappush(todo[m['source']], (m['ready'], m['id']))
    generated = {}; injections = defaultdict(list); ejections = defaultdict(list)
    work = {}; service = []; inputs = []; credits = []; credit_sends = []; allocations = []
    future = defaultdict(list); next_flit = 0; source_stalls = [0]*3; router_stalls = [0]*4
    queue_peaks = [[0]*len(peers) for peers in PORTS]
    def schedule(when, kind, **row):
        future[when].append(dict(kind=kind, **row))
    def upstream_credit(router, port, now):
        identity = PORTS[router][port]; kind, number = identity.split('/'); number = int(number)
        delay = link if kind == 'router' else edge
        credit_sends.append(dict(router=router, input=port, cycle=now, amount=1))
        schedule(now+delay+1, 'credit', target=kind, number=number)
    final_cycle = None
    for now in range(cycle_limit):
        # ReadInputs/endpoint consumption. Arrivals from previous channel writes
        # and credit processing precede allocation. No newly sent flit can be
        # consumed by another router in this same cycle.
        for event in future.pop(now, []):
            kind = event['kind']
            if kind == 'arrival':
                r, p, f = event['router'], event['input'], event['flit']
                states[r]['queues'][p].append(f); work[f]['router_path'].append(r)
                inputs.append(dict(router=r, input=p, flit=f, cycle=now))
                if len(states[r]['queues'][p]) > capacity: raise ValueError('Input capacity exceeded')
                queue_peaks[r][p] = max(queue_peaks[r][p], len(states[r]['queues'][p]))
                if len(work[f]['router_path']) == 1: work[f]['injection_router_arrival'] = now
                else: work[f]['link_arrivals'].append(dict(source=event['upstream'], destination=r, cycle=now, vc=0))
            elif kind == 'credit':
                number = event['number']
                if event['target'] == 'endpoint':
                    source_credits[number] += 1; value = source_credits[number]
                else:
                    states[number]['credit'] += 1; value = states[number]['credit']
                if not 0 <= value <= capacity: raise ValueError('Credit capacity exceeded')
                credits.append(dict(target=event['target'], number=number, cycle=now, amount=1))
            elif kind == 'sink':
                f = event['flit']; work[f]['ejected'] = now
                ejections[work[f]['message']].append(now)
                schedule(now+edge+1, 'credit', target='router', number=3)
            elif kind == 'send':
                r, f = event['router'], event['flit']
                service.append(dict(kind='output_send', router=r, flit=f, cycle=now))
                out = PORTS[r][FORWARD[r]]; out_kind, number = out.split('/'); number = int(number)
                if out_kind == 'router':
                    port = PORTS[number].index(f'router/{r}')
                    schedule(now+link+1, 'arrival', router=number, input=port, upstream=r, flit=f)
                else: schedule(now+edge+1, 'sink', flit=f)
            else: raise ValueError('Unknown internal event')
        # TrafficManager generates the complete current message when its source
        # queue is empty, independent of destination completion.
        for source in range(3):
            if not issuing[source] and todo[source] and todo[source][0][0] <= now:
                _, mid = heapq.heappop(todo[source]); m = demand[mid]; generated[mid] = now
                for _ in range(m['flits']):
                    f = next_flit; next_flit += 1; issuing[source].append(f)
                    work[f] = dict(id=f, message=mid, source=source, destination=3, generated=now,
                                   router_path=[], link_arrivals=[])
            if issuing[source] and source_credits[source]:
                f = issuing[source].popleft(); source_credits[source] -= 1
                work[f]['injected'] = now; injections[work[f]['message']].append(now)
                router = ENDPOINT_ROUTERS[source]; port = PORTS[router].index(f'endpoint/{source}')
                schedule(now+edge+1, 'arrival', router=router, input=port, flit=f)
            elif issuing[source]: source_stalls[source] += 1
        # All Evaluate decisions use pre-update ownership, eligibility and
        # pointers. In particular an owner sending now does not free its VC
        # for allocation earlier in this same cycle.
        for r, state in enumerate(states):
            queues = state['queues']; owner = state['owner']
            pending = [p for p, q in enumerate(queues) if q and p != owner]
            vc_requests = pending if owner is None else []
            sw_requests = [owner] if owner is not None and state['sw_ready'] <= now and state['credit'] else []
            vg = min(vc_requests, key=lambda p: (p-state['vc_pointer']) % len(queues)) if vc_requests else -1
            sg = sw_requests[0] if sw_requests else -1
            if pending or owner is not None:
                allocations.append(dict(router=r, cycle=now, vc_requests=vc_requests, sw_requests=sw_requests,
                    vc_pointer=state['vc_pointer'], sw_pointer=state['sw_pointer'], owner=owner,
                    credit_slots=state['credit'], occupancy=[len(q) for q in queues], heads=[q[0] if q else -1 for q in queues]))
            if owner is not None and state['sw_ready'] <= now and not state['credit']: router_stalls[r] += 1
            if vg >= 0:
                f = queues[vg][0]; state['vc_pointer'] = (vg+1) % len(queues)
                service.append(dict(kind='vc_commit', router=r, input=vg, flit=f, cycle=now))
            if sg >= 0:
                f = queues[sg].popleft(); state['sw_pointer'] = (sg+1) % len(queues)
                state['credit'] -= 1; state['owner'] = None; state['sw_ready'] = None
                service.append(dict(kind='sw_commit', router=r, input=sg, flit=f, cycle=now))
                upstream_credit(r, sg, now)
                schedule(now+c['crossbar_delay'], 'send', router=r, flit=f)
            if vg >= 0: state['owner'] = vg; state['sw_ready'] = now+1
        if (all(len(ejections[m['id']]) == m['flits'] for m in demand) and not future and
                all(not q for q in issuing) and all(not q for q in todo) and
                all(s['owner'] is None and not any(s['queues']) and s['credit'] == capacity for s in states) and
                source_credits == [capacity]*3):
            final_cycle = now+1; break
    if final_cycle is None: raise TimeoutError('Incomplete causal merge execution')
    results = []
    for m in demand:
        mid=m['id']; flits=sorted((dict(f, hops=len(f['router_path'])) for f in work.values() if f['message']==mid),key=lambda f:(f['ejected'],f['id']))
        results.append(dict(id=mid,source=m['source'],destination=3,ready=m['ready'],generated=generated[mid],
            first_inject=min(injections[mid]),last_inject=max(injections[mid]),first_eject=min(ejections[mid]),
            last_eject=max(ejections[mid]),finish=max(ejections[mid])+1,flits=flits))
    return dict(complete=True, drained=True, final_cycle=final_cycle, messages=results, service=service,
        input_arrivals=inputs, credit_returns=credits, credit_sends=credit_sends, allocations=allocations,
        source_stall_cycles=source_stalls, router_credit_stall_cycles=router_stalls, queue_peaks=queue_peaks,
        native_boundary_inputs=False, processed_cycles=final_cycle,
        scope='Independent bounded four-router G1 prediction; no service compression')
