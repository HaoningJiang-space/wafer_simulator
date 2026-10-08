"""Independent DRAM transfer costs alongside an unchanged live C2C/IO network."""
import heapq


class UniformMemoryNetwork:
    backend_name = 'memory_approximation'
    policy_description = 'independent one-HB DRAM cost; live BookSim C2C/IO; native before uniform on ties'

    def __init__(self, native, spec):
        if spec['model'] not in {'U0', 'U1'}:
            raise ValueError('Uniform network requires U0 or U1')
        self.native, self.spec = native, spec
        self.now = 0
        self.pending, self.messages, self.queue = {}, [], []
        self.banks = set(spec['dram_regions'])

    def submit(self, token, transfer, cycle):
        if cycle != self.now or token in self.pending or any(m['token'] == token for m in self.messages):
            raise ValueError('Repeated transfer or mismatched network clock')
        if type(transfer.size_bytes) is not int or transfer.size_bytes <= 0:
            raise ValueError('Positive payload required')
        uniform = bool({transfer.source_memory, transfer.destination_memory} & self.banks)
        identity = len(self.pending)+len(self.messages)
        row = dict(id=identity, token=token, ready=cycle, bytes=transfer.size_bytes,
            source=transfer.source_endpoint, destination=transfer.destination_endpoint,
            data=transfer.data, source_memory=transfer.source_memory, destination_memory=transfer.destination_memory,
            engine='uniform' if uniform else 'booksim')
        if uniform:
            width = self.spec['flit_bytes']
            finish = cycle+(transfer.size_bytes+width-1)//width+self.spec['uniform_startup_cycles']
            heapq.heappush(self.queue, (finish, identity, token))
        else:
            self.native.submit(token, transfer, cycle)
        self.pending[token] = row

    def advance(self, until):
        if type(until) is not int or until < self.now:
            raise ValueError('Invalid network boundary')
        boundary = min(until, self.queue[0][0]) if self.queue else until
        completed = self.native.advance(boundary)
        self.now = self.native.now
        actual = {m['token']: m for m in self.native.messages}
        for token in completed:
            row = self.pending.pop(token)
            row.update(finish=actual[token]['finish'], native_id=actual[token]['id'])
            self.messages.append(row)
        # Stable native-before-uniform ordering at equal cycle boundaries.
        while self.queue and self.queue[0][0] == self.now:
            finish, _, token = heapq.heappop(self.queue)
            row = self.pending.pop(token)
            row['finish'] = finish
            self.messages.append(row)
            completed.append(token)
        return completed

    def evidence(self):
        return dict(native_network_messages=sorted(self.native.messages, key=lambda m: m['id']),
                    uniform_memory_contract=self.spec)

    def close(self):
        if self.pending:
            raise ValueError('Cannot close incomplete mixed network')
        return self.native.close()

    def abort(self):
        self.native.abort()
