"""Collective completion after service, with the existing shared storage pool."""
from wafer_sim.execution.reservations import ReservationPool


class CollectiveState:
    def __init__(self, binding, pool=None):
        self.binding = binding
        self.pool = pool if pool is not None else ReservationPool(binding.memory)
        if self.pool.memory != binding.memory:
            raise ValueError("Collective and caller storage resources differ")
        self.entered, self.active, self.finished = set(), set(), set()
        self.released_staging = False

    def enter(self, rank, ready_input_keys):
        if rank not in self.binding.reservations or rank in self.entered:
            raise ValueError("Unknown or repeated collective participant")
        inputs = [a for (r, _), a in self.binding.inputs.items() if r == rank]
        if any(a.key not in ready_input_keys or self.pool.allocations.get(a.key) != a for a in inputs):
            raise ValueError("Collective input versions must already be resident and ready")
        if not self.pool.reserve(self.binding.reservations[rank]):
            return False
        self.entered.add(rank)
        return True

    def ready_actions(self):
        return tuple(a.id for a in self.binding.actions.values() if a.id not in self.active | self.finished
                     and a.participants <= self.entered and set(a.dependencies) <= self.finished)

    def begin(self, action):
        if action not in self.ready_actions():
            raise ValueError("Collective action lacks entry/dependency prerequisites")
        self.active.add(action)

    def complete(self, action):
        if action not in self.active:
            raise ValueError("Unstarted or already completed collective action")
        self.active.remove(action)
        self.finished.add(action)
        # The backend calls this only after the whole memory/transfer/compute
        # service, not after flit injection or source CPU return.
        if self.all_complete() and not self.released_staging:
            for allocations in self.binding.reservations.values():
                for a in allocations:
                    if a.key[0] == "collective_stage":
                        self.pool.release(a.key)
            self.released_staging = True

    def output_ready(self, rank, slot):
        if (rank, slot) not in self.binding.output_requirements:
            raise ValueError("Unknown collective output")
        return rank in self.entered and self.binding.output_requirements[(rank, slot)] <= self.finished

    def all_complete(self):
        return self.entered == set(self.binding.collective.members) and len(self.finished) == len(self.binding.actions)

    def wait_satisfied(self, rank):
        if rank not in self.binding.collective.members:
            raise ValueError("Unknown waiter")
        if self.binding.collective.kind == "barrier":
            return self.entered == set(self.binding.collective.members)
        local = {a.id for a in self.binding.actions.values() if rank in a.completion_ranks}
        return (rank in self.entered and local <= self.finished and all(
            self.output_ready(r, slot) for r, slot in self.binding.outputs if r == rank))
