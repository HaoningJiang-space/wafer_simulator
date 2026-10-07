"""Independent message-service arithmetic; no timings fitted from native runs."""
from collections import Counter
from math import ceil
from fractions import Fraction


def isolated_comparison(target, message):
    source, destination, size = message['source'], message['destination'], message['bytes']
    if (size <= 0 or not message['flits'] or len(message['flits']) != message['expected_flits']
            or message['expected_flits'] != (size+message['flit_bytes']-1)//message['flit_bytes']):
        raise ValueError('Incomplete or inconsistent isolated transfer')
    coarse_path = tuple(target.route(source, destination))
    paths = Counter(tuple(f['router_path']) for f in message['flits'])
    def cost(path):
        services = [target.endpoints[source].injection,
                    *(target.links[a,b] for a,b in zip(path,path[1:])),target.endpoints[destination].ejection]
        return dict(serialization_cycles=sum(ceil(Fraction(size*s.rate_denominator,s.rate_numerator)) for s in services),
                    latency_cycles=sum(s.latency_cycles for s in services))
    parts = cost(coarse_path)
    predicted = sum(parts.values())
    actual = message['finish']-message['ready']
    if actual <= 0: raise ValueError('Nonpositive reference service')
    return dict(source=source,destination=destination,bytes=size,flits=message['expected_flits'],
        reference_cycles=actual,coarse_cycles=predicted,error_cycles=predicted-actual,
        absolute_percentage_error=100*abs(predicted/actual-1),
        matched_path=all(path==coarse_path for path in paths),coarse_path=coarse_path,**parts,
        native_paths=[dict(path=p,count=n,coarse_cost_on_observed_path=cost(p)) for p,n in sorted(paths.items())],
        injection_span_cycles=message['last_inject']-message['first_inject'],
        first_injection_wait_cycles=message['first_inject']-message['ready'],
        ejection_span_cycles=message['last_eject']-message['first_eject'])


def summarize_isolated(rows, tolerance):
    matched = [r for r in rows if r['matched_path']]
    return dict(total=len(rows),matched_paths=len(matched),route_mismatches=len(rows)-len(matched),
        max_matched_ape_percent=max((r['absolute_percentage_error'] for r in matched),default=None),
        meets_service_target=all(r['absolute_percentage_error']<=tolerance for r in matched) if matched else None,
        tolerance_percent=tolerance)
