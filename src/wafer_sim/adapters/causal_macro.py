"""G2.1 macro extension of the pinned G1 transitions, not a network backend.

Only the primary contract and one source-0 message are supported. The normal
transition body is mechanically reused; no Native trace is a prediction input.
"""
import ast
from collections import deque
from copy import deepcopy
import hashlib
import inspect
from pathlib import Path
from wafer_sim.adapters import causal_merge as g1
from wafer_sim.architecture.causal_merge import validate

G1_SHA256='24831579b2d0c49d11ab1003daef490754dba5d92e80b68c30da0fdbd1e9cf41'
_CORE=None


class RangeQueue:
    """Exact ordered homogeneous source suffix, with constant-time removal."""
    def __init__(self):self.start=0;self.stop=0
    def __len__(self):return self.stop-self.start
    def __bool__(self):return self.start<self.stop
    def __getitem__(self,i):
        if i<0:i+=len(self)
        if not 0<=i<len(self):raise IndexError(i)
        return self.start+i
    def reset(self,start,length):self.start=start;self.stop=start+length
    def popleft(self):
        f=self[0];self.start+=1;return f
    def skip(self,n):
        if not 0<=n<len(self):raise ValueError('Source tail crossed')
        self.start+=n


class LazyWork:
    """Generated label range plus live metadata; retired evidence is separate."""
    def __init__(self):self.data={};self.total=0;self.generated=None
    def register(self,mid,message,start,now):
        if mid!=0 or start!=0 or self.generated is not None:raise ValueError('Unsupported generation epoch')
        self.total=message['flits'];self.generated=now
    def __getitem__(self,f):
        if not 0<=f<self.total:raise ValueError('Unknown generated flit')
        if f not in self.data:
            self.data[f]=dict(id=f,message=0,source=0,destination=3,generated=self.generated,
                router_path=[],link_arrivals=[])
        return self.data[f]
    def items(self):return self.data.items()


def shifted(row,dt,df,kind):
    if kind=='time':return row+dt
    out=deepcopy(row)
    if kind=='retired':
        out['id']+=df
        for field in ('injected','ejected','injection_router_arrival'):
            if field in out:out[field]+=dt
        for arrival in out['link_arrivals']:arrival['cycle']+=dt
    else:
        out['cycle']+=dt
        if 'flit' in out:out['flit']+=df
        if 'heads' in out:out['heads']=[f+df if f>=0 else -1 for f in out['heads']]
    return out


class Evidence:
    def __init__(self,kind,keep):
        self.kind=kind;self.keep=keep;self.segments=[];self.recent=deque()
        self.count=0;self.first=None;self.last=None
    def __len__(self):return self.count
    def clock(self,row):return row if self.kind=='time' else row['ejected'] if self.kind=='retired' else row['cycle']
    def append(self,row):
        t=self.clock(row);self.count+=1
        if self.first is None:self.first=t
        self.last=t;self.recent.append((t,row))
        while self.recent and self.recent[0][0]<t-8:self.recent.popleft()
        if self.keep:
            if not self.segments or self.segments[-1]['kind']!='rows':self.segments.append(dict(kind='rows',rows=[]))
            self.segments[-1]['rows'].append(row)
    def window(self,start,end):return [r for t,r in self.recent if start<=t<end]
    def repeat(self,template,n):
        if not template:raise ValueError('Empty macro evidence template')
        self.count+=n*len(template);self.last=self.clock(template[-1])+2*n
        if self.keep:self.segments.append(dict(kind='repeat',period=2,flit_stride=1,repetitions=n,template=deepcopy(template)))
        self.recent.clear()
    def expand(self):
        if not self.keep:raise ValueError('Counters-only execution cannot provide full evidence')
        result=[]
        for segment in self.segments:
            if segment['kind']=='rows':result.extend(segment['rows'])
            else:
                for i in range(1,segment['repetitions']+1):
                    result.extend(shifted(r,2*i,i,self.kind) for r in segment['template'])
        if len(result)!=self.count:raise ValueError('Expanded evidence count differs')
        return result


def frozen(value):
    if isinstance(value,dict):return tuple((k,frozen(v)) for k,v in sorted(value.items()))
    if isinstance(value,(list,tuple)):return tuple(frozen(v) for v in value)
    return value


def normalized(row,now,anchor,kind):
    if kind=='time':return row-now
    out=shifted(row,-now,-anchor,kind)
    if 'heads' in row:out['heads']=[f-anchor if f>=0 else None for f in row['heads']]
    return frozen(out)


