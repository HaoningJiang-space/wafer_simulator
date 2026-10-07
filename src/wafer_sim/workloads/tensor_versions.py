"""Exact byte-region versions for explicitly ordered, supported accesses.

This layer does not infer allocation epochs, tensor strides, initial values or
an execution order from source IDs. A frontend must provide those facts. Views
reference existing storage; writes create new values only for affected bytes.
It is a workload provenance model, not target memory allocation or timing.
"""
from dataclasses import dataclass


def intervals(spans):
    result = []
    for start, stop in sorted(spans):
        if type(start) is not int or type(stop) is not int or not 0 <= start <= stop:
            raise ValueError("Invalid byte interval")
        if start == stop:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(stop, result[-1][1]))
        else:
            result.append((start, stop))
    return tuple(result)


def strided_footprint(shape, strides, element_bytes, offset_elements=0, *, max_spans=65536):
    """Exact touched bytes, including broadcast/transpose and holes.

    Missing strides cannot be replaced by a contiguous assumption. Large
    irregular views exceeding the exact representation limit are rejected.
    """
    if (strides is None or len(shape) != len(strides) or
            any(type(x) is not int or x < 0 for x in (*shape, *strides, offset_elements)) or
            type(element_bytes) is not int or element_bytes <= 0 or
            type(max_spans) is not int or max_spans <= 0):
        raise ValueError("Explicit nonnegative strides, shape and element size required")
    if 0 in shape:
        return ()
    spans = ((0, element_bytes),)
    for stride, count in sorted(zip(strides, shape)):
        step = stride * element_bytes
        if count == 1 or step == 0:
            continue
        if len(spans) == 1 and step <= spans[0][1] - spans[0][0]:
            spans = ((spans[0][0], spans[0][1] + step * (count - 1)),)
            continue
        if len(spans) * count > max_spans:
            raise ValueError("Exact strided footprint exceeds span limit")
        spans = intervals((a + i * step, b + i * step)
                          for i in range(count) for a, b in spans)
    offset = offset_elements * element_bytes
    return tuple((a + offset, b + offset) for a, b in spans)


@dataclass(frozen=True)
class StorageKey:
    rank: int
    device: str
    source_id: int
    generation: int


@dataclass(frozen=True)
class ValueVersion:
    id: int
    producer: str | None  # None only for explicitly declared initial data
    provenance: str


@dataclass(frozen=True)
class ReadSlice:
    start: int
    stop: int
    version: ValueVersion


class ByteVersions:
    """Finite storage generations and immutable value provenance.

    Explicit new allocations invalidate old source handles even when addresses
    and tensor IDs are reused. Unknown mutations invalidate provenance. Neither
    allocation nor an unseen read silently creates initialized input data.
    """
    def __init__(self):
        self._live = {}
        self._generations = {}
        self._segments = {}
        self._sizes = {}
        self._serial = 0

    def _value(self, producer, provenance):
        if not isinstance(provenance, str) or not provenance:
            raise ValueError("Value provenance required")
        if producer is not None and (not isinstance(producer, str) or not producer):
            raise ValueError("Producer identity required")
        self._serial += 1
        return ValueVersion(self._serial, producer, provenance)

    def allocate(self, rank, device, source_id, size_bytes, *, initial=None):
        if (type(rank) is not int or rank < 0 or not isinstance(device, str) or not device or
                type(source_id) is not int or source_id <= 0 or
                type(size_bytes) is not int or size_bytes < 0):
            raise ValueError("Invalid explicit storage allocation")
        value = self._value(None, initial) if initial is not None else None
        identity = rank, device, source_id
        generation = self._generations.get(identity, 0) + 1
        self._generations[identity] = generation
        key = StorageKey(*identity, generation)
        old = self._live.get(identity)
        if old is not None:
            self._segments.pop(old)
            self._sizes.pop(old)
        self._live[identity] = key
        self._sizes[key] = size_bytes
        self._segments[key] = [(0, size_bytes, value)] if size_bytes else []
        return key

    def _checked(self, key, spans):
        if key not in self._sizes or self._live.get((key.rank, key.device, key.source_id)) != key:
            raise ValueError("Missing or stale allocation generation")
        spans = intervals(spans)
        if spans and spans[-1][1] > self._sizes[key]:
            raise ValueError("Access exceeds storage capacity")
        return spans

    def read(self, key, spans):
        result = []
        for start, stop in self._checked(key, spans):
            for left, right, version in self._segments[key]:
                a, b = max(left, start), min(right, stop)
                if a < b:
                    if version is None:
                        raise ValueError("Read has uninitialized or unresolved bytes")
                    result.append(ReadSlice(a, b, version))
        return tuple(result)

    def check_access(self, key, spans):
        """Check liveness and capacity without reading uninitialized contents."""
        return self._checked(key, spans)

    def _replace(self, key, spans, value):
        segments = self._segments[key]
        for start, stop in spans:
            updated = []
            for left, right, old in segments:
                if right <= start or stop <= left:
                    updated.append((left, right, old))
                    continue
                if left < start:
                    updated.append((left, start, old))
                updated.append((max(left, start), min(right, stop), value))
                if stop < right:
                    updated.append((stop, right, old))
            segments = []
            for left, right, version in updated:
                if segments and segments[-1][1] == left and segments[-1][2] == version:
                    segments[-1] = (segments[-1][0], right, version)
                else:
                    segments.append((left, right, version))
        self._segments[key] = segments

    def write(self, key, spans, producer, provenance):
        spans = self._checked(key, spans)  # validate every span before mutation
        if producer is None:
            raise ValueError("A write requires a producer")
        value = self._value(producer, provenance)
        self._replace(key, spans, value)
        return value

    def invalidate(self, key, spans):
        """An unresolved effect must not leave a previous producer looking valid."""
        spans = self._checked(key, spans)
        self._replace(key, spans, None)
