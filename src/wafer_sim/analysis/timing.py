"""Independent service, dependency and capacity readback for timed execution."""
from collections import defaultdict
from fractions import Fraction
from math import ceil

import networkx as nx


def audit(binding, timing, result):
    if not result["complete"] or result["application_cycles"] is None:
        raise ValueError("Incomplete execution cannot pass completion audit")
    services = {(s.resource,s.unit):s for s in (
        *timing.services, *(l.service for l in timing.links),
        *(s for e in timing.endpoints for s in (e.injection,e.ejection)))}
    records,by_resource,by_token = result["services"],defaultdict(list),defaultdict(list)
    native_messages = None
    if result.get("network_backend") == "booksim":
        from wafer_sim.analysis.online_network import audit_messages
        audit_messages(binding.network, result["network_messages"])
        native_messages = {m["token"]:m for m in result["network_messages"]}
    network_tokens = set()
    physical = nx.Graph()
    physical.add_nodes_from(dict(binding.network.endpoint_routers).values())
    physical.add_edges_from(binding.network.router_links)
    distances = {}
    last_ready = 0
    resource_tail = {}
    if set(result["operations"]) != set(binding.plans):
        raise ValueError("Extra or missing operation timing")
    for i,event in enumerate(records):
        if event["id"] != i: raise ValueError("Service identities not complete and ordered")
        if any(type(event[k]) is not int or event[k] < 0 for k in
               ("ready", "start", "resource_released", "finish")):
            raise ValueError("Service clocks must be nonnegative integer cycles")
        if event["ready"] < last_ready:
            raise ValueError("Service submissions are not chronological")
        last_ready = event["ready"]
        tail = resource_tail.get(event["resource"])
        free = records[tail]["resource_released"] if tail is not None else 0
        expected_start = max(event["ready"], free)
        expected_predecessor = tail if free > event["ready"] else None
        if (event["start"] != expected_start or
                event["resource_predecessor"] != expected_predecessor):
            raise ValueError("Resource trace violates work-conserving FCFS policy")
        resource_tail[event["resource"]] = i
        service = services[event["resource"],event["unit"]]
        duration = ceil(Fraction(event["amount"]*service.rate_denominator,service.rate_numerator))
        if (event["start"] < event["ready"] or event["resource_released"]-event["start"] != duration or
                event["finish"]-event["resource_released"] != service.latency_cycles):
            raise ValueError("Resource service rate, latency or readiness violation")
        by_resource[event["resource"]].append(event)
        by_token[event["token"]].append(event)
        if event["start"] > event["ready"]:
            pred = event["resource_predecessor"]
            if (type(pred) is not int or not 0 <= pred < i or
                    records[pred]["resource"] != event["resource"] or
                    records[pred]["resource_released"] != event["start"]):
                raise ValueError("Resource wait lacks a releasing predecessor")
    for events in by_resource.values():
        ordered = sorted(events,key=lambda e:(e["start"],e["id"]))
        if any(a["resource_released"] > b["start"] for a,b in zip(ordered,ordered[1:])):
            raise ValueError("Overlapping service on a finite resource")
    totals = {}
    for resource,events in by_resource.items():
        work = defaultdict(int)
        for event in events: work[event["unit"]] += event["amount"]
        totals[resource] = dict(busy_cycles=sum(e["resource_released"]-e["start"] for e in events),
            queue_wait_cycles=sum(e["start"]-e["ready"] for e in events),requests=len(events),work=dict(work))
    if totals != result["resources"]: raise ValueError("Resource summary differs from service records")
    phases = {(p["operation"],p["phase"]):p for p in result["phases"]}
    if len(phases) != len(result["phases"]): raise ValueError("Duplicate phase")
    expected_tokens = set()
    for op,plan in binding.plans.items():
        for index,phase in enumerate(plan.phases):
            previous = max((phases[op,p]["finish"] for p in plan.predecessors(index)),
                           default=result["operations"][op]["admitted"])
            row = phases[op,index]
            if plan.dependencies is not None and (row.get("action") != plan.action_ids[index] or
                    tuple(row.get("predecessors", ())) != plan.dependencies[index]):
                raise ValueError("Collective action identity or dependencies disagree")
            token = f"{op}/phase/{index}"
            if phase.transfer is not None and native_messages is not None:
                network_tokens.add(token)
                t = phase.transfer
                m = native_messages[token]
                if (row["ready"] != previous or row["kind"] != "transfer" or
                        row["network_token"] != token or row["transfer_bytes"] != t.size_bytes or
                        m["ready"] != previous or m["finish"] != row["finish"] or
                        m["source"] != t.source_endpoint or m["destination"] != t.destination_endpoint or
                        m["bytes"] != t.size_bytes or m["data"] != t.data or
                        m["source_memory"] != t.source_memory or m["destination_memory"] != t.destination_memory):
                    raise ValueError("Native transfer differs from admitted phase")
                previous = row["finish"]
                continue
            expected_tokens.add(token)
            events = by_token[token]
            if (row["ready"] != previous or row["kind"] != phase.kind or
                    not events or events[0]["ready"] != previous or events[-1]["finish"] != row["finish"]):
                raise ValueError("Missing or mistimed phase service")
            if any(e["step"] != i for i,e in enumerate(events)) or any(
                    a["finish"] != b["ready"] for a,b in zip(events,events[1:])):
                raise ValueError("Next service began before prior completion")
            if phase.transfer is None:
                demands = [(d.resource,d.unit,d.amount) for d in phase.demands]
                category = "compute" if phase.kind == "compute" else "memory"
            else:
                category = "network"
                t = phase.transfer
                path = tuple(row["path"])
                attachments = dict(binding.network.endpoint_routers)
                links = {(l.source,l.destination):l.service for l in timing.links}
                endpoints = {e.endpoint:e for e in timing.endpoints}
                if (not path or path[0] != attachments[t.source_endpoint] or
                        path[-1] != attachments[t.destination_endpoint] or len(set(path)) != len(path)):
                    raise ValueError("Transfer path endpoint or loop mismatch")
                end = attachments[t.destination_endpoint]
                if end not in distances:
                    distances[end] = nx.single_source_shortest_path_length(physical,end)
                distance = distances[end]
                expected = [attachments[t.source_endpoint]]
                while expected[-1] != end:
                    current = expected[-1]
                    expected.append(min(n for n in physical.neighbors(current)
                                        if distance.get(n) == distance[current]-1))
                if tuple(expected) != path:
                    raise ValueError("Transfer violates minimum-hop lexicographic route policy")
                route = [endpoints[t.source_endpoint].injection,
                         *(links[a,b] for a,b in zip(path,path[1:])),endpoints[t.destination_endpoint].ejection]
                demands = [(s.resource,"bytes",t.size_bytes) for s in route]
                if row["transfer_bytes"] != t.size_bytes: raise ValueError("Transfer byte conservation failed")
            if demands != [(e["resource"],e["unit"],e["amount"]) for e in events]:
                raise ValueError("Phase work conservation failed")
            if any(e["category"] != category for e in events):
                raise ValueError("Incorrect resource attribution category")
            previous = row["finish"]
        if max(phases[op,i]["finish"] for i in range(len(plan.phases))) != result["operations"][op]["finish"]:
            raise ValueError("Operation finished before its last phase")
    if expected_tokens != set(by_token) or len(phases) != sum(len(p.phases) for p in binding.plans.values()):
        raise ValueError("Extra or missing phase/service")
    if native_messages is not None and network_tokens != set(native_messages):
        raise ValueError("Extra or missing native transmission")
    expected_ready = {d.id: 0 for d in binding.graph.data.values() if d.producer is None}
    for op, plan in binding.plans.items():
        if result["operations"][op].get("retired") != result["operations"][op]["finish"]:
            raise ValueError("Retirement clock mismatch")
        for data in binding.graph.operations[op].outputs:
            expected_ready[data] = max(phases[op, i]["finish"] for i in plan.output_phases(data))
    if result.get("output_ready") != expected_ready:
        raise ValueError("Output published before required final writes or missing readiness")
    allocations, used = {},dict.fromkeys(binding.memory,0)
    def reserve(key,memory,size):
        if key in allocations: raise ValueError("Duplicate allocation")
        allocations[key] = memory,size
        used[memory] += size
        if used[memory] > binding.memory[memory].capacity_bytes:
            raise ValueError("Regional capacity exceeded")
    def release(key):
        memory,size = allocations.pop(key)
        used[memory] -= size
    remaining = {d:set(consumers) for d,consumers in binding.graph.consumers.items()}
    for d in binding.graph.data.values():
        if d.producer is None and (remaining[d.id] or d.retain):
            reserve(("object",d.id),binding.homes[d.id],d.size_bytes)
    admitted,completed = set(),set()
    published = {d.id for d in binding.graph.data.values() if d.producer is None}
    peak = used.copy()
    last_cycle = 0
    for event in result["lifecycle"]:
        op,cycle = event["operation"],event["cycle"]
        if cycle < last_cycle: raise ValueError("Lifecycle records are not chronological")
        last_cycle = cycle
        if event["event"] == "admit":
            operation = binding.graph.operations[op]
            if (op in admitted or not set(operation.control_deps) <= completed or
                    not set(operation.inputs) <= published or
                    any(("object", d) not in allocations for d in operation.inputs)):
                raise ValueError("Premature or duplicate admission")
            if cycle != result["operations"][op]["admitted"]: raise ValueError("Admission clock mismatch")
            for a in binding.plans[op].reservations: reserve(a.key,a.memory,a.size_bytes)
            admitted.add(op)
        elif event["event"] == "output_ready":
            data = event["data"]
            if (op not in admitted or op in completed or data in published or
                    data not in binding.graph.operations[op].outputs or cycle != expected_ready[data] or
                    ("object", data) not in allocations):
                raise ValueError("Invalid output-ready event")
            published.add(data)
        elif event["event"] == "retire":
            if op not in admitted or op in completed or cycle != result["operations"][op]["finish"]:
                raise ValueError("Invalid operation completion")
            operation = binding.graph.operations[op]
            if not set(operation.outputs) <= published:
                raise ValueError("Retired operation has unpublished outputs")
            completed.add(op)
            for d in operation.inputs: remaining[d].remove(op)
            for d in operation.inputs+operation.outputs:
                obj = binding.graph.data[d]
                if (not remaining[d] and not obj.retain and
                        (obj.producer is None or obj.producer in completed) and ("object",d) in allocations):
                    release(("object",d))
            for a in binding.plans[op].reservations:
                if a.key[0] != "object": release(a.key)
        else:
            raise ValueError("Unknown lifecycle event")
        if used != event["used_bytes"]: raise ValueError("Storage accounting mismatch")
        peak = {m:max(peak[m],used[m]) for m in used}
    if completed != set(binding.plans) or peak != result["peak_bytes"]:
        raise ValueError("Incomplete work or incorrect peak capacity")
    if used != result["storage"]["used_bytes"]:
        raise ValueError("Final resident capacity differs from lifecycle")
    if published != set(binding.graph.data):
        raise ValueError("Missing data publication")
    for op, operation in binding.graph.operations.items():
        ready = max([result["operations"][p]["finish"] for p in operation.control_deps] +
                    [expected_ready[d] for d in operation.inputs], default=0)
        if ready != result["operations"][op]["ready"]: raise ValueError("Dependency-ready clock mismatch")
        row = result["operations"][op]
        if row["admitted"] < ready or row["capacity_wait_cycles"] != row["admitted"]-ready:
            raise ValueError("Capacity-wait accounting mismatch")
    expected_available = sorted(d.id for d in binding.graph.data.values() if d.retain)
    storage = result["storage"]
    if (storage["available_data"] != expected_available or storage["completed"] != sorted(completed)
            or storage["active_phases"] or not storage["all_operations_completed"]
            or storage["peak_bytes"] != peak or result["blocked"] or not result["timing_evaluated"]):
        raise ValueError("Terminal execution state differs from checked lifecycle")
    makespan = max(r["finish"] for r in result["operations"].values())
    if makespan != result["application_cycles"] or makespan != result["stopped_cycle"]:
        raise ValueError("Terminal work excluded")
    return dict(passed=True,operations=len(completed),phases=len(phases),services=len(records),
                application_cycles=makespan,source_duration_used=False)
