"""Physical candidate machines, independent of workloads and execution policy.

This is a declared stitched-compute / memory-periphery stack, not a foundry
qualification. A memory tile is a leaf gateway/controller with banks; it does
not provide an undeclared lateral interconnect wafer.
"""
from dataclasses import dataclass
from math import ceil

from wafer_sim.workloads.spatial import natural


@dataclass(frozen=True)
class Layer:
    id: str
    role: str
    z_um: int


@dataclass(frozen=True)
class Tile:
    id: str
    layer: str
    x_um: int
    y_um: int
    width_um: int
    height_um: int
    max_ports: int
    hb_signal_budget: int


@dataclass(frozen=True)
class Connection:
    id: str
    source: str
    destination: str
    kind: str
    signals_per_direction: int
    bits_per_signal_cycle: int
    latency_cycles: int

    @property
    def bytes_per_cycle(self):
        return self.signals_per_direction * self.bits_per_signal_cycle // 8


@dataclass(frozen=True)
class Store:
    id: str
    tile: str
    kind: str
    capacity_bytes: int
    bytes_per_cycle: int
    latency_cycles: int
    controller: str | None = None


@dataclass(frozen=True)
class Controller:
    id: str
    tile: str
    command_cycles: int
    channel_bytes_per_cycle: int
    buffer_bytes: int


@dataclass(frozen=True)
class WaferMachine:
    name: str
    layers: tuple[Layer, ...]
    tiles: tuple[Tile, ...]
    connections: tuple[Connection, ...]
    stores: tuple[Store, ...]
    controllers: tuple[Controller, ...]
    compute_rates: tuple[tuple[str, int], ...]
    technology: str
    wafer_diameter_um: int
    hb_pitch_um: int
    stitch_signals_per_boundary: int
    wire_um_per_cycle: int
    frequency_hz: int
    flit_bytes: int
    router_latency_cycles: int
    access_latency_cycles: int
    provenance: str


