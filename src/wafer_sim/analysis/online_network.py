"""Independent all-flit conservation, paths and cycle-boundary readback."""
from collections import Counter


def audit_messages(network, messages):
    attachments = dict(network.endpoint_routers)
    edges = {edge for a,b in network.router_links for edge in ((a,b),(b,a))}
    ids, tokens, flit_ids = set(), set(), set()
    used_links, injected, ejected = set(), set(), set()
    link_flits = Counter()
    for message in messages:
        identity, token = message["id"], message["token"]
        if identity in ids or token in tokens:
            raise ValueError("Repeated native message identity")
        ids.add(identity); tokens.add(token)
        size, width = message["bytes"], message["flit_bytes"]
        if type(size) is not int or type(width) is not int or size <= 0 or width <= 0:
            raise ValueError("Invalid payload or native flit width")
        flits = message["flits"]
        expected = (size+width-1)//width
        if len(flits) != expected or message["expected_flits"] != expected:
            raise ValueError("Incomplete payload: all native flits must arrive")
        source, destination = message["source"], message["destination"]
        if source == destination or source not in attachments or destination not in attachments:
            raise ValueError("Invalid native endpoints")
        if not 0 <= message["ready"] <= message["generated"]:
            raise ValueError("Message generated before readiness")
        for f in flits:
            if f["id"] in flit_ids or f["message"] != identity:
                raise ValueError("Missing/repeated/mismatched native flit")
            flit_ids.add(f["id"])
            if (f["source"] != source or f["destination"] != destination or
                    f["generated"] != message["generated"] or
                    not f["generated"] <= f["injected"] < f["injection_router_arrival"] <= f["ejected"]):
                raise ValueError("Native flit clocks or endpoints disagree")
            path = f["router_path"]
            if (not path or path[0] != attachments[source] or path[-1] != attachments[destination]
                    or len(path) != f["hops"]):
                raise ValueError("Observed native route endpoints/hops disagree")
            traversals = f["link_arrivals"]
            if len(traversals) != len(path)-1:
                raise ValueError("Native physical path incomplete")
            previous = f["injection_router_arrival"]
            for (a,b), event in zip(zip(path,path[1:]),traversals):
                if ((a,b) not in edges or (event["source"],event["destination"]) != (a,b)
                        or not previous < event["cycle"] <= f["ejected"]):
                    raise ValueError("Invalid native link or path ordering")
                slot = (a,b,event["cycle"])
                if slot in used_links:
                    raise ValueError("Native directed link supplied more than one flit/cycle")
                used_links.add(slot); link_flits[a,b] += 1
                previous = event["cycle"]
            for slots, slot in ((injected,(source,f["injected"])),(ejected,(destination,f["ejected"]))):
                if slot in slots: raise ValueError("Native endpoint exceeded one flit/cycle")
                slots.add(slot)
        if (message["first_inject"] != min(f["injected"] for f in flits)
                or message["last_inject"] != max(f["injected"] for f in flits)
                or message["first_eject"] != min(f["ejected"] for f in flits)
                or message["last_eject"] != max(f["ejected"] for f in flits)
                or message["finish"] != message["last_eject"]+1):
            raise ValueError("Native message completed before its final flit boundary")
    if ids != set(range(len(messages))) or flit_ids != set(range(len(flit_ids))):
        raise ValueError("Native message/flit identities not complete")
    return dict(passed=True,messages=len(messages),flits=len(flit_ids),
        payload_bytes=sum(m["bytes"] for m in messages),
        padded_bytes=sum(m["expected_flits"]*m["flit_bytes"] for m in messages),
        physical_link_flits=[dict(source=a,destination=b,flits=n) for (a,b),n in sorted(link_flits.items())])
