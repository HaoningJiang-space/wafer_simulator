"""Shared finite storage reservations for execution frontends."""


class ReservationPool:
    def __init__(self, memory):
        self.memory = memory
        self.used = {m: 0 for m in memory}
        self.peak = self.used.copy()
        self.allocations = {}

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
            self.used[a.memory] += a.size_bytes
            self.peak[a.memory] = max(self.peak[a.memory], self.used[a.memory])
        return True

    def release(self, key):
        a = self.allocations.pop(key)
        self.used[a.memory] -= a.size_bytes
