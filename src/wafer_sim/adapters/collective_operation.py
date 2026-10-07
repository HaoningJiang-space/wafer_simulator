"""Embed existing collective actions into the spatial operation/lifetime model.

All rank inputs are ready at atomic admission. Each output has explicit final
write requirements; retirement still waits for every action. The selected
target algorithm is an execution policy, not part of the logical AllReduce.
"""
from dataclasses import replace

from wafer_sim.adapters.collectives import bind_collective
from wafer_sim.execution.plan import Allocation, OperationPlan

def bind_operation(op, target, homes, root_compute, execution_policy):
    collective = op.collective
    rank_inputs = dict(zip(collective.members, op.inputs))
    rank_outputs = dict(zip(collective.members, op.outputs))
    assigned = {}
    for rank in collective.members:
        home = homes[rank_inputs[rank]]
        if homes[rank_outputs[rank]] != home:
            raise ValueError("Collective participant input/output must have the same home")
        candidates = [c.id for c in target.compute if c.memory == home]
        if len(candidates) != 1:
            raise ValueError("Collective participant needs one explicit compute resource at its home")
        assigned[rank] = candidates[0]
    if assigned[collective.members[0]] != root_compute:
        raise ValueError("Collective operation compute must match the declared first-rank root")
    binding = bind_collective(collective, target, assigned, policy=execution_policy.collective_algorithm)
    names = tuple(binding.actions)
    indices = {name: i for i, name in enumerate(names)}
    identities = {f"{op.id}/input/{r}/0": d for r, d in rank_inputs.items()}
    identities.update({f"{op.id}/result/{r}/0": d for r, d in rank_outputs.items()})
    phases = tuple(replace(a.phase, transfer=replace(a.phase.transfer, data=identities[a.phase.transfer.data]))
                   if a.phase.transfer else a.phase for a in binding.actions.values())
    outputs = {a.key: Allocation(("object", rank_outputs[r]), a.memory, a.size_bytes)
               for (r, _), a in binding.outputs.items()}
    reservations = tuple(outputs.get(a.key, a) for allocations in binding.reservations.values() for a in allocations)
    return OperationPlan(reservations, phases,
        tuple(tuple(indices[d] for d in a.dependencies) for a in binding.actions.values()),
        names, execution_policy.collective_algorithm,
        tuple((rank_outputs[r], tuple(sorted(indices[d] for d in binding.output_requirements[r, 0]))
               if execution_policy.collective_completion == "rank_local" else tuple(range(len(names))))
              for r in collective.members))