class MacroRun:
    def __init__(self,controller,final_cycle):
        self.controller=controller;self.final_cycle=final_cycle
    def compact(self):
        s=self.controller;i=s.injections[0];e=s.ejections[0]
        return dict(complete=True,drained=True,final_cycle=self.final_cycle,
            messages=[dict(id=0,source=0,destination=3,ready=s.demand[0]['ready'],generated=s.generated[0],
                flits=s.total,first_inject=i.first,last_inject=i.last,first_eject=e.first,last_eject=e.last,finish=e.last+1)],
            event_counts={name:len(log) for name,log in s.logs.items()},
            source_stall_cycles=s.source_stalls,router_credit_stall_cycles=s.router_stalls,queue_peaks=s.queue_peaks,
            native_boundary_inputs=False)
    def metrics(self):
        s=self.controller
        return dict(physical_cycle_updates=s.updates,logical_cycles=self.final_cycle,skipped_cycles=s.skipped,
            macros=len(s.macros),batches=s.macros,evidence_mode='compact' if s.keep else 'counters',
            expanded_during_execution=False,checkpoints=s.checkpoints)
    def expand(self):
        s=self.controller;message=self.compact()['messages'][0].copy()
        message['flits']=s.retired.expand()
        return dict(complete=True,drained=True,final_cycle=self.final_cycle,messages=[message],
            service=s.service.expand(),input_arrivals=s.inputs.expand(),credit_returns=s.credits.expand(),
            credit_sends=s.credit_sends.expand(),allocations=s.allocations.expand(),
            source_stall_cycles=s.source_stalls,router_credit_stall_cycles=s.router_stalls,queue_peaks=s.queue_peaks,
            native_boundary_inputs=False,processed_cycles=self.final_cycle,
            scope='Independent bounded four-router G1 prediction; no service compression')
    def evidence(self):
        s=self.controller
        if not s.keep:raise ValueError('No complete evidence in counters mode')
        return {name:log.segments for name,log in s.logs.items()}


