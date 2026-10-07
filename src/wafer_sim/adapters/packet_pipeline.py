"""A restricted packet-service approximation to the pinned WoW trace setup.

This is not the VC/credit model. The physical channels stay one flit/cycle;
the two-cycle output initiation interval represents single-VC, non-speculative
allocation of single-flit packets. Queue discipline remains FCFS, routes remain
the coarse minimum-hop rule, and input arbitration/finite credits are omitted.
"""
from wafer_sim.architecture.timing import Service


def contract(export, flit_bytes):
    config=export['inputs']['booksim_config']
    required=dict(num_vcs=1,packet_size=1,wait_for_tail_credit=0,hold_switch_for_packet=0,
                  alloc_iters=1,priority='none',vc_allocator='separable_input_first',
                  sw_allocator='separable_input_first')
    if any(config.get(k)!=v for k,v in required.items()):
        raise ValueError('Packet pipeline only supports the pinned one-VC trace configuration')
    if (config.get('speculative',0)!=0 or export['resources']['router_latency_cycles']!=4
            or export['resources']['link_bits_per_cycle']!=8*flit_bytes):
        raise ValueError('Unsupported packet allocation or channel configuration')
    return dict(model='packet_pipeline_v1',flit_bytes=flit_bytes,router_issue_cycles=2,
        source='pinned booksim_wrapper: VC=1 + SW=1, non-speculative; IQRouter evaluate precedes update; tail frees output VC',
        routing='minimum-hop lexicographic',arbitration='FCFS output services',
        omitted=['input-VC arbitration','finite buffers and credit return','adaptive routing'])


def services(target, model):
    if model['model']!='packet_pipeline_v1' or model['router_issue_cycles']!=2:
        raise ValueError('Unsupported packet service contract')
    result={}
    def add(service,interval,flight):
        if (service.rate_numerator!=model['flit_bytes']*service.rate_denominator or flight<interval):
            raise ValueError('Packet service needs uniform one-flit channels and sufficient pipeline latency')
        value=Service(service.resource,'packet',1,interval,flight-interval)
        if (value.resource,value.unit) in result: raise ValueError('Aliased packet network resource')
        result[value.resource,value.unit]=value
    for e in target.endpoints.values():
        add(e.injection,1,e.injection.latency_cycles+1)
        add(e.ejection,2,e.ejection.latency_cycles+1)
    for link in target.links.values(): add(link,2,link.latency_cycles)
    return result
