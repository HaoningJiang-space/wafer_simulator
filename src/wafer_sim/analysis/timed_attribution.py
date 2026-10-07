"""Observed critical service chain and message/path accounting; not intervention."""
from collections import Counter, defaultdict


def critical_chain(binding, result):
    nodes = {"root":dict(time=0,parents=(),duration=0,category="join")}
    phases = {(p["operation"],p["phase"]):p for p in result["phases"]}
    services = defaultdict(list)
    for row in result["services"]: services[row["token"]].append(row)

    def node(key,time,parents,duration=0,category="join",**fields):
        if key in nodes: raise ValueError("Repeated critical-chain point")
        nodes[key] = dict(time=time,parents=tuple(parents),duration=duration,category=category,**fields)

    for op,plan in binding.plans.items():
        row = result["operations"][op]
        operation = binding.graph.operations[op]
        parents = ([f"op:{p}:finish" for p in operation.control_deps] +
                   [f"data:{d}:ready" for d in operation.inputs
                    if binding.graph.data[d].producer is not None]) or ["root"]
        node(f"op:{op}:ready",row["ready"],parents)
        node(f"op:{op}:admit",row["admitted"],[f"op:{op}:ready"],
             row["capacity_wait_cycles"],"capacity",operation=op)
        for index,phase in enumerate(plan.phases):
            incoming = [f"phase:{op}:{i}:finish" for i in plan.predecessors(index)] or [f"op:{op}:admit"]
            previous = f"phase:{op}:{index}:ready"
            token = f"{op}/phase/{index}"
            p = phases[op,index]
            node(previous,p["ready"],incoming)
            if phase.kind == 'memory_network':
                move=next(m for m in result['boundary']['moves'] if m['token']==token)
                finishes=[]
                for packet in move['packets']:
                    k=packet['ordinal'];base=f'boundary:{token}:{k}'
                    # Source admission wait is observed duration, not a claim
                    # that an omitted internal queue has been causally resolved.
                    node(base+':read-ready',packet['reserved'],[previous],
                         packet['reserved']-p['ready'],'source_queue',operation=op,phase=index,token=token)
                    point=base+':read-ready'
                    for kind in ('read','write'):
                        if kind=='write':
                            node(base+':receive',packet['received'],[point],
                                 packet['received']-packet['supplied'],'network',operation=op,phase=index,token=token)
                            point=base+':receive'
                        event=services[f'{token}/{kind}/{k}'][0];identity=event['id']
                        incoming=[point]
                        if event['resource_predecessor'] is not None:
                            incoming.append(f"service:{event['resource_predecessor']}:release")
                        node(f'service:{identity}:start',event['start'],incoming)
                        node(f'service:{identity}:release',event['resource_released'],
                             [f'service:{identity}:start'],event['resource_released']-event['start'],
                             'memory',operation=op,phase=index,resource=event['resource'],token=token)
                        node(f'service:{identity}:finish',event['finish'],[f'service:{identity}:release'],
                             event['finish']-event['resource_released'],'memory',operation=op,phase=index,token=token)
                        point=f'service:{identity}:finish'
                    finishes.append(point)
                previous=f'boundary:{token}:commit'
                node(previous,p['finish'],finishes)
            elif phase.transfer is not None and result.get("network_backend") in {"booksim","packet_pipeline"}:
                point = f"network:{token}"
                node(point,p["finish"],[previous],p["finish"]-p["ready"],"network",
                     operation=op,phase=index,token=token)
                previous = point
            else:
                for event in services[token]:
                    identity = event["id"]
                    incoming = [previous]
                    if event["resource_predecessor"] is not None:
                        incoming.append(f"service:{event['resource_predecessor']}:release")
                    node(f"service:{identity}:start",event["start"],incoming)
                    node(f"service:{identity}:release",event["resource_released"],
                        [f"service:{identity}:start"],event["resource_released"]-event["start"],
                        event["category"],operation=op,phase=index,resource=event["resource"],token=token)
                    node(f"service:{identity}:finish",event["finish"],[f"service:{identity}:release"],
                         event["finish"]-event["resource_released"],event["category"],
                         operation=op,phase=index,resource=event["resource"],token=token)
                    previous = f"service:{identity}:finish"
            node(f"phase:{op}:{index}:finish",p["finish"],[previous])
        node(f"op:{op}:finish",row["finish"],
             [f"phase:{op}:{i}:finish" for i in range(len(plan.phases))])
        for data in operation.outputs:
            node(f"data:{data}:ready",result["output_ready"][data],
                 [f"phase:{op}:{i}:finish" for i in plan.output_phases(data)])
    for key,row in nodes.items():
        if key == "root": continue
        if row["time"] != max(nodes[p]["time"] for p in row["parents"])+row["duration"]:
            raise ValueError("Observed critical chain does not close at "+key)
    current = max((f"op:{op}:finish" for op in binding.plans),key=lambda k:(nodes[k]["time"],k))
    selected, seen, totals = [],set(),Counter()
    while current != "root":
        if current in seen: raise ValueError("Cyclic observed critical chain")
        seen.add(current)
        row=nodes[current]
        if row["duration"]:
            selected.append(dict(point=current,start=row["time"]-row["duration"],finish=row["time"],
                                 **{k:v for k,v in row.items() if k not in {"parents","time"}}))
            totals[row["category"]] += row["duration"]
        current=max(row["parents"],key=lambda k:(nodes[k]["time"],k))
    if sum(totals.values()) != result["application_cycles"]:
        raise ValueError("Critical service intervals do not sum to application time")
    return dict(segments=selected[::-1],cycles=dict(totals),application_cycles=result["application_cycles"],
                scope="one observed critical chain; overlapping resource waits are not added twice")


def message_summary(messages):
    rows=[]
    for m in messages:
        route_counts=Counter(tuple(f["router_path"]) for f in m["flits"])
        rows.append(dict(token=m["token"],source=m["source"],destination=m["destination"],
            bytes=m["bytes"],flits=m["expected_flits"],ready=m["ready"],finish=m["finish"],
            duration=m["finish"]-m["ready"],injection_wait=m["first_inject"]-m["ready"],
            injection_span=m["last_inject"]-m["first_inject"],
            first_inject_to_complete=m["finish"]-m["first_inject"],
            packet_latency_mean=sum(f["ejected"]-f["generated"] for f in m["flits"])/len(m["flits"]),
            routes=[dict(routers=list(path),flits=count) for path,count in sorted(route_counts.items())]))
    return rows
