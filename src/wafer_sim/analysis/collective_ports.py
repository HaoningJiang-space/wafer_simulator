"""Join checked collective calls to full source ownership and tensor ports.

This is a read-only evidence join, not inferred allocation or execution order.
"""
from collections import Counter
import gzip
from itertools import zip_longest
import json

from wafer_sim.workloads.call_regions import tensor_identity


def check_call(call, row):
    if (call["rank"],call["node_id"],call["byte_offset"],call["name"]) != (
            row["rank"],row["node_id"],row["byte_offset"],row["name"]):
        raise ValueError("Collective and effect source identity differ")
    if any(call[k] != row[k] for k in ("source_ctrl_deps","source_data_deps")):
        raise ValueError("Collective dependency ports changed")
    refs={r["path"]:r for r in row["effects"]["inputs"]+row["effects"]["outputs"]}
    for slot in (call["intent"] or {}).get("slots",[]):
        for role in ("source","destination"):
            ref=slot[role]
            if ref["path"] not in refs or tensor_identity(ref) != tensor_identity(refs[ref["path"]]):
                raise ValueError("Collective role no longer identifies the same source tensor")


def join_ports(report, effects_path, owners_path, output):
    calls={c["node_id"]:c for c in report["calls"]}
    if len(calls)!=len(report["calls"]):
        raise ValueError("Duplicate CPU collective identity")
    wanted=set(calls)
    for c in calls.values(): wanted.update(c["gpu_nodes"]+c["source_wait_nodes"])
    ports,checked,counts={},set(),Counter()
    with gzip.open(effects_path,"rt") as effects, gzip.open(owners_path,"rt") as owners:
        for a,b in zip_longest(effects,owners):
            if a is None or b is None: raise ValueError("Incomplete source/owner join")
            row,owner=json.loads(a),json.loads(b)
            if any(row[k]!=owner[k] for k in ("rank","node_id","byte_offset")):
                raise ValueError("Source owner identity changed")
            if row["rank"]!=report["rank"]: raise ValueError("Cross-rank ownership join")
            counts["source_nodes"]+=1
            node=row["node_id"]
            if node in wanted:
                if node in ports: raise ValueError("Duplicate source port")
                ports[node]=owner
            if node in calls:
                check_call(calls[node],row); checked.add(node)
    if set(calls)!=checked or set(ports)!=wanted:
        raise ValueError("Missing collective source/implementation/wait port")
    with gzip.open(output,"wt",compresslevel=1) as stream:
        for c in report["calls"]:
            slots=(c["intent"] or {}).get("slots",[])
            missing=["allocation_generation","exact_byte_footprint","access_order"]
            if c["identity"] is None: missing.append("communicator_and_sequence")
            row=dict(rank=report["rank"],call=ports[c["node_id"]],identity=c["identity"],
                input_operands=[s["source"] for s in slots],output_operands=[s["destination"] for s in slots],
                gpu_ports=[ports[n] for n in c["gpu_nodes"]],wait_ports=[ports[n] for n in c["source_wait_nodes"]],
                source_ctrl_deps=c["source_ctrl_deps"],source_data_deps=c["source_data_deps"],
                required_binding_evidence=missing,value_versions_bound=False,
                cpu_return_completes_output=False,source_duration_used=False)
            stream.write(json.dumps(row,sort_keys=True,separators=(",",":"))+"\n")
            counts["collective_calls"]+=1
            counts["operand_pairs"]+=len(slots)
            counts["calls_with_explicit_identity"]+=c["identity"] is not None
            counts["gpu_ports"]+=len(row["gpu_ports"])
            counts["wait_ports"]+=len(row["wait_ports"])
            counts["calls_with_same_storage_input_output"]+=any(
                (s["source"]["storage_id"],s["source"]["source_device"])==
                (s["destination"]["storage_id"],s["destination"]["source_device"]) for s in slots)
    # Independently check the emitted IDs, role descriptors and original edges.
    with gzip.open(output,"rt") as stream:
        saved=[json.loads(line) for line in stream]
    if len(saved)!=len(calls) or {r["call"]["node_id"] for r in saved}!=set(calls):
        raise ValueError("Output lost a collective")
    for r in saved:
        c=calls[r["call"]["node_id"]]
        if r["call"]!=ports[c["node_id"]] or r["identity"]!=c["identity"]:
            raise ValueError("Output source identity changed")
        for side,role in (("input","source"),("output","destination")):
            actual=[(v["path"],tensor_identity(v)) for v in r[side+"_operands"]]
            expected=[(s[role]["path"],tensor_identity(s[role])) for s in (c["intent"] or {}).get("slots",[])]
            if actual!=expected:
                raise ValueError("Output tensor role changed")
        for key in ("source_ctrl_deps","source_data_deps"):
            if r[key]!=c[key]: raise ValueError("Output source dependency lost")
        for key,nodes in (("gpu_ports",c["gpu_nodes"]),("wait_ports",c["source_wait_nodes"])):
            if r[key]!=[ports[n] for n in nodes]: raise ValueError("Completion port lost")
    return dict(rank=report["rank"],counts=dict(counts),passed=True,
                value_versions_bound=False,complete_target_workload=False)
