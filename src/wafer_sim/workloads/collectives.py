"""Logical collective identity/volume, independent of target algorithms."""
from dataclasses import dataclass

from wafer_sim.workloads.spatial import identifier, natural


@dataclass(frozen=True)
class Slot:
    input_elements: int
    output_elements: int
    element_bytes: int
    dtype: str


@dataclass(frozen=True)
class Collective:
    id: str
    kind: str
    members: tuple[int, ...]  # communicator order, not sorted topology endpoints
    slots: tuple[Slot, ...]
    reduction: str | None
    root: int | None  # global logical rank
    provenance: str


def validate(collective):
    identifier(collective.id, "Collective")
    identifier(collective.provenance, "Collective provenance")
    members = collective.members
    if type(members) is not tuple or not members or len(members) != len(set(members)):
        raise ValueError("Explicit unique ordered participants required")
    for rank in members:
        natural(rank, "logical participant")
    if collective.kind not in {"allgather", "allreduce", "reduce_scatter", "broadcast", "barrier"}:
        raise ValueError("Unsupported collective")
    if type(collective.slots) is not tuple or bool(collective.slots) == (collective.kind == "barrier"):
        raise ValueError("Barrier has no payload; other collectives require slots")
    if collective.kind == "broadcast":
        if type(collective.root) is not int or collective.root not in members:
            raise ValueError("Broadcast root must be a participant")
    elif collective.root is not None:
        raise ValueError("Unexpected logical root")
    if collective.kind in {"allreduce", "reduce_scatter"}:
        if len(members) > 1 and collective.reduction != "sum":
            raise ValueError("Explicit supported reduction required")
    elif collective.reduction is not None:
        raise ValueError("Unexpected reduction")
    for slot in collective.slots:
        for value in (slot.input_elements, slot.output_elements, slot.element_bytes):
            natural(value, "collective size", positive=True)
        identifier(slot.dtype, "Collective dtype")
        i, o, n = slot.input_elements, slot.output_elements, len(members)
        expected = i*n if collective.kind == "allgather" else i
        if collective.kind == "reduce_scatter":
            if i % n:
                raise ValueError("Reduce-scatter extent not divisible by participants")
            expected = i//n
        if o != expected:
            raise ValueError("Collective volume and membership disagree")
    return collective


def from_match(match, calls):
    if not match["participant_and_volume_match"] or match["issues"]:
        raise ValueError("Only complete explicit participant matches can be bound")
    source = [calls[(ref["rank"], ref["node_id"])] for ref in match["calls"]]
    intent = source[0]["intent"]
    root = intent["root_local_rank"]
    members = tuple(match["members"])
    if root is not None and not 0 <= root < len(members):
        raise ValueError("Broadcast local root outside communicator")
    return validate(Collective(f"pg:{match['group']}/seq:{match['sequence']}", match["kind"], members,
        tuple(Slot(s["input_elements"], s["output_elements"], s["element_bytes"], s["dtype"]) for s in intent["slots"]),
        intent["reduction"], members[root] if root is not None else None,
        "Explicit Chakra parameter group/sequence and c10d operand roles; immutable value binding still required"))