class Controller:
    def __init__(self,c,demand,states,issuing,source_credits,todo,generated,work,injections,ejections,
                 service,inputs,credits,credit_sends,allocations,future,source_stalls,router_stalls,queue_peaks,limit,options):
        self.c=c;self.demand=demand;self.states=states;self.issuing=issuing;self.source_credits=source_credits
        self.todo=todo;self.generated=generated;self.work=work;self.injections=injections;self.ejections=ejections
        self.service=service;self.inputs=inputs;self.credits=credits;self.credit_sends=credit_sends
        self.allocations=allocations;self.future=future;self.source_stalls=source_stalls;self.router_stalls=router_stalls
        self.queue_peaks=queue_peaks;self.limit=limit;self.total=demand[0]['flits'];self.keep=options['evidence']=='compact'
        self.compress=options['compress'];self.verify=options['checkpoints'];self.retired=Evidence('retired',self.keep)
        self.logs=dict(service=service,input_arrivals=inputs,credit_returns=credits,credit_sends=credit_sends,
            allocations=allocations,retired=self.retired,injections=injections[0],ejections=ejections[0])
        self.history={};self.updates=0;self.skipped=0;self.macros=[];self.checkpoints=[]
    def retire(self,f):
        row=self.work[f];self.retired.append(dict(row,hops=len(row['router_path'])))
        del self.work.data[f]
    def local_state(self,now):
        return dict(now=now,demand=self.demand,work=self.work,generated=self.generated,states=self.states,
            issuing=self.issuing,source_credits=self.source_credits,todo=self.todo,future=self.future,
            injections=self.injections,ejections=self.ejections,service=self.service,inputs=self.inputs,
            credits=self.credits,credit_sends=self.credit_sends,allocations=self.allocations,
            source_stalls=self.source_stalls,router_stalls=self.router_stalls,queue_peaks=self.queue_peaks,
            cycle_limit=self.limit,next_flit=self.total)
    def checkpoint(self,now):
        # Independent verbose normalization is only used in validation mode.
        from wafer_sim.analysis.causal_compressibility import BoundaryObserver
        observer=BoundaryObserver();observer.first_flits={0:0};observer.capture(self.local_state(now))
        return observer.rows[0]
    def kernel(self,now):
        anchor=len(self.injections[0]);active=set()
        def token(f):active.add(f);return f-anchor
        state=[]
        for s in self.states:
            state.append((tuple(tuple(token(f) for f in q) for q in s['queues']),s['owner'],
                None if s['sw_ready'] is None else s['sw_ready']-now,s['credit'],s['vc_pointer'],s['sw_pointer']))
        events=[]
        for t,rows in sorted(self.future.items()):
            if t<now:raise ValueError('Overdue event')
            events.append((t-now,tuple(tuple((k,token(v) if k=='flit' else v) for k,v in sorted(r.items())) for r in rows)))
        metadata=[]
        for f in sorted(active):
            row=self.work.data[f]
            metadata.append((f-anchor,row['message'],row['source'],row['destination'],row['generated'],
                row.get('injected',now)-now,row.get('injection_router_arrival',now)-now,
                tuple(row['router_path']),tuple((a['source'],a['destination'],a['cycle']-now,a['vc']) for a in row['link_arrivals'])))
        return (tuple(state),tuple(self.source_credits),tuple(events),tuple(metadata),
            tuple(tuple(q) for q in self.todo),tuple(sorted(self.generated.items())),
            tuple(bool(q) for q in self.issuing),tuple(tuple(q) for q in self.queue_peaks))
    def progress(self):
        return (len(self.injections[0]),len(self.ejections[0]),tuple(self.source_stalls),tuple(self.router_stalls),
            tuple(len(log) for log in self.logs.values()))
    def guard(self):
        return (self.generated=={0:self.demand[0]['ready']} and not any(self.todo) and
            len(self.issuing[0])>3 and not self.issuing[1] and not self.issuing[2] and
            self.total-len(self.ejections[0])>3 and all(s['credit']>0 for s in self.states) and
            all(not q for r,s in enumerate(self.states) for p,q in enumerate(s['queues'])
                if (r,p) not in ((0,0),(2,0),(3,1))))
    def boundary(self,now):
        self.updates+=1
        if not self.compress or not self.guard():return now
        key=self.kernel(now);progress=self.progress();prior=self.history.get(now%2)
        record=dict(now=now,key=key,progress=progress,confirmations=0,pattern=None)
        self.history[now%2]=record
        if prior is None or prior['now']!=now-2 or prior['key']!=key:return now
        before=prior['progress']
        if (progress[0]-before[0],progress[1]-before[1],tuple(b-a for a,b in zip(before[2],progress[2])),
                tuple(b-a for a,b in zip(before[3],progress[3])),tuple(b-a for a,b in zip(before[4],progress[4]))) != (
                    1,1,(1,0,0),(0,0,0,0),(9,3,4,3,6,1,1,1)):
            return now
        templates={name:log.window(now-2,now) for name,log in self.logs.items()}
        pattern=tuple((name,tuple(normalized(row,now-2,before[0],self.logs[name].kind) for row in rows)) for name,rows in templates.items())
        record['pattern']=pattern
        record['confirmations']=prior['confirmations']+1 if prior['pattern']==pattern else 1
        if record['confirmations']<3:return now
        repeats=min(len(self.issuing[0])-1,self.total-len(self.ejections[0])-1,(self.limit-now-1)//2)
        if repeats<=0:return now
        if self.verify:self.checkpoints.append(dict(role='entry',state=self.checkpoint(now)))
        dt=2*repeats;df=repeats
        for s in self.states:
            s['queues']=[deque(f+df for f in q) for q in s['queues']]
            if s['sw_ready'] is not None:s['sw_ready']+=dt
        translated={t+dt:[dict(r,**({'flit':r['flit']+df} if 'flit' in r else {})) for r in rows] for t,rows in self.future.items()}
        self.future.clear();self.future.update(translated)
        live=set(f for s in self.states for q in s['queues'] for f in q)
        live.update(r['flit'] for rows in self.future.values() for r in rows if 'flit' in r)
        data={f:shifted(self.work.data[f-df],dt,df,'retired') for f in live}
        # shift() tolerates pre-retirement live metadata without an eject clock.
        self.work.data.clear();self.work.data.update(data)
        self.issuing[0].skip(df);self.source_stalls[0]+=repeats
        for name,log in self.logs.items():log.repeat(templates[name],repeats)
        self.skipped+=dt
        self.macros.append(dict(start=now,end=now+dt,period=2,repetitions=repeats,flit_stride=1,
            source_remaining_after=len(self.issuing[0]),receiver_remaining_after=self.total-len(self.ejections[0]),
            confirmations=3,templates=deepcopy(templates)))
        self.history.clear()
        if self.verify:self.checkpoints.append(dict(role='exit',state=self.checkpoint(now+dt)))
        return now+dt
    def finish(self,final_cycle):
        if self.updates+self.skipped!=final_cycle:raise ValueError('Physical/logical progress mismatch')
        return MacroRun(self,final_cycle)


def derived_source():
    """Checked edits to storage, observation and loop control, not service rules."""
    if hashlib.sha256(Path(g1.__file__).read_bytes()).hexdigest()!=G1_SHA256:
        raise ValueError('G1 transition source changed')
    tree=ast.parse(inspect.getsource(g1.simulate));fn=tree.body[0]
    fn.name='_derived_core';fn.args.kwonlyargs.append(ast.arg(arg='options'));fn.args.kw_defaults.append(None)
    # Initialization substitutions preserve dictionary/deque APIs used by G1.
    replacements={
        'issuing':'issuing = [RangeQueue() for _ in range(3)]',
        'work':'work = LazyWork()',
        'injections':'injections = {i: Evidence("time", options["evidence"] == "compact") for i in range(3)}',
        'ejections':'ejections = {i: Evidence("time", options["evidence"] == "compact") for i in range(3)}',
        'service':'service = Evidence("event", options["evidence"] == "compact")',
        'inputs':'inputs = Evidence("event", options["evidence"] == "compact")',
        'credits':'credits = Evidence("event", options["evidence"] == "compact")',
        'credit_sends':'credit_sends = Evidence("event", options["evidence"] == "compact")',
        'allocations':'allocations = Evidence("event", options["evidence"] == "compact")'}
    replaced=set();body=[];loop=None
    for node in fn.body:
        if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in replacements:
            name=node.targets[0].id;body.extend(ast.parse(replacements[name]).body);replaced.add(name)
        elif isinstance(node,ast.For) and isinstance(node.target,ast.Name) and node.target.id=='now':
            loop=node;break
        else:body.append(node)
    if replaced!=set(replacements) or loop is None:raise ValueError('Unrecognized G1 initialization')
    generation=[n for n in ast.walk(loop) if isinstance(n,ast.For) and ast.unparse(n.iter)=="range(m['flits'])"]
    if len(generation)!=1:raise ValueError('Unrecognized source-label generation')
    class Substitute(ast.NodeTransformer):
        def visit_For(self,node):
            if node is generation[0]:return ast.parse("work.register(mid, m, next_flit, now)\nissuing[source].reset(next_flit, m['flits'])\nnext_flit += m['flits']").body
            return self.generic_visit(node)
        def visit_If(self,node):
            node=self.generic_visit(node)
            if ast.unparse(node.test)=="kind == 'sink'":node.body.append(ast.parse('controller.retire(f)').body[0])
            return node
    loop=Substitute().visit(loop)
    init='controller = Controller(c, demand, states, issuing, source_credits, todo, generated, work, injections, ejections, service, inputs, credits, credit_sends, allocations, future, source_stalls, router_stalls, queue_peaks, cycle_limit, options)\nnow = 0'
    body.extend(ast.parse(init).body)
    body.append(ast.While(test=ast.parse('now < cycle_limit',mode='eval').body,
        body=ast.parse('now = controller.boundary(now)').body+loop.body+ast.parse('now += 1').body,orelse=[]))
    body.extend(ast.parse("if final_cycle is None: raise TimeoutError('Incomplete causal merge execution')\nreturn controller.finish(final_cycle)").body)
    fn.body=body;ast.fix_missing_locations(tree)
    return '# Mechanically derived from pinned G1 '+G1_SHA256+'\n'+ast.unparse(tree)+'\n'


def run(contract,messages,cycle_limit=200000,*,compress=True,evidence='compact',checkpoints=False):
    global _CORE
    c=validate(contract)
    if (c['capacity_flits']!=32 or c['router_link_latency']!=17 or c['endpoint_link_latency']!=1 or c['crossbar_delay']!=2 or c['flit_bytes']!=64 or
            len(messages)!=1 or set(messages[0])!={'source','destination','flits','ready'} or
            messages[0]['source']!=0 or messages[0]['destination']!=3):raise ValueError('Outside G2.1 single-flow primary contract')
    if type(compress) is not bool or type(checkpoints) is not bool or evidence not in ('compact','counters'):
        raise ValueError('Invalid macro execution mode')
    if _CORE is None:
        namespace=dict(g1.simulate.__globals__,RangeQueue=RangeQueue,LazyWork=LazyWork,Evidence=Evidence,Controller=Controller)
        exec(compile(derived_source(),'<pinned G1 macro derivation>','exec'),namespace)
        _CORE=namespace['_derived_core']
    return _CORE(c,messages,cycle_limit,options=dict(compress=compress,evidence=evidence,checkpoints=checkpoints))
