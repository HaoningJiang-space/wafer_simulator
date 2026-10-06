"""Recover an observed critical chain without changing execution or its audit."""
import numpy as np
from scipy.sparse import coo_matrix


def parent_graph(instructions, dependencies, message_pairs):
    edges = np.concatenate((dependencies, message_pairs))
    kinds = np.concatenate((np.ones(len(dependencies), dtype="i1"),
                            np.full(len(message_pairs), 2, dtype="i1")))
    graph = coo_matrix((kinds, (edges[:, 1], edges[:, 0])),
                       shape=(instructions, instructions)).tocsr()
    if graph.nnz != len(edges):
        raise ValueError("Duplicate graph edges require an explicit relation representation")
    return graph


def recover(operations, events, parents, expected):
    """Match goal_completion.audit's terminal and predecessor tie rules exactly.

    This is one deterministic chain, not an enumeration of all tied critical
    paths. Message service remains observed duration, not router-level causality.
    """
    n = len(operations)
    start, finish = events["start_cycle"], events["finish_cycle"]
    current = int(finish.argmax())  # First ID among tied terminal completions.
    reverse, relations, seen = [], [], set()
    local = message = 0
    while True:
        if current in seen or not 0 <= current < n:
            raise ValueError("Invalid/cyclic observed critical chain")
        seen.add(current)
        reverse.append(current)
        service = int(finish[current]) - int(start[current])
        if service < 0:
            raise ValueError("Negative observed service")
        if operations["kind"][current] == 1:
            message += service
        else:
            local += service
        begin, end = parents.indptr[current:current + 2]
        logical = parents.indices[begin:end]
        candidates = logical.tolist()
        cpu = int(events["cpu_predecessor"][current])
        if cpu >= 0:
            if cpu >= n:
                raise ValueError("Invalid CPU predecessor")
            candidates.append(cpu)
        if not candidates:
            if start[current] != 0:
                raise ValueError("Unexplained nonzero root start")
            relations.append("root")
            break
        parent = max(candidates, key=lambda i: (int(finish[i]), i))
        if finish[parent] != start[current]:
            raise ValueError("Critical-chain timing does not close")
        reasons = []
        index = int(np.searchsorted(logical, parent))
        if index < len(logical) and logical[index] == parent:
            reasons.append({1: "requires", 2: "message_arrival"}[int(parents.data[begin + index])])
        if cpu == parent:
            reasons.append("cpu_resource")
        relations.append("+".join(reasons))
        current = parent
    actual = dict(application_cycles=int(finish.max()), critical_local_work_cycles=local,
                  critical_message_cycles=message, critical_chain_nodes=len(reverse))
    if local + message != actual["application_cycles"]:
        raise ValueError("Observed chain does not sum to application completion")
    for key, value in actual.items():
        if key in expected and expected[key] != value:
            raise ValueError(f"Recovered chain differs from existing audit: {key}")
    return dict(ids=np.array(reverse[::-1], dtype="i8"),
                predecessor_relations=relations[::-1], **actual)


def message_timings(events, ids):
    fields = ("ready_cycle", "start_cycle", "finish_cycle", "cpu_predecessor",
              "generated_cycle", "first_inject_cycle", "last_inject_cycle", "first_eject_cycle")
    result = {field: events[field][ids] for field in fields}
    result.update(cpu_wait=result["start_cycle"] - result["ready_cycle"],
                  injection_wait=result["first_inject_cycle"] - result["start_cycle"],
                  first_inject_to_complete=result["finish_cycle"] - result["first_inject_cycle"],
                  service=result["finish_cycle"] - result["start_cycle"],
                  ready_to_complete=result["finish_cycle"] - result["ready_cycle"])
    for key in ("cpu_wait", "injection_wait", "first_inject_to_complete", "service", "ready_to_complete"):
        if np.any(result[key] < 0):
            raise ValueError(f"Invalid message interval: {key}")
    if not np.array_equal(result["ready_to_complete"], result["cpu_wait"] +
                          result["injection_wait"] + result["first_inject_to_complete"]):
        raise ValueError("Message interval decomposition does not close")
    return result


def difference(operations, left_events, right_events, left_chain, right_chain):
    """Exact accounting across two different observed chains, not a counterfactual."""
    left = np.zeros(len(operations), dtype=bool)
    right = np.zeros(len(operations), dtype=bool)
    left[left_chain["ids"]] = True
    right[right_chain["ids"]] = True
    a = left_events["finish_cycle"] - left_events["start_cycle"]
    b = right_events["finish_cycle"] - right_events["start_cycle"]
    result = {}
    for kind, selected in (("message", operations["kind"] == 1), ("local", operations["kind"] != 1)):
        result[f"common_{kind}_delta"] = int((a[left & right & selected] - b[left & right & selected]).sum())
        result[f"baseline_only_{kind}"] = int(a[left & ~right & selected].sum())
        result[f"rotated_only_{kind}"] = int(b[right & ~left & selected].sum())
    accounted = sum(result[f"common_{k}_delta"] + result[f"baseline_only_{k}"] -
                    result[f"rotated_only_{k}"] for k in ("message", "local"))
    observed = left_chain["application_cycles"] - right_chain["application_cycles"]
    if accounted != observed:
        raise ValueError("Between-chain completion difference does not close")
    result.update(application_delta_cycles=observed, accounted_delta_cycles=accounted,
                  common_nodes=int((left & right).sum()), baseline_only_nodes=int((left & ~right).sum()),
                  rotated_only_nodes=int((right & ~left).sum()))
    return result, left, right
