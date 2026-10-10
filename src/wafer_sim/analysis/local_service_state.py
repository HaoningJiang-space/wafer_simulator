"""One-output causal state replay, with observed external arrivals and credits.

Eligibility, head order, VC ownership, pointers and local pipeline boundaries
are computed here. This is not independent prediction of the surrounding fabric.
"""
from collections import defaultdict, deque
import heapq


def reconstruct_state(arrivals, credits, contract):
    if (contract['routing_delay'] != 0 or contract['vc_alloc_delay'] != 1 or
            contract['sw_alloc_delay'] != 1 or contract['vc_busy_when_full'] or
            contract['output_buffer_limit'] != -1):
        raise ValueError('Unsupported local state contract')
    n = contract['input_count']; capacity = contract['downstream_capacity']
    if n <= 0 or capacity <= 0 or contract['crossbar_delay'] <= 0 or contract['channel_latency'] <= 0:
        raise ValueError('Invalid local capacities or delays')
    jobs = defaultdict(list); returns = defaultdict(int)
    identities = set()
    for row in arrivals:
        if row['flit'] in identities or not 0 <= row['input'] < n or row['cycle'] < 0:
            raise ValueError('Invalid or repeated local arrival')
        identities.add(row['flit']); jobs[row['cycle']].append(dict(row))
    for row in credits:
        if row['amount'] <= 0 or row['cycle'] < 0:
            raise ValueError('Invalid supplied credit return')
        returns[row['cycle']] += row['amount']
    external = sorted(set(jobs) | set(returns)); external_index = 0
    queues = {i: deque() for i in range(n)}
    owner = None; sw_ready = None; free = capacity; vc_pointer = sw_pointer = 0
    sends = []; rows = []; intervals = []; steps = 0; skipped = 0
    now = external[0] if external else 0
    while external_index < len(external) or any(queues.values()) or sends:
        steps += 1
        for row in sorted(jobs.get(now, []), key=lambda r: (r['input'], r['flit'])):
            queues[row['input']].append(row)
        free += returns.get(now, 0)
        if not 0 <= free <= capacity:
            raise ValueError('Supplied credits violate local occupancy')
        while external_index < len(external) and external[external_index] <= now:
            external_index += 1
        while sends and sends[0][0] == now:
            _, _, row = heapq.heappop(sends)
            rows.append(dict(row, output_send=now,
                             output_sink_arrival=now+contract['channel_latency']+1))
        vc_pending = [i for i in range(n) if queues[i] and i != owner]
        vc_requests = vc_pending if owner is None else []
        sw_requests = [owner] if owner is not None and sw_ready <= now and free > 0 else []
        vc_grant = min(vc_requests, key=lambda i: (i-vc_pointer) % n) if vc_requests else -1
        sw_grant = sw_requests[0] if sw_requests else -1
        before_vc, before_sw = vc_pointer, sw_pointer
        if vc_grant >= 0:
            vc_pointer = (vc_grant+1) % n
        if sw_grant >= 0:
            sw_pointer = (sw_grant+1) % n
        point = dict(cycle=now, vc_requests=vc_requests, sw_requests=sw_requests,
            vc_pointer_before=before_vc, sw_pointer_before=before_sw,
            vc_grant=vc_grant, sw_grant=sw_grant,
            vc_pointer_after=vc_pointer, sw_pointer_after=sw_pointer,
            free_before_sw=free)
        if sw_grant >= 0:
            row = queues[owner].popleft(); row['sw_commit'] = now
            free -= 1; owner = None; sw_ready = None
            heapq.heappush(sends, (now+contract['crossbar_delay'], row['flit'], row))
        if vc_grant >= 0:
            owner = vc_grant; sw_ready = now+1
            queues[owner][0]['vc_commit'] = now
        future = []
        if external_index < len(external): future.append(external[external_index])
        if sends: future.append(sends[0][0])
        if owner is not None and sw_ready > now: future.append(sw_ready)
        elif owner is not None and free > 0: future.append(now+1)
        if owner is None and any(queues.values()): future.append(now+1)
        if not future:
            if any(queues.values()): raise ValueError('Local state blocked without supplied credit')
            intervals.append(dict(**point, next_cycle=now+1)); break
        next_time = min(future)
        if next_time <= now: raise ValueError('Non-progressing local state replay')
        intervals.append(dict(**point, next_cycle=next_time))
        skipped += max(0, next_time-now-1)
        now = next_time
    if len(rows) != len(arrivals) or free != capacity:
        raise ValueError('Incomplete local data or credit drainage')
    return dict(boundaries=sorted(rows, key=lambda r: r['flit']), intervals=intervals,
        processed_event_times=steps, skipped_empty_or_blocked_cycles=skipped,
        scope='Observed arrivals/credit returns; internally reconstructed eligibility and local service')


def compare_state(records, boundaries, reconstructed):
    native = {r['flit']: r for r in boundaries}
    predictions = {r['flit']: r for r in reconstructed['boundaries']}
    if set(native) != set(predictions): raise ValueError('Different local state demand')
    fields = ('vc_commit', 'sw_commit', 'output_send', 'output_sink_arrival')
    errors = [dict(flit=f, field=k, actual=native[f][k], predicted=predictions[f][k])
              for f in native for k in fields if native[f][k] != predictions[f][k]]
    points = {r['cycle']: r for r in reconstructed['intervals']}
    intervals = reconstructed['intervals']; index = 0; checks = []; stages = ('vc', 'sw')
    for row in (r for r in records if r['kind'] == 'allocate_pre'):
        stage = row['stage']; t = row['cycle']
        if stage not in stages: raise ValueError('Unknown observed stage')
        while index+1 < len(intervals) and intervals[index+1]['cycle'] <= t: index += 1
        point = points.get(t)
        if point is None:
            previous = intervals[index]
            if not previous['cycle'] < t < previous['next_cycle']:
                raise ValueError('Uncovered allocation clock')
            # A skipped interval has no service opportunity. Its pointers hold.
            requests = []; pointer = previous[stage+'_pointer_after']
        else:
            requests = point[stage+'_requests']; pointer = point[stage+'_pointer_before']
        actual = [r['input'] for r in row['inputs'] if r['requested']]
        checks.append(dict(cycle=t, stage=stage, requests_match=actual == requests,
                           pointer_matches=row['grant_pointer'] == pointer))
    return dict(boundary_mismatches=len(errors), boundary_errors=errors,
        eligibility_mismatches=sum(not r['requests_match'] for r in checks),
        pointer_mismatches=sum(not r['pointer_matches'] for r in checks),
        allocation_calls_checked=len(checks), processed_event_times=reconstructed['processed_event_times'],
        skipped_empty_or_blocked_cycles=reconstructed['skipped_empty_or_blocked_cycles'],
        eligibility_from_native=False, upstream_arrivals_from_native=True, credit_returns_from_native=True,
        scope='Conditional local reconstruction, not an independent network backend')
