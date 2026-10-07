"""Independent packet conservation, path, service, FCFS and completion audit."""
from collections import defaultdict
import networkx as nx
from wafer_sim.analysis.online_network import audit_messages


def audit_pipeline(binding,timing,messages,records,model):
    audit_messages(binding.network,messages)
    if model['model']!='packet_pipeline_v1' or model['router_issue_cycles']!=2:
        raise ValueError('Unsupported packet contract')
    width=model['flit_bytes']
    definitions={}
    for e in timing.endpoints:
        definitions[e.injection.resource]=(1,e.injection.latency_cycles+1,e.injection)
        definitions[e.ejection.resource]=(2,e.ejection.latency_cycles+1,e.ejection)
    links={(l.source,l.destination):l.service.resource for l in timing.links}
    for l in timing.links: definitions[l.service.resource]=(2,l.service.latency_cycles,l.service)
    if any(s.rate_numerator!=width*s.rate_denominator or latency<period for period,latency,s in definitions.values()):
        raise ValueError('Invalid pipeline service definitions')
    tail={};by_packet=defaultdict(list);last_ready=-1
    for i,e in enumerate(records):
        if e['id']!=i or e['unit']!='packet' or e['amount']!=1 or e['category']!='network':
            raise ValueError('Packet service identity/work mismatch')
        if any(type(e[k]) is not int or e[k]<0 for k in ('ready','start','resource_released','finish')):
            raise ValueError('Invalid packet service clock')
        period,flight,_=definitions[e['resource']]
        prior=tail.get(e['resource']);free=prior['resource_released'] if prior else 0
        if (e['ready']<last_ready or e['start']!=max(e['ready'],free)
                or e['resource_predecessor']!=(prior['id'] if free>e['ready'] else None)
                or e['resource_released']!=e['start']+period or e['finish']!=e['start']+flight):
            raise ValueError('Pipeline FCFS/service violation')
        last_ready=e['ready'];tail[e['resource']]=e;by_packet[e['token']].append(e)
    graph=nx.Graph(binding.network.router_links);attachments=dict(binding.network.endpoint_routers)
    endpoints={e.endpoint:e for e in timing.endpoints};expected=set()
    for m in messages:
        if m['flit_bytes']!=width or m['generated']!=m['ready']: raise ValueError('Packet creation/width mismatch')
        distance=nx.single_source_shortest_path_length(graph,attachments[m['destination']])
        path=[attachments[m['source']]]
        while path[-1]!=attachments[m['destination']]:
            path.append(min(n for n in graph.neighbors(path[-1]) if distance[n]==distance[path[-1]]-1))
        resources=[endpoints[m['source']].injection.resource,
            *(links[a,b] for a,b in zip(path,path[1:])),endpoints[m['destination']].ejection.resource]
        for f in m['flits']:
            token=str(f['id']);expected.add(token);events=by_packet[token]
            if (f['router_path']!=path or [e['resource'] for e in events]!=resources
                    or [e['step'] for e in events]!=list(range(len(resources)))
                    or events[0]['ready']!=m['ready']
                    or any(a['finish']!=b['ready'] for a,b in zip(events,events[1:]))):
                raise ValueError('Packet path or per-hop dependency mismatch')
            if (f['injected']!=events[0]['start'] or f['injection_router_arrival']!=events[0]['finish']
                    or f['ejected']+1!=events[-1]['finish']
                    or [e['cycle'] for e in f['link_arrivals']]!=[e['finish'] for e in events[1:-1]]):
                raise ValueError('Packet timestamp mismatch')
    if set(by_packet)!=expected: raise ValueError('Extra or missing packet service')
    return dict(passed=True,packets=len(expected),services=len(records))
