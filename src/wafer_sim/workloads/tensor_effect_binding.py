"""Apply supported call effects only after exact source bindings are supplied.

The frontend supplies allocation generations and touched byte spans. This
adapter never invents those from a tensor/storage ID or logical tensor size.
"""
from dataclasses import dataclass

from wafer_sim.workloads.tensor_versions import StorageKey


@dataclass(frozen=True)
class AccessBinding:
    storage: StorageKey
    spans: tuple[tuple[int, int], ...]


def apply_effect(state, effect, bindings, operation, provenance):
    """Return immutable input/output values, with no target time or work cost.

    Single-destination writes and metadata aliases are supported. Explicit
    allocation, order reconstruction and unsupported/partial mutations remain
    the frontend's responsibility. Reads are resolved before any write.
    """
    category = effect["category"]
    if category not in {"write", "alias"}:
        raise ValueError("Effect requires explicit frontend lowering")
    if effect["allocations"] or (category == "write" and len(effect["writes"]) != 1):
        raise ValueError("Only existing-storage single-destination writes supported")
    refs = {r["path"]: r for r in effect["inputs"] + effect["outputs"]}
    paths = set(effect["reads"] + effect["writes"])
    for alias in effect["aliases"]:
        paths.update([alias["output"], *alias["inputs"]])
    for path in paths:
        if path not in bindings:
            raise ValueError("Missing exact access binding")
        bound, ref = bindings[path], refs[path]
        if (bound.storage.device, bound.storage.source_id) != (ref["source_device"], ref["storage_id"]):
            raise ValueError("Binding disagrees with source storage")
        # Bounds/liveness validation must not require initialized values for
        # a pure view or an overwrite destination.
        state.check_access(bound.storage, bound.spans)
    if len({bindings[p].storage.rank for p in paths}) > 1:
        raise ValueError("One source call cannot cross rank namespaces")
    for alias in effect["aliases"]:
        if any(bindings[p].storage != bindings[alias["output"]].storage for p in alias["inputs"]):
            raise ValueError("Alias points to another allocation generation")
    reads = {p: state.read(bindings[p].storage, bindings[p].spans) for p in effect["reads"]}
    writes = {}
    for path in effect["writes"]:
        bound = bindings[path]
        writes[path] = state.write(bound.storage, bound.spans, operation, provenance)
    return dict(reads=reads, writes=writes, aliases=effect["aliases"], timing_evaluated=False)
