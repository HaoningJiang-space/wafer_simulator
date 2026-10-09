"""D1: one rational, event-driven fluid state for every traffic class.

All resources on a route are occupied concurrently during fluid serialization;
fixed propagation follows release. This idealizes immediate path backpressure.
Router outputs use independently calibrated single-packet service; physical
link and endpoint capacities retain the declared machine budgets. There are
no per-flit, finite-buffer, VC or credit objects.
"""
from dataclasses import asdict
from fractions import Fraction
import heapq
from math import ceil

from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.adapters.memory_abstraction import contract as resource_contract
from wafer_sim.io import object_digest
from wafer_sim.workloads.spatial import natural


def pair(value):
    value=Fraction(value)
    return [value.numerator,value.denominator]


def contract(compiled, registration):
    m=compiled.physical
    if registration['packet_service_cycles']!=2 or m.flit_bytes!=64:
        raise ValueError('D1 requires the independently verified 64-byte, two-cycle packet domain')
    if any(l.bytes_per_cycle!=m.flit_bytes for l in m.connections):
        raise ValueError('Unvalidated D1 physical link width')
    return dict(model='D1',machine_sha256=object_digest(asdict(m)),flit_bytes=m.flit_bytes,
        packet_service_cycles=registration['packet_service_cycles'],routing=registration['routing'],
        sharing=registration['sharing'],propagation=registration['propagation'],
        router_latency_cycles=m.router_latency_cycles,access_latency_cycles=m.access_latency_cycles,
        links=[dict(source=compiled.router_ids[l.source],destination=compiled.router_ids[l.destination],
                    latency_cycles=l.latency_cycles,bytes_per_cycle=l.bytes_per_cycle,kind=l.kind) for l in m.connections],
        resource_contract=resource_contract(compiled,'U1'),scope=registration['scope'],
        prediction_inputs=['physical machine','message endpoints','payload bytes','own online readiness and active flows'])


def max_min_rates(paths, capacities):
    """Progressive filling with exact rational rates and fixed equal weights."""
    rates={i:Fraction() for i in paths};unfixed=set(paths)
    users={r:{i for i,p in paths.items() if r in p} for r in capacities}
    while unfixed:
        limits={}
        for r,ids in users.items():
            count=len(ids & unfixed)
            if count:
                residual=capacities[r]-sum((rates[i] for i in ids),Fraction())
                limits[r]=residual/count
        if not limits: raise ValueError('Flow has no finite resource')
        increment=min(limits.values())
        if increment<0: raise ValueError('Infeasible fluid allocation')
        for i in unfixed: rates[i]+=increment
        saturated={r for r,v in limits.items() if v==increment}
        stopped=set().union(*(users[r] for r in saturated)) & unfixed
        if not stopped: raise ValueError('Progressive filling made no progress')
        unfixed-=stopped
    return rates


