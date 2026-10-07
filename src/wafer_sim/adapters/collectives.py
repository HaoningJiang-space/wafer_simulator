"""Explicit direct collective policy -> memory, network and reduction demands.

Whole immutable input/output versions and separate receive staging are assumed.
This is an explicit target algorithm, not a reproduction of NCCL ring/tree
choices. It binds resource demands without calibrated service times.
"""
from dataclasses import dataclass
from types import MappingProxyType

from wafer_sim.adapters.spatial import validate_target
from wafer_sim.execution.plan import Allocation, Demand, Phase, Transfer
from wafer_sim.workloads.collectives import validate


@dataclass(frozen=True)
class Action:
    id: str
    dependencies: tuple[str, ...]
    participants: frozenset[int]
    phase: Phase


@dataclass(frozen=True)
class CollectiveBinding:
    collective: object
    memory: object
    actions: object
    inputs: object
    reservations: object
    outputs: object
    output_requirements: object
    policy: str


def bind_collective(collective, target, placement, *, policy):
    validate(collective)
    if policy != "direct_exchange_rank_order_sum":
        raise ValueError("An explicit supported target collective policy is required")
    memory, compute, attachments, component = validate_target(target)
    ranks = collective.members
    if set(placement) != set(ranks) or any(c not in compute for c in placement.values()):
        raise ValueError("Every collective participant needs exactly one target compute binding")
    homes = {r: memory[compute[placement[r]].memory] for r in ranks}
    actions, inputs, reserves, outputs, requirements = {}, {}, {r: [] for r in ranks}, {}, {}

    def allocation(role, rank, slot, size, suffix=""):
        return Allocation((role, collective.id, str(rank), str(slot), suffix), homes[rank].id, size)

    def action(label, phase, deps=(), participants=()):
        if label in actions:
            raise ValueError("Repeated collective action")
        actions[label] = Action(label, tuple(deps), frozenset(participants), phase)
        return label

    def port(label, rank, write, amount, deps=(), participants=()):
        m = homes[rank]
        return action(label, Phase("memory_write" if write else "memory_read",
            (Demand(m.write_port if write else m.read_port, "bytes", amount),)), deps, {rank, *participants})

    def deliver(label, src, dst, size, dependency, data):
        a, b = homes[src], homes[dst]
        if component[attachments[a.endpoint]] != component[attachments[b.endpoint]]:
            raise ValueError("Collective requires unreachable target data movement")
        dep = dependency
        if a.id != b.id:
            dep = action(label + "/network", Phase("transfer", transfer=Transfer(data, a.id, b.id,
                a.endpoint, b.endpoint, size)), (dependency,), (src, dst))
        return port(label + "/write", dst, True, size, (dep,), (src,))

    for slot_index, slot in enumerate(collective.slots):
        for rank in ranks:
            key = (rank, slot_index)
            inputs[key] = allocation("collective_input", rank, slot_index, slot.input_elements*slot.element_bytes)
            outputs[key] = allocation("collective_output", rank, slot_index, slot.output_elements*slot.element_bytes)
            reserves[rank].append(outputs[key])
        if collective.kind in {"allgather", "broadcast"}:
            sources = ranks if collective.kind == "allgather" else (collective.root,)
            written = {r: [] for r in ranks}
            size = slot.input_elements*slot.element_bytes
            for src in sources:
                read = port(f"{slot_index}/read/{src}", src, False, size)
                for dst in ranks:
                    written[dst].append(deliver(f"{slot_index}/{src}->{dst}", src, dst, size, read,
                                               f"{collective.id}/input/{src}/{slot_index}"))
            for rank in ranks:
                requirements[(rank, slot_index)] = frozenset(written[rank])
        elif collective.kind in {"allreduce", "reduce_scatter"}:
            destinations = ranks if collective.kind == "reduce_scatter" else (ranks[0],)
            elements = slot.output_elements
            size = elements*slot.element_bytes
            for dst in destinations:
                received = []
                for src in ranks:
                    # For reduce-scatter, dst's communicator position selects
                    # its input chunk. Each source chunk is read once.
                    label = f"{slot_index}/chunk/{src}->{dst}"
                    read = port(label + "/read", src, False, size)
                    if src == dst:
                        received.append(read)
                    else:
                        reserves[dst].append(allocation("collective_stage", dst, slot_index, size, str(src)))
                        written = deliver(label, src, dst, size, read, f"{collective.id}/chunk/{src}/{dst}/{slot_index}")
                        received.append(port(label + "/reduce-read", dst, False, size, (written,), (src,)))
                deps = tuple(received)
                if len(ranks) > 1:
                    c = compute[placement[dst]]
                    if "scalar_add" not in c.work_units:
                        raise ValueError("Target lacks explicit scalar-add service for reduction")
                    reduced = action(f"{slot_index}/sum/{dst}", Phase("compute", (
                        Demand(c.id, "scalar_add", (len(ranks)-1)*elements),)), deps, ranks)
                    deps = (reduced,)
                final = port(f"{slot_index}/result/{dst}", dst, True, size, deps, ranks)
                requirements[(dst, slot_index)] = frozenset({final})
                if collective.kind == "allreduce":
                    # Root result must be read after its final write, before broadcast.
                    for rank in ranks:
                        if rank == dst:
                            continue
                        read = port(f"{slot_index}/result-read/{rank}", dst, False, size, (final,), ranks)
                        written = deliver(f"{slot_index}/broadcast/{rank}", dst, rank, size, read,
                                          f"{collective.id}/result/{slot_index}")
                        requirements[(rank, slot_index)] = frozenset({written})
    return CollectiveBinding(collective, MappingProxyType(memory), MappingProxyType(actions),
        MappingProxyType(inputs), MappingProxyType({r: tuple(a) for r, a in reserves.items()}),
        MappingProxyType(outputs), MappingProxyType(requirements), policy)
