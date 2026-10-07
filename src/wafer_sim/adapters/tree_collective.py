"""Fixed communicator-order heap tree: bottom-up SUM, top-down broadcast.

Whole-tensor store/reload at each internal non-root node is explicit. Partial
values have separate storage and never publish as final AllReduce outputs.
No geometry-dependent construction, segmentation or rank-local entry policy.
"""
from types import MappingProxyType

from wafer_sim.adapters.collectives import Action, CollectiveBinding
from wafer_sim.adapters.spatial import validate_target
from wafer_sim.execution.plan import Allocation, Demand, Phase, Transfer
from wafer_sim.workloads.collectives import validate


def bind_tree(collective, target, placement, *, values=None):
    validate(collective)
    if collective.kind != "allreduce" or len(collective.members) < 2 or values is not None:
        raise ValueError("Tree supports multi-rank logical AllReduce; capture value binding is separate")
    memory, compute, attachments, component = validate_target(target)
    ranks = collective.members
    if set(placement) != set(ranks) or any(c not in compute for c in placement.values()):
        raise ValueError("Every tree participant needs one target compute binding")
    homes = {r: memory[compute[placement[r]].memory] for r in ranks}
    children = {r: tuple(ranks[j] for j in (2*i+1, 2*i+2) if j < len(ranks))
                for i, r in enumerate(ranks)}
    actions, inputs, outputs, requirements = {}, {}, {}, {}
    reserves = {r: [] for r in ranks}

    def action(name, phase, deps, participants, completion):
        if name in actions or any(d not in actions for d in deps):
            raise ValueError("Tree actions must have unique topologically ordered dependencies")
        actions[name] = Action(name, tuple(deps), frozenset(participants), frozenset(completion), phase)
        return name

    def port(name, rank, size, write=False, deps=()):
        home = homes[rank]
        return action(name, Phase("memory_write" if write else "memory_read", (
            Demand(home.write_port if write else home.read_port, "bytes", size),)), deps, (rank,), (rank,))

    def deliver(name, src, dst, size, dep, data):
        a, b = homes[src], homes[dst]
        if component[attachments[a.endpoint]] != component[attachments[b.endpoint]]:
            raise ValueError("Tree transfer crosses disconnected target components")
        if a.id != b.id:
            dep = action(name + "/network", Phase("transfer", transfer=Transfer(
                data, a.id, b.id, a.endpoint, b.endpoint, size)), (dep,), (src, dst), (src, dst))
        return port(name + "/write", dst, size, True, (dep,))

    def allocate(role, rank, slot, size, suffix=""):
        return Allocation((role, collective.id, str(rank), str(slot), suffix), homes[rank].id, size)

    for slot, tensor in enumerate(collective.slots):
        size = tensor.output_elements * tensor.element_bytes
        for rank in ranks:
            inputs[rank, slot] = allocate("collective_input", rank, slot, size)
            outputs[rank, slot] = allocate("collective_output", rank, slot, size)
            reserves[rank].append(outputs[rank, slot])
            for child in children[rank]:
                reserves[rank].append(allocate("collective_stage", rank, slot, size, str(child)))
            if children[rank] and rank != ranks[0]:
                reserves[rank].append(allocate("collective_partial", rank, slot, size))

        partial_read, partial_data = {}, {}
        # Read each initial local contribution once; siblings may enter together.
        local = {r: port(f"{slot}/local-read/{r}", r, size) for r in ranks}
        final = {}
        for rank in reversed(ranks):
            operands = [local[rank]]
            for child in children[rank]:
                label = f"{slot}/reduce/{child}->{rank}"
                written = deliver(label, child, rank, size, partial_read[child], partial_data[child])
                operands.append(port(label + "/read", rank, size, deps=(written,)))
            if children[rank]:
                unit = compute[placement[rank]]
                if "scalar_add" not in unit.work_units:
                    raise ValueError("Tree reduction requires local scalar-add service")
                reduced = action(f"{slot}/sum/{rank}", Phase("compute", (
                    Demand(unit.id, "scalar_add", len(children[rank])*tensor.output_elements),)),
                    operands, (rank,), (rank,))
                if rank == ranks[0]:
                    final[rank] = port(f"{slot}/result/{rank}", rank, size, True, (reduced,))
                else:
                    written = port(f"{slot}/partial/{rank}/write", rank, size, True, (reduced,))
                    partial_read[rank] = port(f"{slot}/partial/{rank}/read", rank, size, deps=(written,))
                    partial_data[rank] = f"{collective.id}/partial/{rank}/{slot}"
            else:
                partial_read[rank] = local[rank]
                partial_data[rank] = f"{collective.id}/input/{rank}/{slot}"
        # Parent writes its own final result before any child broadcast read.
        for rank in ranks:
            requirements[rank, slot] = frozenset({final[rank]})
            for child in children[rank]:
                label = f"{slot}/broadcast/{rank}->{child}"
                read = port(label + "/read", rank, size, deps=(final[rank],))
                final[child] = deliver(label, rank, child, size, read,
                                       f"{collective.id}/result/{rank}/{slot}")
    return CollectiveBinding(collective, MappingProxyType(memory), MappingProxyType(actions),
        MappingProxyType(inputs), MappingProxyType({r: tuple(a) for r, a in reserves.items()}),
        MappingProxyType(outputs), MappingProxyType(requirements), "binary_tree_sum")
