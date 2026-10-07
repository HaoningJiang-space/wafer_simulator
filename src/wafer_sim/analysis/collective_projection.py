"""Matched direct-root/tree evidence: work conservation and spatial projection."""
from collections import Counter, defaultdict

from wafer_sim.analysis.resource_balance import checked_run, check_current, assert_same, summarize_arm
from wafer_sim.analysis.spatial_traffic import project
from wafer_sim.io import read_json


def conservation(arm, binding):
    record = arm["record"]
    endpoints = record["worker_endpoints"]
    inverse = {e: r for r, e in enumerate(endpoints)}
    if len(inverse) != len(endpoints): raise ValueError("Study needs distinct physical endpoints")
    algorithm = record["execution_policy"]["collective_algorithm"]
    answer = {}
    for collective in record["collectives"]:
        op = collective["operation"]
        ranks = collective["participants"]
        n, size = len(ranks), collective["elements"]*collective["element_bytes"]
        expected_reduce = [(i, 0 if algorithm == "direct_exchange_rank_order_sum" else (i-1)//2)
                           for i in range(1, n)]
        expected_edges = Counter((a, b, size) for a, b in expected_reduce + [(b, a) for a, b in expected_reduce])
        observed = Counter((inverse[m["source"]], inverse[m["destination"]], m["bytes"])
                           for m in record["booksim"]["network_messages"] if m["token"].startswith(op + "/phase/"))
        assert_same(observed, expected_edges, "logical collective edges/" + op)
        plan = binding.plans[op]
        resources = defaultdict(lambda: Counter())
        adds = Counter()
        for phase in plan.phases:
            for demand in phase.demands:
                if phase.kind == "compute":
                    assert_same(demand.unit, "scalar_add", "reduction unit")
                    adds[demand.resource] += demand.amount
                resources[demand.resource][phase.kind] += demand.amount
        expected_adds = Counter()
        for _, parent in expected_reduce:
            expected_adds[f"compute-{endpoints[parent]}"] += collective["elements"]
        assert_same(adds, expected_adds, "distributed reduction work/" + op)
        for backend in ("booksim", "store_and_forward"):
            served = Counter()
            for service in record[backend]["services"]:
                if service["token"].startswith(op + "/phase/") and service["category"] == "compute":
                    served[service["resource"]] += service["amount"]
            assert_same(served, expected_adds, "served adds/" + backend + "/" + op)
        memory_bytes = sum(value for row in resources.values() for kind, value in row.items() if kind.startswith("memory"))
        partials = (n-2)//2 if algorithm == "binary_tree_sum" else 0
        assert_same(memory_bytes, (5*n-3+2*partials)*size, "memory service accounting/" + op)
        assert_same(sum(m["bytes"] for m in record["booksim"]["network_messages"] if m["token"].startswith(op + "/phase/")),
                    2*(n-1)*size, "payload conservation")
        answer[op] = dict(network_bytes=2*(n-1)*size, scalar_adds=sum(adds.values()),
            memory_service_bytes=memory_bytes, resources={k: dict(v) for k, v in resources.items()},
            logical_reduce_edges=expected_reduce,
            intermediate_partial_objects=partials,
            reserved_bytes=sum(a.size_bytes for a in plan.reservations))
    return answer


def analyze(direct_root, tree_root):
    direct, direct_receipt = checked_run(direct_root)
    tree, tree_receipt = checked_run(tree_root)
    registration = read_json(tree_root / "CONFIG.json")["balance"]
    expected = {(f"memory-{bw}", p) for bw in registration["memory_bytes_per_cycle"]
                for p in ("baseline", "ours_rotated")}
    assert_same(set(tree), expected, "registered tree arms")
    if not expected <= set(direct): raise ValueError("Missing accepted direct-root reference")
    a, b = read_json(direct_root / "STARTED.json"), read_json(tree_root / "STARTED.json")
    for key in ("native_binary_sha256", "online_binary_sha256", "online_source_sha256", "packages"):
        assert_same(a[key], b[key], "native/environment identity/" + key)
    rows, details = [], {}
    for key in sorted(expected):
        old, new = direct[key], tree[key]
        for field in ("logical_workload", "tensors", "operators", "collectives", "mapping", "worker_endpoints", "target", "timing"):
            assert_same(old["record"][field], new["record"][field], "algorithm control/" + field)
        assert_same(old["exported"], new["exported"], "same physical network")
        assert_same(old["config"]["workload"], new["config"]["workload"], "same workload/service config")
        ca, cb = dict(old["config"]["experiment"]), dict(new["config"]["experiment"])
        pa, pb = ca.pop("execution_policy"), cb.pop("execution_policy")
        assert_same(ca, cb, "all other execution controls")
        assert_same(pa, dict(collective_algorithm="direct_exchange_rank_order_sum", collective_completion="rank_local"), "direct policy")
        assert_same(pb, dict(collective_algorithm="binary_tree_sum", collective_completion="rank_local"), "tree policy")
        for label, arm in (("direct", old), ("tree", new)):
            binding = check_current(arm)
            work = conservation(arm, binding)
            row, detail = summarize_arm(arm)
            record = arm["record"]
            spatial = project(arm["exported"], record["booksim"]["network_messages"], record["worker_endpoints"])
            phases = {(p["operation"], p["phase"]): p for p in record["booksim"]["phases"]}
            critical = [dict(action=phases[s["operation"], s["phase"]]["action"],
                             operation=s["operation"], start=s["start"], finish=s["finish"], duration=s["duration"])
                        for s in arm["chain"]["segments"] if s["category"] == "network"]
            output = dict(algorithm=label, **row,
                collective_memory_bytes=sum(w["memory_service_bytes"] for w in work.values()),
                collective_adds=sum(w["scalar_adds"] for w in work.values()),
                network_payload_bytes=spatial["total_payload_bytes"], network_wire_bytes=spatial["total_wire_bytes"],
                endpoint_max_bytes=spatial["max_endpoint_payload_bytes"], endpoint_max_mean=spatial["endpoint_max_over_mean"],
                max_link_payload_bytes=spatial["max_directed_link_payload_bytes"],
                max_link_wire_bytes=spatial["max_directed_link_wire_bytes"],
                payload_byte_hops=spatial["payload_byte_hops"], wire_byte_hops=spatial["wire_byte_hops"],
                cut_payload_bytes=sum(x["payload_bytes"] for x in spatial["cut"]["directions"].values()),
                cut_wire_bytes=sum(x["wire_bytes"] for x in spatial["cut"]["directions"].values()),
                cut_bound_cycles=spatial["cut"]["wire_service_lower_bound_cycles"])
            rows.append(output)
            details[label + "/" + "/".join(key)] = dict(work=work, spatial=spatial,
                critical_transfers=critical, **detail)
    rows.sort(key=lambda r: (r["memory_bytes_per_cycle"], r["algorithm"], r["placement"]))
    return dict(rows=rows, runs=[direct_receipt, tree_receipt], current_audited_arms=len(rows),
                all_work_and_controls_checked=True, direct_simulations_reused=6, new_tree_simulations=6), details
