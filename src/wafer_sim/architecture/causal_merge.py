"""Declared four-router merge component; no workload or service scheduler."""
from copy import deepcopy

PORTS = [['endpoint/0', 'endpoint/1', 'router/2'], ['endpoint/2', 'router/2'],
         ['router/0', 'router/1', 'router/3'], ['endpoint/3', 'router/2']]
FORWARD = [2, 1, 2, 0]
ENDPOINT_ROUTERS = [0, 0, 1, 3]
POLICY = dict(num_vcs=1, packet_size=1, vc_alloc_delay=1, sw_alloc_delay=1,
              routing_delay=0, credit_delay=0, wait_for_tail_credit=0,
              vc_busy_when_full=0, output_buffer_size=-1, input_speedup=1,
              output_speedup=1, internal_speedup=1.0, buffer_policy='private',
              vc_allocator='islip', sw_allocator='islip', alloc_iters=1,
              speculative=0, hold_switch_for_packet=0)


def validate(contract):
    required = set(POLICY) | {'routers', 'forward_outputs', 'endpoint_routers',
        'router_link_latency', 'endpoint_link_latency', 'crossbar_delay',
        'capacity_flits', 'flit_bytes'}
    if set(contract) != required: raise ValueError('Incomplete/unknown causal merge contract')
    if (contract['routers'] != PORTS or contract['forward_outputs'] != FORWARD or
            contract['endpoint_routers'] != ENDPOINT_ROUTERS or
            any(contract[k] != v for k, v in POLICY.items())):
        raise ValueError('Unsupported causal merge organization/policy')
    for k in ('router_link_latency', 'endpoint_link_latency', 'crossbar_delay', 'capacity_flits', 'flit_bytes'):
        if type(contract[k]) is not int or contract[k] <= 0: raise ValueError('Invalid '+k)
    return deepcopy(contract)


def topology(contract):
    validate(contract); rows = []
    for r, peers in enumerate(PORTS):
        fields = [f'router {r}']
        for identity in peers:
            kind, number = identity.split('/')
            delay = contract['router_link_latency'] if kind == 'router' else contract['endpoint_link_latency']
            fields.append(f'{"node" if kind == "endpoint" else "router"} {number} {delay}')
        rows.append(' '.join(fields))
    return '\n'.join(rows)+'\n'