def validate(machine):
    """Check declared geometric legality and budgets, not physical sign-off."""
    def unique(rows):
        if type(rows) is not tuple:
            raise ValueError('Physical collections must be immutable tuples')
        out = {r.id: r for r in rows}
        if len(out) != len(rows) or any(not r.id for r in rows):
            raise ValueError('Duplicate or empty physical identity')
        return out
    layers, tiles = unique(machine.layers), unique(machine.tiles)
    stores, controllers = unique(machine.stores), unique(machine.controllers)
    unique(machine.connections)
    if not machine.name or not machine.provenance:
        raise ValueError('Machine identity and parameter provenance required')
    if machine.technology not in {'stitched_compute_hb_memory', 'unstitched_compute_hb_memory'}:
        raise ValueError('Unknown integration technology')
    if sorted(l.role for l in layers.values()) != ['compute', 'external', 'memory']:
        raise ValueError('Candidate requires compute, memory and external domains')
    if any(type(l.z_um) is not int for l in layers.values()):
        raise ValueError('Layer coordinates must use integer micrometers')
    for field in ('wafer_diameter_um', 'hb_pitch_um', 'stitch_signals_per_boundary',
                  'wire_um_per_cycle', 'frequency_hz', 'flit_bytes',
                  'router_latency_cycles', 'access_latency_cycles'):
        natural(getattr(machine, field), field, positive=True)
    if not machine.compute_rates or len(dict(machine.compute_rates)) != len(machine.compute_rates):
        raise ValueError('Explicit unique compute service rates required')
    for unit, rate in machine.compute_rates:
        if not unit: raise ValueError('Empty work unit')
        natural(rate, 'compute rate', positive=True)
    def role(tile): return layers[tile.layer].role
    for t in tiles.values():
        if t.layer not in layers: raise ValueError('Tile has missing layer')
        if type(t.x_um) is not int or type(t.y_um) is not int:
            raise ValueError('Tile coordinates must use integer micrometers')
        for f in ('width_um', 'height_um', 'max_ports'):
            natural(getattr(t, f), f, positive=True)
        natural(t.hb_signal_budget, 'HB signal budget')
        if role(t) != 'external':
            for x in (t.x_um, t.x_um+t.width_um):
                for y in (t.y_um, t.y_um+t.height_um):
                    if 4*(x*x+y*y) > machine.wafer_diameter_um**2:
                        raise ValueError('Tile extends outside wafer')
    ts = list(tiles.values())
    def overlap(a, b):
        return (min(a.x_um+a.width_um,b.x_um+b.width_um)-max(a.x_um,b.x_um),
                min(a.y_um+a.height_um,b.y_um+b.height_um)-max(a.y_um,b.y_um))
    for i, a in enumerate(ts):
        for b in ts[i+1:]:
            dx, dy = overlap(a,b)
            if a.layer == b.layer and dx > 0 and dy > 0:
                raise ValueError('Same-layer tiles overlap')
    ports = dict.fromkeys(tiles, 0); hb = dict.fromkeys(tiles, 0); pairs = set()
    adjacency = {t:set() for t in tiles}
    for link in machine.connections:
        if link.source not in tiles or link.destination not in tiles:
            raise ValueError('Connection references missing tile')
        a,b = tiles[link.source],tiles[link.destination]
        pair = tuple(sorted((a.id,b.id)))
        if a.id == b.id or pair in pairs: raise ValueError('Duplicate or self connection')
        pairs.add(pair); adjacency[a.id].add(b.id); adjacency[b.id].add(a.id)
        for f in ('signals_per_direction','bits_per_signal_cycle','latency_cycles'):
            natural(getattr(link,f),f,positive=True)
        if link.signals_per_direction*link.bits_per_signal_cycle % 8:
            raise ValueError('Bandwidth must be an integral byte per cycle')
        for t in (a,b): ports[t.id] += 1
        dx,dy = overlap(a,b)
        if link.kind == 'stitch':
            if machine.technology != 'stitched_compute_hb_memory':
                raise ValueError('Lateral reticle link requires declared stitching')
            if role(a) != 'compute' or role(b) != 'compute' or a.layer != b.layer:
                raise ValueError('Stitching only exists on compute wafer')
            if not ((dx == 0 and dy > 0) or (dy == 0 and dx > 0)):
                raise ValueError('Stitch link must cross a shared physical boundary')
            if 2*link.signals_per_direction > machine.stitch_signals_per_boundary:
                raise ValueError('Stitch boundary signal budget exceeded')
            distance = abs(2*a.x_um+a.width_um-2*b.x_um-b.width_um)+abs(2*a.y_um+a.height_um-2*b.y_um-b.height_um)
            if link.latency_cycles < ceil(distance/(2*machine.wire_um_per_cycle)):
                raise ValueError('Link latency smaller than declared wire pipeline bound')
        elif link.kind == 'hb':
            if {role(a),role(b)} != {'compute','memory'} or (a.x_um,a.y_um,a.width_um,a.height_um) != (b.x_um,b.y_um,b.width_um,b.height_um):
                raise ValueError('HB candidate requires aligned equal-size footprints')
            if layers[a.layer].z_um == layers[b.layer].z_um:
                raise ValueError('HB requires separate physical layers')
            sites = (dx//machine.hb_pitch_um)*(dy//machine.hb_pitch_um)
            for t in (a,b):
                hb[t.id] += 2*link.signals_per_direction
                if t.hb_signal_budget > sites: raise ValueError('HB budget exceeds geometric sites')
        elif link.kind == 'io':
            if {role(a),role(b)} != {'compute','external'}:
                raise ValueError('Off-wafer I/O must attach to compute fabric')
            compute_tile = a if role(a)=='compute' else b
            # At least one unoccupied rectangle edge must face off-array space.
            neighbors=[t for t in ts if role(t)=='compute' and t.id!=compute_tile.id]
            enclosed=all(any((side=='left' and t.x_um+t.width_um==compute_tile.x_um and overlap(t,compute_tile)[1]>0)
                         or (side=='right' and t.x_um==compute_tile.x_um+compute_tile.width_um and overlap(t,compute_tile)[1]>0)
                         or (side=='down' and t.y_um+t.height_um==compute_tile.y_um and overlap(t,compute_tile)[0]>0)
                         or (side=='up' and t.y_um==compute_tile.y_um+compute_tile.height_um and overlap(t,compute_tile)[0]>0)
                         for t in neighbors) for side in ('left','right','down','up'))
            if enclosed: raise ValueError('I/O gateway is not on array edge')
        else: raise ValueError('Unknown physical connection kind')
    for c in controllers.values():
        if c.tile not in tiles or role(tiles[c.tile]) not in {'memory','external'}:
            raise ValueError('Controller must occupy memory-periphery or external tile')
        natural(c.command_cycles,'command cycles',positive=True)
        natural(c.channel_bytes_per_cycle,'channel bandwidth',positive=True)
        natural(c.buffer_bytes,'controller staging capacity',positive=True)
        if not any(s.controller==c.id for s in stores.values()):
            raise ValueError('Unconnected memory controller')
    per_tile = dict.fromkeys(tiles,0)
    for m in stores.values():
        if m.tile not in tiles: raise ValueError('Store has missing tile')
        expected = {'sram':'compute','dram':'memory','external':'external'}
        if m.kind not in expected or role(tiles[m.tile]) != expected[m.kind]:
            raise ValueError('Store kind does not match layer')
        for f in ('capacity_bytes','bytes_per_cycle'): natural(getattr(m,f),f,positive=True)
        natural(m.latency_cycles,'memory service latency')
        if m.kind in {'dram','external'}:
            if m.controller not in controllers or controllers[m.controller].tile != m.tile:
                raise ValueError('Addressable store must name its colocated controller')
        elif m.controller is not None: raise ValueError('Unexpected controller on non-DRAM store')
        ports[m.tile] += 1; per_tile[m.tile] += 1
    for t in tiles.values():
        if ports[t.id] > t.max_ports or hb[t.id] > t.hb_signal_budget:
            raise ValueError('Router port or HB signal budget exceeded')
        if role(t) in {'compute','external'} and per_tile[t.id] != 1:
            raise ValueError('One local SRAM / external store per gateway required')
        if role(t) == 'memory' and (per_tile[t.id] == 0 or len(adjacency[t.id]) != 1):
            raise ValueError('Memory tile must be a populated leaf, not a transit fabric')
    return dict(passed=True,router_ports=ports,hb_signal_usage=hb,
                qualification='Declared geometry and resource consistency only; not PPA/yield sign-off')


def from_config(config):
    rows,cols=config['array']; tw,th=config['tile_um']
    natural(rows,'rows',positive=True); natural(cols,'columns',positive=True)
    natural(tw,'tile width',positive=True); natural(th,'tile height',positive=True)
    natural(config['banks_per_tile'],'banks per tile',positive=True)
    tiles=[]; stores=[]; controllers=[]; links=[]
    for y in range(rows):
        for x in range(cols):
            i=y*cols+x; px=x*tw-cols*tw//2; py=y*th-rows*th//2
            for prefix,layer in (('c','compute'),('m','memory')):
                tiles.append(Tile(f'{prefix}{i}',layer,px,py,tw,th,
                                  config['max_router_ports'],config['hb_signal_budget']))
            s=config['sram']; d=config['dram']; ctrl=f'controller-{i}'
            stores.append(Store(f'sram-{i}',f'c{i}','sram',s['capacity_bytes'],s['bytes_per_cycle'],s['latency_cycles']))
            controllers.append(Controller(ctrl,f'm{i}',d['command_cycles'],d['channel_bytes_per_cycle'],d['buffer_bytes']))
            for j in range(config['banks_per_tile']):
                stores.append(Store(f'dram-{i}-{j}',f'm{i}','dram',d['bank_capacity_bytes'],
                                    d['bank_bytes_per_cycle'],d['bank_latency_cycles'],ctrl))
            for peer in ([i+1] if x+1<cols else [])+([i+cols] if y+1<rows else []):
                spec=config['links']['stitch']
                links.append(Connection(f'c{i}-c{peer}',f'c{i}',f'c{peer}','stitch',**spec))
            links.append(Connection(f'hb-{i}',f'c{i}',f'm{i}','hb',**config['links']['hb']))
    io=config['io']
    tiles.append(Tile('host','external',-cols*tw//2-tw,-rows*th//2,tw,th,2,0))
    controllers.append(Controller('host-controller','host',io['command_cycles'],io['channel_bytes_per_cycle'],io['buffer_bytes']))
    stores.append(Store('host-memory','host','external',io['capacity_bytes'],io['bytes_per_cycle'],io['latency_cycles'],'host-controller'))
    links.append(Connection('edge-io','c0','host','io',**config['links']['io']))
    m=WaferMachine(config['name'],(Layer('compute','compute',0),Layer('memory','memory',50),
        Layer('external','external',0)),tuple(tiles),tuple(links),tuple(stores),tuple(controllers),
        tuple(config['compute_rates'].items()),config['technology'],config['wafer_diameter_um'],
        config['hb_pitch_um'],config['stitch_signals_per_boundary'],config['wire_um_per_cycle'],
        config['frequency_hz'],config['flit_bytes'],config['router_latency_cycles'],
        config['access_latency_cycles'],config['provenance'])
    validate(m)
    return m
