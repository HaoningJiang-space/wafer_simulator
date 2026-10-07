"""Bind logical work to explicit memory, compute and network service demands.

No durations or hardware capacities are inferred. No network run is launched.
Staging is whole-object, serialized within each operation and uncached between
operations. A service backend must arbitrate equal resource IDs, including
ports shared across regions, and complete each phase before advancing it.
"""
from types import MappingProxyType

from wafer_sim.workloads.spatial import identifier, natural, validate
from wafer_sim.io import object_digest
from wafer_sim.architecture.spatial import Network
from wafer_sim.execution.plan import Allocation, Demand, Transfer, Phase, OperationPlan, Binding


def network_from_wow(export):
    """Reuse an existing author geometry export; do not invent memory sizes.

    Full bandwidth, latency and geometry remain in the hashed export, for a
    future timing backend. This contract checks physical reachability only.
    """
    links = export["inputs"]["links"]
    if any(not link["bidirectional"] for link in links):
        raise ValueError("v1 requires bidirectional physical links")
    return Network(tuple((e["node"], e["router"]) for e in export["endpoints"]),
                   tuple((link["src"], link["dst"]) for link in links),
                   "WoW export object SHA-256 " + object_digest(export))


def validate_target(target):
    import networkx as nx

    network = target.network
    identifier(network.provenance, "Network provenance")
    for rows in (network.endpoint_routers, network.router_links):
        if type(rows) is not tuple:
            raise ValueError("Network collections must be immutable tuples")
        for pair in rows:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError("Network rows must be immutable pairs")
            for item in pair:
                natural(item, "network identity")
    attachments = dict(network.endpoint_routers)
    if len(attachments) != len(network.endpoint_routers):
        raise ValueError("Duplicate network endpoint")
    physical = nx.Graph()
    physical.add_nodes_from(attachments.values())
    seen = set()
    for a, b in network.router_links:
        edge = tuple(sorted((a, b)))
        if a == b or edge in seen:
            raise ValueError("Self/parallel router links need explicit modeling")
        seen.add(edge)
        physical.add_edge(a, b)
    component = {router: i for i, group in enumerate(nx.connected_components(physical)) for router in group}
    memory = {m.id: m for m in target.memory}
    compute = {c.id: c for c in target.compute}
    if (type(target.memory) is not tuple or type(target.compute) is not tuple or
            not memory or not compute or len(memory) != len(target.memory) or len(compute) != len(target.compute)):
        raise ValueError("Target needs unique, immutable resource collections")
    endpoints, ports = set(), set()
    for m in memory.values():
        for value in (m.id, m.read_port, m.write_port, m.provenance):
            identifier(value, "Memory resource/provenance")
        natural(m.endpoint, "network endpoint")
        natural(m.capacity_bytes, "regional capacity", positive=True)
        if m.endpoint in endpoints:
            raise ValueError("One memory region per endpoint in v1; local DMA needs a separate model")
        endpoints.add(m.endpoint)
        if m.endpoint not in attachments:
            raise ValueError("Memory endpoint absent from physical network")
        ports.update((m.read_port, m.write_port))
    for c in compute.values():
        identifier(c.id, "Compute resource")
        identifier(c.provenance, "Compute provenance")
        if c.memory not in memory or c.id in ports:
            raise ValueError("Missing compute memory or ambiguous compute/port resource ID")
        if type(c.work_units) is not tuple or len(c.work_units) != len(set(c.work_units)):
            raise ValueError("Compute work units must be unique immutable tuples")
        for unit in c.work_units:
            identifier(unit, "Supported work unit")
    return memory, compute, attachments, component


def bind(workload, target, placement):
    graph = validate(workload)
    network = target.network
    memory, compute, attachments, component = validate_target(target)
    homes, assigned = dict(placement.data), dict(placement.compute)
    if set(homes) != set(graph.data) or set(assigned) != set(graph.operations):
        raise ValueError("Placement must cover all and only logical objects/operations")
    if any(m not in memory for m in homes.values()) or any(c not in compute for c in assigned.values()):
        raise ValueError("Placement refers to an absent resource")
    for d in graph.data.values():
        if d.size_bytes > memory[homes[d.id]].capacity_bytes:
            raise ValueError("Data object cannot fit in its home region")
    plans = {}
    for op in graph.operations.values():
        c = compute[assigned[op.id]]
        local = memory[c.memory]
        if any(unit not in c.work_units for unit, _ in op.work):
            raise ValueError("Target compute resource cannot serve the declared work unit")
        allocations, phases = [], []

        def service(kind, port, amount):
            if amount:
                phases.append(Phase(kind, (Demand(port, "bytes", amount),)))

        def move(d, src, dst):
            if component[attachments[src.endpoint]] != component[attachments[dst.endpoint]]:
                raise ValueError("Required data movement crosses disconnected network components")
            service("memory_read", src.read_port, d.size_bytes)
            phases.append(Phase("transfer", transfer=Transfer(d.id, src.id, dst.id,
                src.endpoint, dst.endpoint, d.size_bytes)))
            service("memory_write", dst.write_port, d.size_bytes)

        for name in op.inputs:
            d, home = graph.data[name], memory[homes[name]]
            if home.id != local.id:
                allocations.append(Allocation(("input", op.id, name), local.id, d.size_bytes))
                move(d, home, local)
        service("memory_read", local.read_port, sum(graph.data[d].size_bytes for d in op.inputs))
        phases.append(Phase("compute", tuple(Demand(c.id, unit, amount) for unit, amount in op.work)))
        service("memory_write", local.write_port, sum(graph.data[d].size_bytes for d in op.outputs))
        for name in op.outputs:
            d, home = graph.data[name], memory[homes[name]]
            allocations.append(Allocation(("object", name), home.id, d.size_bytes))
            if home.id != local.id:
                allocations.append(Allocation(("output", op.id, name), local.id, d.size_bytes))
                move(d, local, home)
        if op.scratch_bytes:
            allocations.append(Allocation(("scratch", op.id), local.id, op.scratch_bytes))
        plans[op.id] = OperationPlan(tuple(allocations), tuple(phases))
    return Binding(graph, MappingProxyType(memory), MappingProxyType(homes), MappingProxyType(plans), network)
