"""Packet-by-packet pipeline using the existing event/resource calendar."""
from wafer_sim.adapters.packet_pipeline import services
from wafer_sim.adapters.timing import Step
from wafer_sim.execution.timing import ResourceCalendar
from wafer_sim.workloads.spatial import natural


class PacketCalendar(ResourceCalendar):
    def __init__(self, rates):
        super().__init__(rates)
        self.by_packet={}

    def _schedule(self, token, steps, index, callback):
        super()._schedule(token,steps,index,callback)
        self.by_packet.setdefault(token,[]).append(self.records[-1])


class PacketPipeline:
    backend_name='packet_pipeline'
    policy_description='packet pipeline; FCFS output service; unbounded queues; fixed coarse paths; no VC/credit feedback'

    def __init__(self,target,model):
        self.target,self.model=target,model
        self.clock=PacketCalendar(services(target,model))
        self.pending,self.messages={},[]
        self._next_packet=0
        self._completed=[]
        self.closed=False

    @property
    def now(self): return self.clock.now

    def submit(self,token,transfer,cycle):
        if self.closed or cycle!=self.now or token in self.pending or any(m['token']==token for m in self.messages):
            raise ValueError('Closed, repeated or mistimed pipeline submission')
        natural(transfer.size_bytes,'Transfer bytes',positive=True)
        if transfer.source_endpoint==transfer.destination_endpoint:
            raise ValueError('Local data must not enter the network')
        path=self.target.route(transfer.source_endpoint,transfer.destination_endpoint)
        resources=[self.target.endpoints[transfer.source_endpoint].injection.resource,
            *(self.target.links[a,b].resource for a,b in zip(path,path[1:])),
            self.target.endpoints[transfer.destination_endpoint].ejection.resource]
        steps=tuple(Step(r,'packet',1,'network') for r in resources)
        width=self.model['flit_bytes'];count=(transfer.size_bytes+width-1)//width
        m=dict(id=len(self.pending)+len(self.messages),token=token,ready=cycle,generated=cycle,
            bytes=transfer.size_bytes,flit_bytes=width,expected_flits=count,
            source=transfer.source_endpoint,destination=transfer.destination_endpoint,
            data=transfer.data,source_memory=transfer.source_memory,destination_memory=transfer.destination_memory,flits=[])
        self.pending[token]=m
        for _ in range(count):
            fid=self._next_packet;self._next_packet+=1
            self.clock.submit(str(fid),steps,lambda fid=fid:self._retire_packet(m,path,fid))

    def _retire_packet(self,m,path,fid):
        events=self.clock.by_packet[str(fid)]
        m['flits'].append(dict(id=fid,message=m['id'],source=m['source'],destination=m['destination'],
            generated=m['generated'],injected=events[0]['start'],injection_router_arrival=events[0]['finish'],
            ejected=events[-1]['finish']-1,hops=len(path),router_path=list(path),
            link_arrivals=[dict(source=a,destination=b,cycle=e['finish'])
                           for (a,b),e in zip(zip(path,path[1:]),events[1:-1])]))
        if len(m['flits'])==m['expected_flits']:
            m.update(first_inject=min(f['injected'] for f in m['flits']),
                last_inject=max(f['injected'] for f in m['flits']),
                first_eject=min(f['ejected'] for f in m['flits']),
                last_eject=max(f['ejected'] for f in m['flits']),finish=self.now)
            del self.pending[m['token']]
            self.messages.append(m);self._completed.append(m['token'])

    def advance(self,until):
        natural(until,'Network boundary')
        if self.closed or until<self.now: raise ValueError('Invalid pipeline clock')
        self._completed=[]
        while self.clock.events and self.clock.events[0][0]<=until:
            if self._completed and self.clock.events[0][0]>self.now: break
            self.clock.advance()
        if not self._completed: self.clock.now=until
        return list(self._completed)

    def evidence(self):
        return dict(packet_contract=self.model,packet_services=self.clock.records)

    def close(self):
        if self.pending or self.clock.events or self.clock.active:
            raise ValueError('Cannot close unfinished pipeline work')
        self.closed=True
        return dict(complete=True,messages=sorted(self.messages,key=lambda m:m['id']),**self.evidence())

    def abort(self): self.closed=True
