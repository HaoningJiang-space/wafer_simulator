"""Homogeneous single-message storage, only for the bounded R3 runner.

Ordinary initialize() keeps its accepted eager source queues and metadata.
These containers compress labels, not physical injection or service rules.
"""
class SourceRange:
    def __init__(self):
        self.start = self.stop = 0

    def __len__(self):
        return self.stop-self.start

    def __bool__(self):
        return self.start < self.stop

    def __iter__(self):
        return iter(range(self.start, self.stop))

    def reset(self, start, length):
        self.start, self.stop = start, start+length

    def popleft(self):
        if not self:
            raise IndexError('Empty source range')
        first = self.start
        self.start += 1
        return first

    def skip(self, amount):
        if type(amount) is not int or not 0 <= amount < len(self):
            raise ValueError('Source tail crossed')
        self.start += amount


class LazyPackets:
    def __init__(self):
        self.data = {}
        self.total = 0
        self.generated = None

    def register(self, message, start, now):
        if message['id'] != 0 or start != 0 or self.generated is not None:
            raise ValueError('Outside homogeneous single generation contract')
        self.total, self.generated = message['flits'], now

    def peek(self, flit):
        """Validation can inspect the source suffix without materializing it."""
        if type(flit) is not int or not 0 <= flit < self.total:
            raise ValueError('Unknown generated flit')
        if flit in self.data:
            return self.data[flit]
        return dict(id=flit, message=0, source=0, destination=3, generated=self.generated,
                    router_path=[], link_arrivals=[])

    def __getitem__(self, flit):
        if flit not in self.data:
            self.data[flit] = self.peek(flit)
        return self.data[flit]

    def retire(self, flit):
        del self.data[flit]

    def items(self):
        return self.data.items()
