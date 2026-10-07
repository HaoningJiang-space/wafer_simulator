"""Shared finite storage reservations for execution frontends."""


class ReservationPool:
    def __init__(self, memory):
        self.memory = memory
        self.used = {m: 0 for m in memory}
        self.peak = self.used.copy()
        self.allocations = {}
        self.pins = {}

    def shortages(self, reservations):
        needed, keys = dict.fromkeys(self.used, 0), set()
        for a in reservations:
            if (a.memory not in needed or type(a.size_bytes) is not int or a.size_bytes <= 0
                    or a.key in keys or a.key in self.allocations):
                raise ValueError("Invalid or repeated storage reservation")
            keys.add(a.key)
            needed[a.memory] += a.size_bytes
        return tuple((m, self.used[m] + size - self.memory[m].capacity_bytes)
                     for m, size in sorted(needed.items())
                     if self.used[m] + size > self.memory[m].capacity_bytes)

    def reserve(self, reservations):
        reservations = tuple(reservations)
        if self.shortages(reservations):
            return False
        for a in reservations:
            self.allocations[a.key] = a
            self.pins[a.key] = set()
            self.used[a.memory] += a.size_bytes
            self.peak[a.memory] = max(self.peak[a.memory], self.used[a.memory])
        return True

    def release(self, key):
        if self.pins[key]:
            raise ValueError("Cannot release storage with active value consumers")
        a = self.allocations.pop(key)
        del self.pins[key]
        self.used[a.memory] -= a.size_bytes

    def pin(self, key, consumer):
        if key not in self.allocations or consumer in self.pins[key]:
            raise ValueError("Missing allocation or repeated lifetime pin")
        self.pins[key].add(consumer)

    def unpin(self, key, consumer):
        if consumer not in self.pins[key]:
            raise ValueError("Missing lifetime pin")
        self.pins[key].remove(consumer)
