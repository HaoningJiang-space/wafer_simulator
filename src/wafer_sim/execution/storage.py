"""Finite-region admission and lifetime semantics, without a timing engine.

The caller chooses admission order and reports completion of each service
phase. Reservations are atomic across regions. Data becomes visible only at
operation completion; copies are retained through all consumers' completion.
No eviction, spill, address-alias inference or hidden infinite storage.
"""
from dataclasses import dataclass

from wafer_sim.execution.plan import Allocation
from wafer_sim.execution.reservations import ReservationPool


@dataclass(frozen=True)
class Admission:
    admitted: bool
    missing_dependencies: tuple[str, ...]
    shortage_bytes: tuple[tuple[str, int], ...]


class StorageState:
    def __init__(self, binding):
        self.binding = binding
        self.pool = ReservationPool(binding.memory)
        self.used, self.peak, self.allocations = self.pool.used, self.pool.peak, self.pool.allocations
        self.available = set()
        self.completed = set()
        self.active = {}
        self.phase_started, self.phase_finished = {}, {}
        self.remaining = {d: set(cs) for d, cs in binding.graph.consumers.items()}
        initial = []
        for d in binding.graph.data.values():
            if d.producer is None and (self.remaining[d.id] or d.retain):
                initial.append(Allocation(("object", d.id), binding.homes[d.id], d.size_bytes))
                self.available.add(d.id)
        if self._shortages(initial):
            raise ValueError("Initial live data exceeds regional capacity")
        self._reserve(initial)

    def _shortages(self, reservations):
        return self.pool.shortages(reservations)

    def _reserve(self, reservations):
        if not self.pool.reserve(reservations):
            raise ValueError("Storage reservation exceeds capacity")

    def _release(self, key):
        self.pool.release(key)

    def admission(self, op):
        if op not in self.binding.plans:
            raise ValueError("Unknown operation")
        if op in self.completed or op in self.active:
            raise ValueError("Operation already admitted or completed")
        missing = tuple(sorted(self.binding.graph.predecessors[op] - self.completed))
        shortages = self._shortages(self.binding.plans[op].reservations)
        return Admission(not missing and not shortages, missing, shortages)

    def try_begin(self, op):
        decision = self.admission(op)
        if not decision.admitted:
            return decision
        if any(d not in self.available for d in self.binding.graph.operations[op].inputs):
            raise ValueError("Prerequisites complete but required data unavailable")
        self._reserve(self.binding.plans[op].reservations)
        self.active[op] = 0
        self.phase_started[op], self.phase_finished[op] = set(), set()
        return decision

    def ready_phases(self, op):
        if op not in self.active:
            raise ValueError("Operation has not been admitted")
        plan = self.binding.plans[op]
        return tuple(i for i in range(len(plan.phases))
                     if i not in self.phase_started[op] | self.phase_finished[op]
                     and set(plan.predecessors(i)) <= self.phase_finished[op])

    def begin_phase(self, op, index):
        if index not in self.ready_phases(op):
            raise ValueError("Phase lacks completed action prerequisites")
        self.phase_started[op].add(index)

    def next_phase(self, op):
        if op not in self.active:
            raise ValueError("Operation has not been admitted")
        if self.binding.plans[op].dependencies is not None:
            raise ValueError("Concurrent actions require ready_phases")
        return self.binding.plans[op].phases[self.active[op]]

    def complete_phase(self, op, index):
        if op not in self.active or type(index) is not int:
            raise ValueError("Out-of-order, duplicate or unadmitted phase completion")
        plan = self.binding.plans[op]
        if ((plan.dependencies is None and index != self.active[op]) or
                (plan.dependencies is not None and index not in self.phase_started[op]) or
                index in self.phase_finished[op]):
            raise ValueError("Out-of-order, duplicate or unadmitted phase completion")
        self.phase_finished[op].add(index)
        self.phase_started[op].discard(index)
        self.active[op] += 1
        if self.active[op] != len(self.binding.plans[op].phases):
            return
        operation = self.binding.graph.operations[op]
        del self.active[op]
        del self.phase_started[op], self.phase_finished[op]
        self.completed.add(op)
        self.available.update(operation.outputs)
        for d in operation.inputs:
            self.remaining[d].remove(op)
        for d in operation.inputs + operation.outputs:
            if not self.remaining[d] and not self.binding.graph.data[d].retain:
                self._release(("object", d))
                self.available.remove(d)
        for a in self.binding.plans[op].reservations:
            if a.key[0] != "object":
                self._release(a.key)

    def snapshot(self):
        return dict(used_bytes=self.used.copy(), peak_bytes=self.peak.copy(),
            available_data=sorted(self.available), completed=sorted(self.completed),
            active_phases=self.active.copy(),
            all_operations_completed=len(self.completed) == len(self.binding.plans),
            timing_evaluated=False)
