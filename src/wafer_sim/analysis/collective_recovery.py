"""Join recovery decisions to accepted full source ports, preserving every call."""
from collections import Counter
import gzip
import json


def join_recovery(source, destination, rank, plans):
    expected = {node: plan for (r, node), plan in plans.items() if r == rank}
    seen, counts = set(), Counter()
    with gzip.open(source, "rt") as src, gzip.open(destination, "wt", compresslevel=1) as dst:
        for line in src:
            row = json.loads(line)
            node = row["call"]["node_id"]
            if row["rank"] != rank or node not in expected or node in seen:
                raise ValueError("Unexpected or duplicate accepted source call")
            seen.add(node)
            plan = expected[node]
            # Preserve original port record, including old evidence status.
            # The replacement decision is separately versioned and reviewable.
            dst.write(json.dumps(dict(source_ports=row, recovery=plan), sort_keys=True) + "\n")
            counts["calls"] += 1
            counts[plan["recipe"]] += 1
            counts["value_versions_bound_calls"] += plan["value_versions_bound"]
    if seen != set(expected):
        raise ValueError("Missing source calls in recovery join")
    # Read back every row and compare the entire original evidence, not counts.
    with gzip.open(source, "rt") as src, gzip.open(destination, "rt") as dst:
        for line in src:
            original, saved = json.loads(line), json.loads(next(dst))
            if (saved["source_ports"] != original or
                    saved["recovery"] != expected[original["call"]["node_id"]]):
                raise ValueError("Recovery output changed source ports or decision")
        if next(dst, None) is not None:
            raise ValueError("Extra recovery output")
    return dict(counts)
