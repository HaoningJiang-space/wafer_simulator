"""Integer-cycle FCFS resource calendar and automatic spatial execution.

Resources serialize one request at a time. Latency does not hold a serializer;
the next hop/phase is submitted only after completion, so future resources are
not reserved early. Admission and data lifetime reuse StorageState unchanged.
"""
import heapq

from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.execution.storage import StorageState


class ResourceCalendar:
    def __init__(self, services):
        self.services = services
        self.now = 0
        self.events = []
        self.free, self.owners = {}, {}
        self.records, self.active = [], set()
        self._sequence = 0

    def submit(self, token, steps, callback):
        if token in self.active or not steps:
            raise ValueError("Repeated request or empty service sequence")
        if any((s.resource,s.unit) not in self.services or type(s.amount) is not int or s.amount <= 0 for s in steps):
            raise ValueError("Missing service or invalid requested work")
        self.active.add(token)
        self._schedule(token,tuple(steps),0,callback)

    def _schedule(self, token, steps, index, callback):
        step = steps[index]
        service = self.services[step.resource,step.unit]
        duration = (step.amount*service.rate_denominator+service.rate_numerator-1)//service.rate_numerator
        start = max(self.now,self.free.get(step.resource,0))
        released = start+duration
        finish = released+service.latency_cycles
        identity = len(self.records)
        predecessor = self.owners.get(step.resource) if start > self.now else None
        self.records.append(dict(id=identity,token=token,step=index,resource=step.resource,
            unit=step.unit,amount=step.amount,category=step.category,ready=self.now,start=start,
            resource_released=released,finish=finish,resource_predecessor=predecessor))
        self.free[step.resource],self.owners[step.resource] = released,identity
        self._sequence += 1
        heapq.heappush(self.events,(finish,self._sequence,token,steps,index,callback))

    def advance(self):
        if not self.events: raise ValueError("No pending service completion")
        self.now, _,token,steps,index,callback = heapq.heappop(self.events)
        if index+1 < len(steps):
            self._schedule(token,steps,index+1,callback)
        else:
            self.active.remove(token)
            callback()

    def resource_summary(self):
        result = {}
        for event in self.records:
            entry = result.setdefault(event["resource"],dict(busy_cycles=0,queue_wait_cycles=0,requests=0,work={}))
            entry["busy_cycles"] += event["resource_released"]-event["start"]
            entry["queue_wait_cycles"] += event["start"]-event["ready"]
            entry["requests"] += 1
            entry["work"][event["unit"]] = entry["work"].get(event["unit"],0)+event["amount"]
        return result


def execute(binding, timing, *, network=None, cycle_limit=1000000):
    target = TimedTarget(binding,timing)
    state = StorageState(binding)
    clock = ResourceCalendar(target.services)
    operations, phases, lifecycle = {}, [], []
    dependency_ready = {}
    pending = list(binding.graph.order)
    network_callbacks = {}

    def submit_phase(op):
        index,phase = state.active[op],state.next_phase(op)
        token = f"{op}/phase/{index}"
        row = dict(operation=op,phase=index,kind=phase.kind,ready=clock.now,finish=None)
        if phase.transfer:
            row["transfer_bytes"] = phase.transfer.size_bytes
            if network is None:
                row["path"] = target.route(phase.transfer.source_endpoint,phase.transfer.destination_endpoint)
            else:
                row["network_token"] = token
        phases.append(row)
        def complete():
            row["finish"] = clock.now
            state.complete_phase(op,index)
            if op in state.completed:
                operations[op]["finish"] = clock.now
                lifecycle.append(dict(event="complete",operation=op,cycle=clock.now,used_bytes=state.used.copy()))
            else:
                submit_phase(op)
        if network is not None and phase.transfer:
            network.submit(token,phase.transfer,clock.now)
            network_callbacks[token] = complete
        else:
            clock.submit(token,target.steps(phase),complete)

    while True:
        # Stable topological input order within each admission opportunity.
        # No busy waiting: unsuccessful capacity admission waits for an event.
        for op in tuple(pending):
            decision = state.admission(op)
            if decision.missing_dependencies:
                continue
            dependency_ready.setdefault(op,clock.now)
            if not decision.admitted:
                continue
            state.try_begin(op)
            pending.remove(op)
            operations[op] = dict(ready=dependency_ready[op],admitted=clock.now,finish=None,
                capacity_wait_cycles=clock.now-dependency_ready[op])
            lifecycle.append(dict(event="admit",operation=op,cycle=clock.now,used_bytes=state.used.copy()))
            submit_phase(op)
        if len(state.completed) == len(binding.plans):
            complete = True
            break
        if not clock.events and not network_callbacks:
            complete = False
            break
        if network is None:
            clock.advance()
        else:
            boundary = min(clock.events[0][0],cycle_limit) if clock.events else cycle_limit
            completed_tokens = network.advance(boundary)
            clock.now = network.now
            # Receive completions at a boundary precede local completions at
            # that boundary. Every later submission observes all prior cycles.
            for token in completed_tokens:
                network_callbacks.pop(token)()
            if not completed_tokens and clock.events and clock.events[0][0] == clock.now:
                clock.advance()
            if clock.now >= cycle_limit:
                raise TimeoutError("Target execution reached its declared cycle limit")
    blocked = {}
    for op in pending:
        decision = state.admission(op)
        blocked[op] = dict(missing_dependencies=decision.missing_dependencies,
                          shortage_bytes=decision.shortage_bytes)
    result = dict(complete=complete,application_cycles=clock.now if complete else None,
        stopped_cycle=clock.now,operations=operations,phases=phases,services=clock.records,
        resources=clock.resource_summary(),blocked=blocked,lifecycle=lifecycle,
        storage={k:v for k,v in state.snapshot().items() if k != "timing_evaluated"},
        peak_bytes=state.peak.copy(),timing_evaluated=True,
        policy=dict(admission="stable topological order; atomic whole-operation capacity",
            arbitration="nonpreemptive FCFS at each resource; latency follows serialization",
            network="minimum-hop lexicographic route; whole-message store-and-forward",
            within_phase="demands in declared order",time="integer cycles; rational rates rounded up"))
    if network is not None:
        result["network_backend"] = "booksim"
        result["network_messages"] = sorted(network.messages,key=lambda m:m["id"])
        result["policy"]["network"] = "live BookSim; all-flit reception at end-of-cycle boundary"
        result["policy"]["ties"] = "network completions before local completions at the same boundary"
    return result
