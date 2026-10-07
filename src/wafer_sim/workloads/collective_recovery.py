"""Recover only source-proved collective bindings, without target timing.

Matching is recomputed from all ranks. Barriers bind without tensor evidence;
identity operations expose forwarding recipes but still need upstream values.
Other calls keep their exact missing evidence, rather than a blanket failure.
"""
from dataclasses import asdict

from wafer_sim.workloads.chakra_collectives import match_collectives
from wafer_sim.workloads.collective_values import bind_values, forwards_input
from wafer_sim.workloads.collectives import from_match
from wafer_sim.workloads.tensor_versions import ByteVersions


def recover(reports):
    if len({r["rank"] for r in reports}) != len(reports):
        raise ValueError("Repeated source rank")
    calls = {}
    for report in reports:
        if report["errors"]:
            raise ValueError("Source report has unresolved parsing errors")
        for call in report["calls"]:
            key = report["rank"], call["node_id"]
            if call["rank"] != key[0] or key in calls:
                raise ValueError("Repeated or inconsistent source call")
            calls[key] = call
    matched = match_collectives(reports)
    by_call, barriers = {}, []
    for match in matched["collectives"]:
        for entry in match["calls"]:
            key = entry["rank"], entry["node_id"]
            if key in by_call:
                raise ValueError("One call belongs to two collective instances")
            by_call[key] = match
        if not match["issues"] and match["kind"] == "barrier":
            values = bind_values(ByteVersions(), match, calls, {},
                                 provenance="Explicit matched source barrier; no tensor payload")
            barriers.append(dict(collective=asdict(values.collective),
                                 source_calls=values.source_calls, inputs=[], outputs=[]))
    plans = {}
    for key, call in calls.items():
        match = by_call.get(key)
        issues = list(call["issues"])
        if match is None:
            issues.append("communicator_and_sequence")
        else:
            issues.extend(match["issues"])
        intent = call["intent"]
        if intent is None:
            issues.append("operand_roles")
        kind, forwarding, bound = "unresolved_collective", [], False
        missing = []
        if not issues:
            collective = from_match(match, calls)
            if collective.kind == "barrier":
                kind, bound = "no_payload", True
            else:
                forwarding = [i for i, slot in enumerate(intent["slots"])
                              if forwards_input(collective, slot)]
                if len(forwarding) == len(intent["slots"]):
                    kind, missing = "forward_input", ["input_value_binding"]
                else:
                    kind = "payload_binding"
        if not bound and kind != "forward_input" and intent and intent["slots"]:
            missing = ["allocation_generation", "exact_byte_footprint", "access_order", "input_value_binding"]
        plans[key] = dict(rank=key[0], node_id=key[1], recipe=kind,
                          collective_issues=sorted(set(issues)),
                          required_binding_evidence=sorted(set(issues + missing)),
                          forwarded_slots=forwarding, value_versions_bound=bound,
                          target_execution_complete=False,
                          completion="participant rendezvous" if bound else "explicit operation completion",
                          source_duration_used=False)
    return plans, barriers, matched
