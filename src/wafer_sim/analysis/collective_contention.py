"""Passive native-path residence and shared-link observations, without reruns."""
from collections import defaultdict


def summarize(exported, messages):
    links = {tuple(sorted((l["src"], l["dst"]))): l for l in exported["inputs"]["links"]}
    router_delay = exported["resources"]["router_latency_cycles"]
    chiplets = exported["inputs"]["chiplets"]
    placed = exported["inputs"]["placement"]["chiplets"]
    rows, traversals = [], defaultdict(list)
    for message in messages:
        first = min(message["flits"], key=lambda f: (f["injected"], f["id"]))
        for flit in message["flits"]:
            for event in flit["link_arrivals"]:
                traversals[event["source"], event["destination"]].append((message["id"], event["cycle"]))
        arrival = first["injection_router_arrival"]
        router = first["router_path"][0]
        residence = []
        for event in first["link_arrivals"]:
            propagation = links[tuple(sorted((event["source"], event["destination"])))]["latency"]
            excess = event["cycle"]-arrival-propagation-router_delay
            if excess < 0:
                raise ValueError("Native residence below the declared router pipeline")
            residence.append(dict(router=router, excess_cycles=excess))
            arrival, router = event["cycle"], event["destination"]
        access = chiplets[placed[router]["name"]]["unit_to_router_latency"]
        excess = first["ejected"]-arrival-access-router_delay
        if excess < 0:
            raise ValueError("Native ejection below the declared pipeline/channel latency")
        residence.append(dict(router=router, excess_cycles=excess))
        rows.append(dict(token=message["token"], message=message["id"], source=message["source"],
            destination=message["destination"], ready=message["ready"],finish=message["finish"],
            first_injection_wait=message["first_inject"]-message["ready"],
            first_flit=first["id"], routers=first["router_path"],
            first_flit_router_excess_cycles=sum(e["excess_cycles"] for e in residence),
            router_residence=residence))
    return dict(messages=rows,
        first_flit_router_excess_cycles=sum(r["first_flit_router_excess_cycles"] for r in rows),
        shared_links=[dict(source=a,destination=b,messages=len({m for m,_ in values}),
                           flits=len(values),first_arrival=min(t for _,t in values),last_arrival=max(t for _,t in values))
                      for (a,b),values in sorted(traversals.items()) if len({m for m,_ in values})>1],
        scope="Observed first-injected-flit residence beyond configured router pipeline on its actual path; includes arbitration/credit effects, not a counterfactual or unique cause. Shared-link totals include sequential messages.")
