"""Finite-region admission and lifetime semantics, without a timing engine.

The caller chooses admission order and reports completion of each service
phase. Reservations are atomic across regions. Data becomes visible only at
operation completion; copies are retained through all consumers' completion.
No eviction, spill, address-alias inference or hidden infinite storage.
"""
from dataclasses import dataclass

from wafer_sim.execution.plan import Allocation


@dataclass(frozen=True)
class Admission:
    admitted: bool
    missing_dependencies: tuple[str, ...]
    shortage_bytes: tuple[tuple[str, int], ...]


class StorageState:
    def __init__(self, binding):
        self.binding = binding
        self.used = {m: 0 for m in binding.memory}
        self.peak = self.used.copy()
        self.allocations = {}
        self.available = set()
        self.completed = set()
        self.active = {}
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
        needed = dict.fromkeys(self.used, 0)
        for a in reservations:
            needed[a.memory] += a.size_bytes
        return tuple((m, self.used[m] + size - self.binding.memory[m].capacity_bytes)
                     for m, size in sorted(needed.items())
                     if self.used[m] + size > self.binding.memory[m].capacity_bytes)

    def _reserve(self, reservations):
        for a in reservations:
            if a.key in self.allocations:
                raise ValueError("Storage identity allocated twice")
            self.allocations[a.key] = a
            self.used[a.memory] += a.size_bytes
            self.peak[a.memory] = max(self.peak[a.memory], self.used[a.memory])

    def _release(self, key):
        a = self.allocations.pop(key)
        self.used[a.memory] -= a.size_bytes

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
        return decision

    def next_phase(self, op):
        if op not in self.active:
            raise ValueError("Operation has not been admitted")
        return self.binding.plans[op].phases[self.active[op]]

    def complete_phase(self, op, index):
        if op not in self.active or type(index) is not int or index != self.active[op]:
            raise ValueError("Out-of-order, duplicate or unadmitted phase completion")
        self.active[op] += 1
        if self.active[op] != len(self.binding.plans[op].phases):
            return
        operation = self.binding.graph.operations[op]
        del self.active[op]
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
