"""Bind collective source ports to immutable byte versions, before execution.

Exact allocation generations, spans and access order are frontend inputs.
Creating a producer version here never makes its target data ready.
"""
from dataclasses import asdict, dataclass
from types import MappingProxyType

from wafer_sim.io import object_digest
from wafer_sim.workloads.call_regions import tensor_identity
from wafer_sim.workloads.collectives import from_match
from wafer_sim.workloads.spatial import identifier
from wafer_sim.workloads.tensor_versions import ReadSlice, StorageKey


@dataclass(frozen=True)
class TensorValue:
    storage: StorageKey
    slices: tuple[ReadSlice, ...]

    @property
    def key(self):
        return ("value", object_digest(asdict(self)))

    @property
    def size_bytes(self):
        return sum(s.stop - s.start for s in self.slices)

    @property
    def producers(self):
        return frozenset(s.version.producer for s in self.slices if s.version.producer is not None)


@dataclass(frozen=True)
class CollectiveValues:
    collective: object
    inputs: object
    outputs: object
    source_calls: tuple[tuple[int, int], ...]


def forwards_input(collective, operands):
    """Only a proved identity on the very same tensor argument can forward.

    An opaque singleton ReduceOp is not enough: PREMUL_SUM may scale its input.
    Equal storage IDs or equal byte counts do not establish identical views.
    """
    source, destination = operands["source"], operands["destination"]
    return (len(collective.members) == 1
            and (collective.kind == "broadcast" or
                 collective.kind == "allreduce" and collective.reduction == "sum")
            and source["path"] == destination["path"]
            and tensor_identity(source) == tensor_identity(destination))


def bind_values(state, match, calls, accesses, *, provenance):
    """Snapshot ALL input bytes before any collective output mutation.

Access keys are (rank, original CPU node, original argument path). Destination
aliasing an input is legal under immutable target versioning; two overlapping
destinations are rejected. No layout or generation is inferred from byte count.
"""
    identifier(provenance, "Collective value provenance")
    collective = from_match(match, calls)
    refs, destinations, inputs, forwarded = {}, {}, {}, set()
    for entry in match["calls"]:
        rank, node = entry["rank"], entry["node_id"]
        call = calls[(rank, node)]
        identity = call["identity"]
        if (identity is None or (identity["group"], identity["sequence"]) != (match["group"], match["sequence"])
                or identity["local_rank"] != collective.members.index(rank)
                or call["rank"] != rank or call["node_id"] != node):
            raise ValueError("Collective source identity differs from matched instance")
        for slot, operands in enumerate(call["intent"]["slots"]):
            if forwards_input(collective, operands):
                forwarded.add((rank, slot))
            for role in ("source", "destination"):
                ref = operands[role]
                key = rank, node, ref["path"]
                if key in refs and refs[key] != ref:
                    raise ValueError("One source port names conflicting tensor descriptors")
                refs[key] = ref
                if key not in accesses:
                    raise ValueError("Missing exact collective access binding")
                access = accesses[key]
                if (access.storage.rank, access.storage.device, access.storage.source_id) != (
                        rank, ref["source_device"], ref["storage_id"]):
                    raise ValueError("Collective access bound to another source storage")
                spans = state.check_access(access.storage, access.spans)
                # v1 requires a non-overlapping exact representation: packing
                # repeated/broadcast elements requires an explicit later rule.
                if sum(b-a for a,b in spans) != ref["num_elements"] * ref["element_bytes"]:
                    raise ValueError("Exact footprint differs from logical operand volume")
                if role == "source":
                    if collective.kind != "broadcast" or rank == collective.root:
                        inputs[(rank, slot)] = TensorValue(access.storage, state.read(access.storage, spans))
                else:
                    destinations[(rank, slot)] = (access.storage, spans)
    if set(accesses) != set(refs):
        raise ValueError("Unexpected source access bindings")
    occupied = {}
    for storage, spans in destinations.values():
        previous = occupied.setdefault(storage, [])
        if any(max(a,c) < min(b,d) for a,b in spans for c,d in previous):
            raise ValueError("Overlapping collective destinations need an explicit alias rule")
        previous.extend(spans)
    outputs = {}
    for (rank, slot), (storage, spans) in destinations.items():
        if (rank, slot) in forwarded:
            outputs[(rank, slot)] = inputs[(rank, slot)]
            continue
        producer = f"{collective.id}/output/{rank}/{slot}"
        state.write(storage, spans, producer, provenance)
        outputs[(rank, slot)] = TensorValue(storage, state.read(storage, spans))
    return CollectiveValues(collective, MappingProxyType(inputs), MappingProxyType(outputs),
                            tuple((c["rank"], c["node_id"]) for c in match["calls"]))
