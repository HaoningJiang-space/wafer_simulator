"""Collective completion after service, with the existing shared storage pool."""
from wafer_sim.execution.reservations import ReservationPool


def input_consumer(binding, rank):
    return f"{binding.collective.id}/input-consumer/{rank}"


def output_hold(binding):
    return f"{binding.collective.id}/output-hold"


class CollectiveState:
    def __init__(self, binding, pool=None, *, lifetime=None):
        self.binding = binding
        self.lifetime = lifetime
        if lifetime is not None:
            if pool is not None and pool is not lifetime.pool:
                raise ValueError("Collective and values must share the same storage pool")
            pool = lifetime.pool
        if (binding.values is None) != (lifetime is None):
            raise ValueError("Bound tensor versions and value lifetimes must be supplied together")
        self.pool = pool if pool is not None else ReservationPool(binding.memory)
        if self.pool.memory != binding.memory:
            raise ValueError("Collective and caller storage resources differ")
        self.entered, self.active, self.finished = set(), set(), set()
        self.released_staging = False
        self.published_outputs, self.consumed_inputs = set(), set()
        self.released_output_holds = False
        if lifetime is not None:
            for table, versions, is_input in ((binding.inputs, binding.values.inputs, True),
                                               (binding.outputs, binding.values.outputs, False)):
                for (rank, slot), allocation in table.items():
                    record = lifetime.values.get(allocation.key)
                    consumer = input_consumer(binding, rank) if is_input else output_hold(binding)
                    if (record is None or record.allocation != allocation or record.producers != versions[(rank,slot)].producers
                            or consumer not in record.remaining):
                        raise ValueError("Collective value allocation, producers or consumers not declared")

    def enter(self, rank, ready_input_keys=None):
        if rank not in self.binding.reservations or rank in self.entered:
            raise ValueError("Unknown or repeated collective participant")
        inputs = [a for (r, _), a in self.binding.inputs.items() if r == rank]
        if self.lifetime is not None:
            if not all(self.lifetime.can_acquire(a.key, input_consumer(self.binding, rank)) for a in inputs):
                return False
            ready_input_keys = {a.key for a in inputs}
        elif ready_input_keys is None:
            raise ValueError("Explicit input readiness required")
        if any(a.key not in ready_input_keys or self.pool.allocations.get(a.key) != a for a in inputs):
            raise ValueError("Collective input versions must already be resident and ready")
        if not self.pool.reserve(self.binding.reservations[rank]):
            return False
        if self.lifetime is not None:
            for key in {a.key for a in inputs}:
                self.lifetime.acquire(key, input_consumer(self.binding, rank))
        self.entered.add(rank)
        self._update_values()
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
        self._update_values()

    def _update_values(self):
        if self.lifetime is None:
            return
        for (rank, slot), allocation in self.binding.outputs.items():
            if allocation.key not in self.published_outputs and self.output_ready(rank, slot):
                value = self.binding.values.outputs[(rank, slot)]
                self.lifetime.publish(allocation.key, value.producers)
                self.lifetime.acquire(allocation.key, output_hold(self.binding))
                self.published_outputs.add(allocation.key)
        for rank in self.entered - self.consumed_inputs:
            if self.wait_satisfied(rank):
                for key in {a.key for (r,_),a in self.binding.inputs.items() if r == rank}:
                    self.lifetime.finish(key, input_consumer(self.binding, rank))
                self.consumed_inputs.add(rank)
        if self.all_complete() and not self.released_output_holds:
            for allocation in self.binding.outputs.values():
                self.lifetime.finish(allocation.key, output_hold(self.binding))
            self.released_output_holds = True

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
