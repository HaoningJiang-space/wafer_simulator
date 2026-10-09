"""Independent D0 message and unchanged-resource completion audit."""
from wafer_sim.analysis.memory_abstraction import audit_projection
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.io import object_digest


def audit_network(network, result):
    spec = result['independent_spatial_contract']
    if spec['model'] != 'D0': raise ValueError('Unexpected D0 contract')
    raw = result['native_network_messages']; audit_messages(network, raw)
    native = {m['token']:m for m in raw}
    seen, identities, forwarded = set(), set(), set()
    attachments = dict(network.endpoint_routers)
    banks = set(spec['resource_contract']['dram_regions'])
    fields = ('token','ready','finish','bytes','source','destination','data','source_memory','destination_memory')
    edges = set(network.router_links) | {(b,a) for a,b in network.router_links}
    for m in result['network_messages']:
        if m['token'] in seen or m['id'] in identities: raise ValueError('Duplicate D0 message')
        seen.add(m['token']); identities.add(m['id'])
        if any(type(m[k]) is not int or m[k] < 0 for k in ('id','ready','finish','bytes')) or m['bytes'] == 0:
            raise ValueError('Invalid D0 clock/payload')
        if m['source'] not in attachments or m['destination'] not in attachments or m['source'] == m['destination']:
            raise ValueError('Invalid D0 endpoints')
        if {m['source_memory'],m['destination_memory']} & banks:
            k = f"{m['source']}:{m['destination']}:{m['bytes']}"
            component = spec['entries'].get(k)
            if (not component or m['engine'] != 'isolated' or m.get('component_key') != k or
                    m.get('component_sha256') != object_digest(component) or
                    m['finish']-m['ready'] != component['duration_cycles'] or m['token'] in native or 'flits' in m):
                raise ValueError('D0 isolated cost/classification violation')
            total = 0
            for route in component['routes']:
                path = route['routers']; total += route['flits']
                if (not path or path[0] != attachments[m['source']] or path[-1] != attachments[m['destination']] or
                        len(set(path)) != len(path) or any((a,b) not in edges for a,b in zip(path,path[1:]))):
                    raise ValueError('Isolated component path disagrees with machine')
            width = spec['resource_contract']['flit_bytes']
            if total != (m['bytes']+width-1)//width: raise ValueError('Component flit conservation failed')
        else:
            n = native.get(m['token'])
            if not n or m['engine'] != 'booksim' or m.get('native_id') != n['id'] or any(m[k] != n[k] for k in fields):
                raise ValueError('D0 native passthrough differs')
            forwarded.add(m['token'])
    if identities != set(range(len(seen))) or forwarded != set(native): raise ValueError('Missing D0/native message')
    return dict(passed=True, native_messages=len(raw), isolated_messages=len(seen)-len(raw))


def audit(compiled, base, binding, timing, spec, result):
    from wafer_sim.analysis.timing import audit as audit_timing
    if result['independent_spatial_contract'] != spec: raise ValueError('Changed D0 prediction contract')
    projection = audit_projection(compiled, base, binding, timing, spec['resource_contract'])
    checked = audit_timing(binding, timing, result)
    return dict(passed=True, projection=projection, execution=checked,
        status=dict(execution_completed=True, semantic_audit_passed=True,
            aggregate_capacity='feasible', controller_staging_capacity='feasible', per_bank_capacity='feasible',
            dram_spatial_contention='unmodeled', single_flow_service='independent component calibrated',
            hardware_calibration='declared assumptions; not hardware measurement', streaming_rx_capacity='unmodeled'))
