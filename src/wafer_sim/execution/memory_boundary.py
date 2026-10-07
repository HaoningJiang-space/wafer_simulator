"""Streaming endpoint controller sharing the application's memory calendar."""
from collections import defaultdict, deque
from wafer_sim.adapters.timing import Step


class MemoryBoundary:
    backend_name='booksim_boundary'
    policy_description='BookSim with incremental source supply; whole-object commit; explicit endpoint service'

    def __init__(self, client, *, tx_slots, rx_slots, bounded):
        self.client=client;self.tx_slots=tx_slots;self.rx_slots=rx_slots;self.bounded=bounded
        client.configure(rx_slots=rx_slots,bounded=bounded)
        self.now=0;self.moves={};self.pending={};self.done=[];self.events=[]
        self.queues=defaultdict(deque);self.tx=defaultdict(int);self.rx=defaultdict(int)
        self.reading=defaultdict(bool);self.by_id={};self.clock=None

    @property
    def messages(self): return self.client.messages

    def submit_movement(self, token, phase, clock):
        if self.clock is None: self.clock=clock
        if clock is not self.clock or clock.now!=self.now: raise ValueError('Boundary clock mismatch')
        t=phase.transfer
        self.client.submit(token,t,self.now)
        mid=self.client.pending[token]['id'];self.by_id[mid]=token
        count=(t.size_bytes+self.client.flit_bytes-1)//self.client.flit_bytes
        row=dict(token=token,id=mid,ready=self.now,bytes=t.size_bytes,source=t.source_endpoint,
                 destination=t.destination_endpoint,read_port=phase.demands[0].resource,
                 write_port=phase.demands[1].resource,packets=[],committed=0,read_count=0,
                 injected_count=0,finish=None)
        self.moves[token]=row;self.pending[token]=row
        for k in range(count):
            row['packets'].append(dict(ordinal=k,bytes=min(self.client.flit_bytes,t.size_bytes-k*self.client.flit_bytes)))
        self.queues[t.source_endpoint].append(token)
        self._pump(t.source_endpoint)

    def _event(self, kind, row, packet, **fields):
        self.events.append(dict(event=kind,cycle=self.clock.now,token=row['token'],ordinal=packet['ordinal'],
            bytes=packet['bytes'],source=row['source'],destination=row['destination'],
            tx_slots=self.tx[row['source']],rx_slots=self.rx[row['destination']],**fields))

    def _pump(self, src):
        if self.reading[src] or self.tx[src]>=self.tx_slots or not self.queues[src]: return
        row=self.moves[self.queues[src][0]]
        k=row['read_count']
        if k==len(row['packets']): return
        p=row['packets'][k];row['read_count']+=1
        self.tx[src]+=1;self.reading[src]=True
        p['reserved']=self.clock.now;self._event('tx_reserve',row,p)
        def ready():
            p['supplied']=self.clock.now;self.reading[src]=False
            self.client.supply(row['id']);self._event('supply',row,p);self._pump(src)
        self.clock.submit(f"{row['token']}/read/{k}",(Step(row['read_port'],'bytes',p['bytes'],'memory'),),ready)

    def advance(self, until):
        if self.done:
            result=self.done;self.done=[];self.now=self.clock.now
            return result
        self.client.advance(until);self.now=self.client.now
        self.clock.now=self.now
        for event in self.client.progress:
            row=self.moves[self.by_id[event['id']]];p=row['packets'][event['ordinal']]
            if event['cycle']!=self.now: raise ValueError('Native progress clock mismatch')
            if event['event']=='inject':
                p['injected']=self.now;p['flit']=event['flit'];self.tx[row['source']]-=1
                row['injected_count']+=1;self._event('inject',row,p)
                if row['injected_count']==len(row['packets']):
                    if self.queues[row['source']].popleft()!=row['token']: raise ValueError('Source message order changed')
                self._pump(row['source'])
            elif event['event']=='receive':
                p['received']=self.now
                self.rx[row['destination']]+=1;self._event('receive',row,p)
                if self.bounded and self.rx[row['destination']]>self.rx_slots: raise ValueError('RX overflow')
                def committed(row=row,p=p):
                    p['committed']=self.clock.now;self.rx[row['destination']]-=1
                    row['committed']+=p['bytes'];self._event('commit',row,p)
                    if self.bounded: self.client.commit(p['flit'])
                    if row['committed']==row['bytes']:
                        row['finish']=self.clock.now;self.pending.pop(row['token']);self.done.append(row['token'])
                self.clock.submit(f"{row['token']}/write/{p['ordinal']}",
                    (Step(row['write_port'],'bytes',p['bytes'],'memory'),),committed)
            else: raise ValueError('Unknown native progress event')
        return []

    def evidence(self):
        return dict(boundary=dict(tx_capacity_slots=self.tx_slots,rx_capacity_slots=self.rx_slots,
            bounded=self.bounded,flit_bytes=self.client.flit_bytes,
            moves=list(self.moves.values()),events=self.events))

    def close(self):
        if self.pending or self.done or any(self.tx.values()) or any(self.rx.values()):
            raise ValueError('Cannot close incomplete boundary')
        return self.client.close()

    def abort(self): self.client.abort()