class SharedSpatialNetwork:
    backend_name='shared_spatial_service'
    policy_description='one all-class fluid network; physical lexicographic routes; equal max-min path sharing; integer release plus fixed propagation'

    def __init__(self, binding, timing, spec):
        if spec['model']!='D1': raise ValueError('D1 contract required')
        self.target=TimedTarget(binding,timing);self.spec=spec
        self.now=0;self.pending={};self.messages=[];self.active={};self.tails=[]
        self.rates={};self.epochs=[];self.epoch_begin=0;self.closed=False
        self.capacities={};self.path_cache={};self.next_id=0
        width=spec['flit_bytes'];output_rate=Fraction(1,spec['packet_service_cycles'])
        self.link_latency={}
        for l in spec['links']:
            for a,b in ((l['source'],l['destination']),(l['destination'],l['source'])):
                self.capacities[f'link/{a}/{b}']=Fraction(l['bytes_per_cycle'],width)
                self.capacities[f'output/{a}/router/{b}']=output_rate
                self.link_latency[a,b]=l['latency_cycles']
        for e,attachment in self.target.attachments.items():
            ep=self.target.endpoints[e]
            self.capacities[f'inject/{e}']=Fraction(ep.injection.rate_numerator,ep.injection.rate_denominator*width)
            self.capacities[f'eject/{e}']=Fraction(ep.ejection.rate_numerator,ep.ejection.rate_denominator*width)
            self.capacities[f'output/{attachment}/endpoint/{e}']=output_rate

    def route(self, source, destination):
        k=source,destination
        if k not in self.path_cache:
            path=self.target.route(source,destination)
            resources=[f'inject/{source}']
            for a,b in zip(path,path[1:]): resources.extend((f'link/{a}/{b}',f'output/{a}/router/{b}'))
            resources.extend((f'output/{path[-1]}/endpoint/{destination}',f'eject/{destination}'))
            latency=2*self.spec['access_latency_cycles']+len(path)*self.spec['router_latency_cycles']+sum(
                self.link_latency[a,b] for a,b in zip(path,path[1:]))
            self.path_cache[k]=path,tuple(resources),latency
        return self.path_cache[k]

    def _seal_epoch(self):
        if self.rates and self.now>self.epoch_begin:
            self.epochs.append(dict(begin=self.epoch_begin,end=self.now,
                rates={str(i):pair(r) for i,r in sorted(self.rates.items())}))
        self.epoch_begin=self.now

    def _reallocate(self):
        paths={i:v['resources'] for i,v in self.active.items()}
        used={r for p in paths.values() for r in p}
        self.rates=max_min_rates(paths,{r:self.capacities[r] for r in used}) if paths else {}

    def submit(self, token, transfer, cycle):
        if self.closed or type(cycle) is not int or cycle!=self.now or token in self.pending or any(m['token']==token for m in self.messages):
            raise ValueError('Closed, repeated or mistimed D1 submission')
        natural(transfer.size_bytes,'D1 payload',positive=True)
        if transfer.source_endpoint==transfer.destination_endpoint: raise ValueError('Local data must not enter D1')
        path,resources,latency=self.route(transfer.source_endpoint,transfer.destination_endpoint)
        self._seal_epoch();identity=self.next_id;self.next_id+=1
        work=(transfer.size_bytes+self.spec['flit_bytes']-1)//self.spec['flit_bytes']
        m=dict(id=identity,token=token,ready=cycle,bytes=transfer.size_bytes,source=transfer.source_endpoint,
            destination=transfer.destination_endpoint,data=transfer.data,source_memory=transfer.source_memory,
            destination_memory=transfer.destination_memory,engine='fluid',path=list(path),resources=list(resources),
            work_packets=work,propagation_cycles=latency)
        self.pending[token]=m;self.active[identity]=dict(message=m,remaining=Fraction(work),resources=resources)
        self._reallocate()

    def advance(self, until):
        natural(until,'D1 boundary')
        if self.closed or until<self.now: raise ValueError('Invalid D1 clock')
        while True:
            step=min([until]+([self.tails[0][0]] if self.tails else [])+[
                self.now+ceil(v['remaining']/self.rates[i]) for i,v in self.active.items()])
            elapsed=step-self.now
            for i,v in self.active.items(): v['remaining']=max(Fraction(),v['remaining']-self.rates[i]*elapsed)
            self.now=step
            done=[i for i,v in self.active.items() if v['remaining']==0]
            if done:
                self._seal_epoch()
                for i in sorted(done):
                    m=self.active.pop(i)['message'];m['service_finish']=self.now
                    heapq.heappush(self.tails,(self.now+m['propagation_cycles'],i,m['token']))
                self._reallocate()
            completed=[]
            while self.tails and self.tails[0][0]==self.now:
                finish,_,token=heapq.heappop(self.tails);m=self.pending.pop(token)
                m['finish']=finish;self.messages.append(m);completed.append(token)
            if completed or self.now==until: return completed

    def evidence(self):
        self._seal_epoch()
        return dict(shared_spatial_contract=self.spec,flow_epochs=self.epochs,
            flow_resource_capacities={r:pair(c) for r,c in sorted(self.capacities.items())},
            flow_counters=dict(messages=self.next_id,epochs=len(self.epochs),native_processes=0,flit_events=0))

    def close(self):
        if self.pending or self.active or self.tails: raise ValueError('Cannot close incomplete D1 network')
        self._seal_epoch();self.closed=True
        return dict(complete=True,messages=sorted(self.messages,key=lambda m:m['id']),**self.evidence())

    def abort(self): self.closed=True
