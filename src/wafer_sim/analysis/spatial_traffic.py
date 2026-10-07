"""All-flit spatial traffic accounting on the exported physical resource graph.

Payload bytes use source flit-ID order, including the short last flit; occupied
wire bytes include its padding. Hops count inter-router traversals, not routers.
The x=0 cut is a router-center graph partition, not detailed wire routing.
"""
from collections import defaultdict
from math import ceil

from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.architecture.spatial import Network


def project(exported, messages, active_endpoints):
    network = Network(tuple((e["node"], e["router"]) for e in exported["endpoints"]),
                      tuple((l["src"], l["dst"]) for l in exported["inputs"]["links"]), "observed export")
    audit_messages(network, messages)
    endpoints = sorted(active_endpoints)
    if len(endpoints) != len(set(endpoints)) or not set(endpoints) <= set(dict(network.endpoint_routers)):
        raise ValueError("Unique active physical endpoints required for concentration statistics")
    traffic = {e: dict(endpoint=e, in_payload_bytes=0, out_payload_bytes=0,
                      in_wire_bytes=0, out_wire_bytes=0) for e in endpoints}
    loads = {}
    for link in exported["inputs"]["links"]:
        if not link["bidirectional"] or link["bandwidth"] % 8:
            raise ValueError("Expected byte-aligned bidirectional physical links")
        for a, b in ((link["src"], link["dst"]), (link["dst"], link["src"])):
            loads[a, b] = dict(source=a, destination=b, payload_bytes=0, wire_bytes=0,
                               flits=0, bytes_per_cycle=link["bandwidth"]//8)
    centers = {}
    for router, placed in enumerate(exported["inputs"]["placement"]["chiplets"]):
        # This pinned WoW fork exports center coordinates, unlike some upstream
        # RapidChiplet formats. See its rapidchiplet/visualizer.py: rectangles
        # start at position-width/2 and links connect position to position.
        centers[router] = placed["position"]["x"]
    side = {r: int(x >= 0) for r, x in centers.items()}
    cut = {"left_to_right": dict(payload_bytes=0, wire_bytes=0, capacity_bytes_per_cycle=0),
           "right_to_left": dict(payload_bytes=0, wire_bytes=0, capacity_bytes_per_cycle=0)}
    for (a, b), row in loads.items():
        if side[a] != side[b]:
            direction = "left_to_right" if side[a] == 0 else "right_to_left"
            cut[direction]["capacity_bytes_per_cycle"] += row["bytes_per_cycle"]
    traversed_messages = defaultdict(set)
    for message in messages:
        src, dst = message["source"], message["destination"]
        if src not in traffic or dst not in traffic: raise ValueError("Message outside active endpoints")
        payload, width = message["bytes"], message["flit_bytes"]
        wire = message["expected_flits"]*width
        traffic[src]["out_payload_bytes"] += payload; traffic[dst]["in_payload_bytes"] += payload
        traffic[src]["out_wire_bytes"] += wire; traffic[dst]["in_wire_bytes"] += wire
        for i, flit in enumerate(sorted(message["flits"], key=lambda f: f["id"])):
            carried = min(width, payload-i*width)
            for event in flit["link_arrivals"]:
                a, b = event["source"], event["destination"]
                row = loads[a, b]
                row["payload_bytes"] += carried; row["wire_bytes"] += width; row["flits"] += 1
                traversed_messages[a, b].add(message["id"])
                if side[a] != side[b]:
                    direction = "left_to_right" if side[a] == 0 else "right_to_left"
                    cut[direction]["payload_bytes"] += carried
                    cut[direction]["wire_bytes"] += width
    for row in traffic.values(): row["total_payload_bytes"] = row["in_payload_bytes"]+row["out_payload_bytes"]
    for edge, row in loads.items(): row["messages"] = len(traversed_messages[edge])
    total = sum(m["bytes"] for m in messages)
    maximum = max((r["total_payload_bytes"] for r in traffic.values()), default=0)
    average = 2*total/len(traffic) if traffic else 0
    for row in cut.values():
        capacity = row["capacity_bytes_per_cycle"]
        if not capacity and row["wire_bytes"]: raise ValueError("Traffic on zero-capacity cut")
        row["wire_service_lower_bound_cycles"] = ceil(row["wire_bytes"]/capacity) if capacity else 0
    return dict(endpoint_rows=list(traffic.values()), active_endpoint_count=len(traffic),
        total_payload_bytes=total, total_wire_bytes=sum(m["expected_flits"]*m["flit_bytes"] for m in messages),
        max_endpoint_payload_bytes=maximum, endpoint_max_over_mean=maximum/average if average else 0,
        directed_links=list(loads.values()),
        max_directed_link_payload_bytes=max((r["payload_bytes"] for r in loads.values()), default=0),
        max_directed_link_wire_bytes=max((r["wire_bytes"] for r in loads.values()), default=0),
        payload_byte_hops=sum(r["payload_bytes"] for r in loads.values()),
        wire_byte_hops=sum(r["wire_bytes"] for r in loads.values()),
        cut=dict(definition="router rectangle centers: x<0 left, x>=0 right; all layers; directed exported links",
            router_x=centers, directions=cut,
            wire_service_lower_bound_cycles=max(r["wire_service_lower_bound_cycles"] for r in cut.values())),
        scope="Integrated volume, not utilization or saturation. Count every physical traversal, including repeated cut crossings; native padding charged separately.")
