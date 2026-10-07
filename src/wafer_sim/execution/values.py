"""Resident immutable values and explicit consumer lifetimes on a shared pool."""
from dataclasses import dataclass


@dataclass
class ResidentValue:
    allocation: object
    producers: frozenset[str]
    remaining: set[str]
    retain: bool
    active: set[str]
    ready: bool = False
    published: bool = False


class ValueLifetime:
    def __init__(self, pool):
        self.pool = pool
        self.values = {}

    def declare(self, allocation, producers, consumers, *, retain=False):
        if allocation.key in self.values or type(retain) is not bool:
            raise ValueError("Value already declared or invalid retention")
        producers, consumers = tuple(producers), tuple(consumers)
        if (len(set(consumers)) != len(consumers) or
                any(not isinstance(x, str) or not x for x in producers + consumers)):
            raise ValueError("Explicit unique consumer identities required")
        self.values[allocation.key] = ResidentValue(allocation, frozenset(producers), set(consumers), retain, set())

    def publish(self, key, completed_producers):
        value = self.values[key]
        if (value.published or not value.producers <= set(completed_producers)
                or self.pool.allocations.get(key) != value.allocation):
            raise ValueError("Value needs resident storage and completed producers exactly once")
        value.ready = value.published = True
        self._release_unused(value)

    def can_acquire(self, key, consumer):
        value = self.values[key]
        if consumer not in value.remaining or consumer in value.active:
            raise ValueError("Unknown, completed or active value consumer")
        return value.ready and self.pool.allocations.get(key) == value.allocation

    def acquire(self, key, consumer):
        if not self.can_acquire(key, consumer):
            raise ValueError("Input version is not ready")
        self.values[key].active.add(consumer)
        self.pool.pin(key, consumer)

    def finish(self, key, consumer):
        value = self.values[key]
        if consumer not in value.active:
            raise ValueError("Value consumer did not begin or already completed")
        self.pool.unpin(key, consumer)
        value.active.remove(consumer)
        value.remaining.remove(consumer)
        self._release_unused(value)

    def _release_unused(self, value):
        if value.published and not value.remaining and not value.retain and value.ready:
            self.pool.release(value.allocation.key)
            value.ready = False
