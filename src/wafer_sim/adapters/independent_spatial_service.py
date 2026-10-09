"""D0: endpoint/size component service, independent of concurrent messages.

The lookup is measured on empty physical networks, before application execution.
It is intentionally bounded to calibrated machines, endpoints and payloads.
Native C2C/IO continues as in U1; DRAM traffic never enters that shared network.
"""
from dataclasses import asdict
import heapq

from wafer_sim.adapters.memory_abstraction import contract as resource_contract
from wafer_sim.io import object_digest


def key(source, destination, size):
    if any(type(v) is not int for v in (source, destination, size)) or min(source, destination) < 0 or size <= 0:
        raise ValueError('Invalid isolated service key')
    return f'{source}:{destination}:{size}'


def machine_identity(compiled):
    return object_digest(asdict(compiled.physical))


def contract(compiled, table):
    identity = machine_identity(compiled)
    if table.get('schema') != 'isolated-spatial-service-v1' or not table.get('validated'):
        raise ValueError('Validated independent component table required')
    part = table['machines'].get(identity)
    if part is None:
        raise ValueError('Uncalibrated physical machine')
    return dict(model='D0', machine_sha256=identity, table_sha256=object_digest(table),
        binary_sha256=table['binary_sha256'], semantic_network_config=table['semantic_network_config'],
        topology_sha256=part['topology_sha256'], entries=part['entries'],
        resource_contract=resource_contract(compiled, 'U1'),
        communication='exact isolated component service by physical endpoints and payload; no DRAM sharing',
        prediction_inputs=['physical machine', 'message endpoints', 'payload bytes', 'own ready cycle'],
        scope=table['scope'])


class IndependentSpatialNetwork:
    backend_name = 'independent_spatial_service'
    policy_description = 'isolated DRAM service; live BookSim C2C/IO; native before D0 on ties'

    def __init__(self, native, spec):
        if spec['model'] != 'D0' or native.identity['binary_sha256'] != spec['binary_sha256']:
            raise ValueError('D0 component/native identity mismatch')
        self.native, self.spec = native, spec
        self.now = 0
        self.pending, self.messages, self.queue = {}, [], []
        self.banks = set(spec['resource_contract']['dram_regions'])

    def submit(self, token, transfer, cycle):
        if cycle != self.now or token in self.pending or any(m['token'] == token for m in self.messages):
            raise ValueError('Repeated transfer or mismatched network clock')
        k = key(transfer.source_endpoint, transfer.destination_endpoint, transfer.size_bytes)
        isolated = bool({transfer.source_memory, transfer.destination_memory} & self.banks)
        identity = len(self.pending)+len(self.messages)
        row = dict(id=identity, token=token, ready=cycle, bytes=transfer.size_bytes,
            source=transfer.source_endpoint, destination=transfer.destination_endpoint,
            data=transfer.data, source_memory=transfer.source_memory, destination_memory=transfer.destination_memory,
            engine='isolated' if isolated else 'booksim')
        if isolated:
            component = self.spec['entries'].get(k)
            if component is None:
                raise ValueError('Uncalibrated endpoint/payload: '+k)
            duration = component['duration_cycles']
            if type(duration) is not int or duration <= 0:
                raise ValueError('Invalid isolated component duration')
            row.update(component_key=k, component_sha256=object_digest(component))
            heapq.heappush(self.queue, (cycle+duration, identity, token))
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
        while self.queue and self.queue[0][0] == self.now:
            finish, _, token = heapq.heappop(self.queue)
            row = self.pending.pop(token); row['finish'] = finish
            self.messages.append(row); completed.append(token)
        return completed

    def evidence(self):
        return dict(native_network_messages=sorted(self.native.messages, key=lambda m:m['id']),
                    independent_spatial_contract=self.spec)

    def close(self):
        if self.pending:
            raise ValueError('Cannot close incomplete D0 network')
        return self.native.close()

    def abort(self):
        self.native.abort()
