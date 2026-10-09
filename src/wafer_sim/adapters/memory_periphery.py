"""Controller-shared attachment and bounded DMA lowering of the same work.

No service rate is inferred or changed. The old whole-object adapter is reused
for admission, transactions, C2C and ordinary operation phases.
"""
from dataclasses import dataclass, replace
from types import MappingProxyType

from wafer_sim.architecture.memory_periphery import NetworkInterface, PeripheryTarget
from wafer_sim.architecture.spatial import Network
from wafer_sim.architecture.timing import Endpoint, Service
from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine, CONTROL_BYTES
from wafer_sim.adapters.spatial import validate_target
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.execution.plan import Demand, Phase
from wafer_sim.workloads.spatial import natural


@dataclass(frozen=True)
class TransactionPolicy:
    kind: str = 'whole'
    chunk_bytes: int = 4096
    window_chunks: int = 4

    def __post_init__(self):
        if self.kind not in {'whole', 'pipeline'}:
            raise ValueError('Unknown periphery transaction policy')
        natural(self.chunk_bytes, 'DMA chunk bytes', positive=True)
        natural(self.window_chunks, 'DMA window chunks', positive=True)


def compile_periphery(machine):
    """One endpoint per controller; SRAM retains its own interface."""
    old = compile_machine(machine)
    groups = {}
    for store in machine.stores:
        interface = (store.controller if store.kind != 'sram' else store.id) + '/nic'
        groups.setdefault(interface, []).append(store)
    interfaces = tuple(NetworkInterface(name, i, tuple(s.id for s in members), machine.provenance)
                       for i, (name, members) in enumerate(groups.items()))
    endpoints = {s: interface.endpoint for interface in interfaces for s in interface.memory_regions}
    stores = {s.id: s for s in machine.stores}
    attachments = []
    for interface in interfaces:
        tiles = {stores[s].tile for s in interface.memory_regions}
        if len(tiles) != 1:
            raise ValueError('A controller interface must attach at one physical tile')
        attachments.append((interface.endpoint, old.router_ids[next(iter(tiles))]))
    network = Network(tuple(attachments), old.target.network.router_links, machine.provenance)
    target = PeripheryTarget(tuple(replace(m, endpoint=endpoints[m.id]) for m in old.target.memory),
                             old.target.compute, network, interfaces)
    validate_target(target)
    eps = tuple(Endpoint(i.endpoint,
        Service(f'inject/{i.endpoint}', 'bytes', machine.flit_bytes,
                latency_cycles=machine.access_latency_cycles),
        Service(f'eject/{i.endpoint}', 'bytes', machine.flit_bytes,
                latency_cycles=machine.access_latency_cycles + machine.router_latency_cycles))
        for i in interfaces)
    buffers = tuple(replace(m, endpoint=endpoints[next(s.id for s in machine.stores
                    if s.controller is not None and s.controller + '/buffer' == m.id)]) for m in old.controller_buffers)
    return replace(old, target=target, endpoints=endpoints, controller_buffers=buffers,
                   timing=replace(old.timing, endpoints=eps))


def bind_periphery(workload, compiled, placement, policy):
    """Keep reservations/lifetimes and operand order; pipeline each DMA only."""
    base, transactions = bind_machine(workload, compiled, placement)
    if policy.kind == 'whole':
        return base, transactions
    plans, ledger = {}, []
    for op, plan in base.plans.items():
        movements = {t['first_phase']: t for t in transactions if t['operation'] == op}
        phases, dependencies, actions = [], [], []
        frontier = ()

        def push(phase, deps, label):
            index = len(phases)
            phases.append(phase)
            dependencies.append(tuple(dict.fromkeys(deps)))
            actions.append(f'{index}:{label}')
            return index

        def bytes_phase(kind, resource, amount, deps, label):
            return push(Phase(kind, (Demand(resource, 'bytes', amount),)), deps, label)

        index = 0
        while index < len(plan.phases):
            tx = movements.get(index)
            if tx is None or tx['kind'] == 'c2c':
                start = len(phases)
                end = tx['last_phase'] + 1 if tx is not None else index + 1
                while index < end:
                    frontier = (push(plan.phases[index], frontier, 'ordinary'),)
                    index += 1
                if tx is not None:
                    row = dict(tx, first_phase=start, last_phase=frontier[0],
                               payload_phase=start + 1)
                    ledger.append(row)
                continue
            old = plan.phases
            transfer = old[tx['payload_phase']].transfer
            ctrl = tx['controller']
            start = len(phases); entry = frontier
            chunks, terminals = [], []
            request = command = ack = None
            if tx['kind'] == 'read':
                request = push(old[tx['request_phase']], entry, 'read-request')
                command = push(old[tx['request_phase'] + 1], (request,), 'read-command')
            for ordinal, offset in enumerate(range(0, transfer.size_bytes, policy.chunk_bytes)):
                amount = min(policy.chunk_bytes, transfer.size_bytes - offset)
                gate = (terminals[ordinal-policy.window_chunks],) if ordinal >= policy.window_chunks else ()
                if tx['kind'] == 'read':
                    source = bytes_phase('memory_read', base.memory[tx['source']].read_port,
                                         amount, (command, *gate), 'bank-fragment')
                    channel = bytes_phase('memory_read', ctrl + '/channel', amount,
                                          (source,), 'channel-fragment')
                    payload = push(Phase('transfer', transfer=replace(transfer, size_bytes=amount)),
                                   (channel,), 'response-fragment')
                    destination = bytes_phase('memory_write', base.memory[tx['destination']].write_port,
                                              amount, (payload,), 'sram-fragment')
                else:
                    source = bytes_phase('memory_read', base.memory[tx['source']].read_port,
                                         amount, (*entry, *gate), 'sram-fragment')
                    payload = push(Phase('transfer', transfer=replace(transfer, size_bytes=amount)),
                                   (source,), 'write-fragment')
                    if command is None:
                        command = bytes_phase('memory_write', ctrl + '/command', CONTROL_BYTES,
                                              (payload,), 'write-command')
                    channel = bytes_phase('memory_write', ctrl + '/channel', amount,
                                          (payload, command), 'channel-fragment')
                    destination = bytes_phase('memory_write', base.memory[tx['destination']].write_port,
                                              amount, (channel,), 'bank-fragment')
                chunks.append(dict(ordinal=ordinal, offset=offset, bytes=amount,
                    source_phase=source, channel_phase=channel, payload_phase=payload,
                    destination_phase=destination))
                terminals.append(destination)
            if tx['kind'] == 'write':
                ack = push(old[tx['ack_phase']], tuple(terminals), 'write-ack')
                frontier = (ack,)
            else:
                frontier = tuple(terminals)
            row = {k: v for k, v in tx.items() if k not in {'payload_phase', 'first_phase', 'last_phase',
                                                          'request_phase', 'ack_phase'}}
            row.update(first_phase=start, last_phase=len(phases)-1, entry_phases=entry,
                       request_phase=request, command_phase=command, ack_phase=ack, chunks=chunks)
            ledger.append(row)
            index = tx['last_phase'] + 1
        plans[op] = replace(plan, phases=tuple(phases), dependencies=tuple(dependencies),
                            action_ids=tuple(actions), policy='bounded-periphery-dma')
    binding = replace(base, plans=MappingProxyType(plans))
    TimedTarget(binding, compiled.timing)
    return binding, ledger
