"""Independent capacity, max-min bottleneck and fluid-work readback for D1."""
from collections import defaultdict
from fractions import Fraction

import networkx as nx

from wafer_sim.analysis.memory_abstraction import audit_projection


def rational(value, positive=True):
    if (not isinstance(value,list) or len(value)!=2 or any(type(x) is not int for x in value)
            or value[1]<=0 or (positive and value[0]<=0)):
        raise ValueError('Invalid rational flow record')
    f=Fraction(*value)
    if [f.numerator,f.denominator]!=value: raise ValueError('Noncanonical rational flow record')
    return f


def audit_network(network, result):
    spec=result['shared_spatial_contract']
    if spec['model']!='D1' or spec['packet_service_cycles']!=2: raise ValueError('Unexpected D1 contract')
    if 'native_network_messages' in result or any('flits' in m for m in result['network_messages']):
        raise ValueError('D1 must not contain native or per-flit execution')
    attachments=dict(network.endpoint_routers);graph=nx.Graph(network.router_links)
    capacities={};latency={}
    for link in spec['links']:
        for a,b in ((link['source'],link['destination']),(link['destination'],link['source'])):
            capacities[f'link/{a}/{b}']=Fraction(link['bytes_per_cycle'],spec['flit_bytes'])
            capacities[f'output/{a}/router/{b}']=Fraction(1,2)
            latency[a,b]=link['latency_cycles']
    if set(latency)!={edge for a,b in network.router_links for edge in ((a,b),(b,a))}:
        raise ValueError('D1 links differ from physical graph')
    for endpoint,router in attachments.items():
        capacities[f'inject/{endpoint}']=capacities[f'eject/{endpoint}']=Fraction(1)
        capacities[f'output/{router}/endpoint/{endpoint}']=Fraction(1,2)
    actual={k:rational(v) for k,v in result['flow_resource_capacities'].items()}
    if actual!=capacities: raise ValueError('D1 physical/effective resource capacities differ')
    messages={};tokens=set();paths={};remaining={};distances={}
    for m in result['network_messages']:
        if m['id'] in messages or m['token'] in tokens: raise ValueError('Duplicate D1 message')
        messages[m['id']]=m;tokens.add(m['token'])
        if any(type(m[k]) is not int or m[k]<0 for k in ('id','ready','bytes','work_packets','service_finish','finish')) or not m['bytes']:
            raise ValueError('Invalid D1 clock/payload')
        source,destination=m['source'],m['destination']
        if source not in attachments or destination not in attachments or source==destination: raise ValueError('Invalid D1 endpoints')
        start,end=attachments[source],attachments[destination]
        if end not in distances:distances[end]=nx.single_source_shortest_path_length(graph,end)
        path=[start]
        while path[-1]!=end:
            here=path[-1];path.append(min(n for n in graph.neighbors(here) if distances[end].get(n)==distances[end][here]-1))
        resources=[f'inject/{source}']
        for a,b in zip(path,path[1:]):resources.extend((f'link/{a}/{b}',f'output/{a}/router/{b}'))
        resources.extend((f'output/{end}/endpoint/{destination}',f'eject/{destination}'))
        tail=2*spec['access_latency_cycles']+len(path)*spec['router_latency_cycles']+sum(latency[a,b] for a,b in zip(path,path[1:]))
        if (m['path']!=path or m['resources']!=resources or m['engine']!='fluid' or m['propagation_cycles']!=tail or
                m['finish']!=m['service_finish']+tail or m['service_finish']<=m['ready']):
            raise ValueError('D1 route/propagation/classification violation')
        work=(m['bytes']+spec['flit_bytes']-1)//spec['flit_bytes']
        if work!=m['work_packets']: raise ValueError('D1 rounded work mismatch')
        paths[m['id']]=resources;remaining[m['id']]=Fraction(work)
    if set(messages)!=set(range(len(messages))):raise ValueError('Missing D1 message identity')
    last=0;epochs=result['flow_epochs']
    for epoch in epochs:
        begin,end=epoch['begin'],epoch['end']
        if type(begin) is not int or type(end) is not int or begin<last or end<=begin: raise ValueError('Invalid flow epoch clock')
        if any(max(m['ready'],last)<min(m['service_finish'],begin) for m in messages.values()):
            raise ValueError('Unrecorded active-flow service interval')
        active={i for i,m in messages.items() if m['ready']<=begin<m['service_finish']}
        rates={int(i):rational(v) for i,v in epoch['rates'].items()}
        if len(rates)!=len(epoch['rates']) or any(str(int(i))!=i for i in epoch['rates']) or set(rates)!=active or not active:
            raise ValueError('Flow epoch has missing/extra active demand')
        if any(begin<t<end for m in messages.values() for t in (m['ready'],m['service_finish'])):
            raise ValueError('Flow demand changes inside constant-rate epoch')
        users=defaultdict(set)
        for i in active:
            for r in paths[i]:users[r].add(i)
        saturated=set()
        for r,ids in users.items():
            load=sum((rates[i] for i in ids),Fraction())
            if load>capacities[r]:raise ValueError('Shared resource capacity exceeded')
            if load==capacities[r]:saturated.add(r)
        # Equal-weight max-min allocation has a saturated bottleneck on every
        # flow, with that flow's rate at least all rates sharing the bottleneck.
        # This certificate is independent of the predictor's filling algorithm.
        for i in active:
            if not any(r in saturated and all(rates[j]<=rates[i] for j in users[r]) for r in paths[i]):
                raise ValueError('Allocation lacks a max-min bottleneck certificate')
            before=remaining[i];amount=rates[i]*(end-begin)
            if messages[i]['service_finish']==end:
                if not rates[i]*(end-begin-1)<before<=amount:raise ValueError('Fluid release is not the first integer completion boundary')
            elif before<=amount:raise ValueError('Flow remains active after work completed')
            remaining[i]=max(Fraction(),before-amount)
        last=end
    if any(remaining.values()):raise ValueError('Incomplete fluid packet-equivalent work')
    expected=dict(messages=len(messages),epochs=len(epochs),native_processes=0,flit_events=0)
    if result['flow_counters']!=expected:raise ValueError('D1 event counts differ')
    return dict(passed=True,messages=len(messages),epochs=len(epochs),logical_bytes=sum(m['bytes'] for m in messages.values()),
        packet_equivalents=sum(m['work_packets'] for m in messages.values()),
        unified_traffic_classes=True,capacity_and_max_min_certificates=True)


def audit(compiled, base, binding, timing, spec, result):
    from wafer_sim.analysis.timing import audit as audit_timing
    if result['shared_spatial_contract']!=spec:raise ValueError('Changed D1 contract')
    projection=audit_projection(compiled,base,binding,timing,spec['resource_contract'])
    execution=audit_timing(binding,timing,result)
    return dict(passed=True,projection=projection,execution=execution,status=dict(
        execution_completed=True,semantic_audit_passed=True,aggregate_capacity='feasible',
        controller_staging_capacity='feasible',per_bank_capacity='feasible',dram_spatial_contention='fluid shared paths',
        single_flow_service='independent component verified',hardware_calibration='declared assumptions; not hardware measurement',
        streaming_rx_capacity='unmodeled'))
