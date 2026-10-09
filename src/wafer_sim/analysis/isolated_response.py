"""Full-flit response progress and temporal sharing; no new timing model."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import subprocess

from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.memory_abstraction_study import csv_file
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server


def progress(message):
    flits = sorted(message['flits'], key=lambda f:f['id'])
    n = len(flits); size = message['bytes']; width = message['flit_bytes']
    if n < 4 or n*width != size or n != message['expected_flits']:
        raise ValueError('Registered whole-flit long response required')
    injections = [f['injected'] for f in flits]
    if any(b <= a for a,b in zip(injections,injections[1:])):
        raise ValueError('Single-source flit identity/order mismatch')
    span = injections[-1]-injections[0]
    lo,hi = n//4,3*n//4
    paths = Counter(tuple(f['router_path']) for f in flits)
    return dict(bytes=size, flits=n, ready=message['ready'],
        first_inject_wait=injections[0]-message['ready'], injection_span=span,
        first_receive_boundary=message['first_eject']+1,
        last_receive_boundary=message['last_eject']+1,
        first_receive_latency=message['first_eject']+1-message['ready'],
        duration=message['finish']-message['ready'],
        tail_after_last_inject=message['finish']-injections[-1],
        injection_bytes_per_cycle=size/(span+1),
        middle_half_injection_bytes_per_cycle=(hi-lo)*width/(injections[hi]-injections[lo]),
        completion_bytes_per_cycle=size/(message['finish']-message['ready']),
        unused_injection_slots=span+1-n,
        injection_gap_histogram=dict(Counter(b-a for a,b in zip(injections,injections[1:]))),
        routes=[dict(routers=list(p),flits=count) for p,count in sorted(paths.items())])


def shared_windows(target, messages):
    """Other flits actually using each directed edge during this message's use."""
    own = defaultdict(list); peer = defaultdict(list)
    for m in messages:
        dest = own if m['token'] == target['token'] else peer
        for f in m['flits']:
            for e in f['link_arrivals']:
                dest[e['source'],e['destination']].append((e['cycle'],m['token']))
    rows=[]
    for (a,b),events in sorted(own.items()):
        begin,end = min(t for t,_ in events),max(t for t,_ in events)
        others = Counter(token for t,token in peer[a,b] if begin <= t <= end)
        count = len(events)+sum(others.values())
        if count > end-begin+1: raise ValueError('More than one flit per directed link/cycle')
        rows.append(dict(source=a,destination=b,first_arrival=begin,last_arrival=end,
            own_flits=len(events),other_flits=sum(others.values()),peer_messages=dict(others),
            window_flits_per_cycle=count/(end-begin+1)))
    return rows


def analyze(root, output):
    from wafer_sim.experiments.isolated_response import REPO, cases, machine, semantic_config
    require_active_server()
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']): raise ValueError('Clean analysis source required')
    done,start = read_json(root/'COMPLETE.json'),read_json(root/'STARTED.json')
    if not done['complete'] or (root/'FAILED.json').exists(): raise ValueError('Incomplete experiment')
    reg = read_json(REPO/'configs/isolated_response.json')
    if reg != start['registration']: raise ValueError('Changed registration')
    for name,sha in done['artifacts_sha256'].items():
        if digest(root/name)!=sha: raise ValueError('Changed artifact '+name)
    for name,sha in start['source_hashes'].items():
        if digest(REPO/name)!=sha: raise ValueError('Changed source '+name)
    descriptors, backgrounds, identities = cases(Path(start['accepted_root']),reg)
    if object_digest(identities) != object_digest(start['accepted_sources']): raise ValueError('Changed accepted source identity')
    rows, comparisons, shared = [],[],[]; full_checks=0
    for desc in descriptors:
        compiled = machine(desc['side'],reg)
        hashes=set()
        for rep in range(reg['repetitions']):
            d=root/f"{desc['name']}-rep-{rep}"; record=read_json(d/'online_network.json')
            if not record['complete'] or not record['final']['drained'] or len(record['messages'])!=1:
                raise ValueError('Probe is incomplete or has other traffic')
            checked=audit_messages(compiled.target.network,record['messages'])
            if checked!=read_json(d/'AUDIT.json'): raise ValueError('Independent network audit differs')
            m=record['messages'][0]; p=progress(m)
            if (m['bytes']!=reg['payload_bytes'] or m['source_memory']!=desc['source_memory'] or
                m['destination_memory']!=desc['destination_memory'] or m['ready']!=desc['ready'] or
                m['source']!=compiled.endpoints[desc['source_memory']] or m['destination']!=compiled.endpoints[desc['destination_memory']]):
                raise ValueError('Changed message identity')
            if any(route['routers']!=desc['path'] for route in p['routes']): raise ValueError('Unexpected actual path')
            if p!=read_json(d/'PROGRESS.json'): raise ValueError('Progress metrics differ')
            config=d/'rapidchiplet/booksim2/src/rc_configs/network.conf'
            if semantic_config(config)!=start['semantic_network_config']: raise ValueError('Changed network policy')
            if record['identity']['binary_sha256']!=start['binary_sha256'] or record['identity']['config_sha256']!=digest(config):
                raise ValueError('Changed native identity')
            hashes.add(object_digest(m));full_checks+=1
        if len(hashes)!=1: raise ValueError('Unstable isolated timing')
        replay=read_json(root/f"{desc['name']}-rep-0/replay/REPLAY.json")
        if not replay['passed'] or replay['binary_sha256']!=start['binary_sha256']: raise ValueError('Native replay failed')
        row=dict(name=desc['name'],kind=desc['kind'],side=desc['side'],c2c_hops=desc['c2c_hops'],**p)
        rows.append(row)
        if desc['kind']=='matched':
            original=next(m for m in backgrounds[desc['side']]['network_messages'] if m['token']==desc['token'])
            before=progress(original)
            if before['routes']!=p['routes']: raise ValueError('Background changed physical path in matched comparison')
            comparisons.append(dict(name=desc['name'],side=desc['side'],token=desc['token'],
                original_duration=before['duration'],isolated_duration=p['duration'],
                background_duration_excess=before['duration']-p['duration'],
                original_injection_span=before['injection_span'],isolated_injection_span=p['injection_span'],
                background_injection_span_excess=before['injection_span']-p['injection_span'],
                original_middle_half_rate=before['middle_half_injection_bytes_per_cycle'],
                isolated_middle_half_rate=p['middle_half_injection_bytes_per_cycle'],
                original_first_wait=before['first_inject_wait'],isolated_first_wait=p['first_inject_wait'],
                original_tail=before['tail_after_last_inject'],isolated_tail=p['tail_after_last_inject']))
            for link in shared_windows(original,backgrounds[desc['side']]['network_messages']):
                shared.append(dict(name=desc['name'],side=desc['side'],**link))
    output.mkdir()
    csv_file(output/'isolated.csv',[{k:v for k,v in r.items() if k not in {'routes','injection_gap_histogram'}} for r in rows])
    csv_file(output/'matched.csv',comparisons)
    csv_file(output/'shared_windows.csv',[{k:v for k,v in r.items() if k!='peer_messages'} for r in shared])
    write_json(output/'SUMMARY.json',dict(rows=rows,comparisons=comparisons,shared_windows=shared))
    plot(output,rows,comparisons)
    write_json(output/'VERIFIED.json',dict(passed=True,full_response_readbacks=full_checks,
        artifact_hashes_checked=len(done['artifacts_sha256']),native_replays=len(descriptors),
        source_commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip(),
        run_manifest_sha256=digest(root/'COMPLETE.json'),accepted_sources_rechecked=True,
        artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    print(dict(rows=rows,comparisons=comparisons),flush=True)


def plot(output,rows,comparisons):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'svg.fonttype':'none','font.size':10})
    fig,axes=plt.subplots(1,2,figsize=(10,3.7))
    a=[r for r in rows if r['kind']=='distance']
    for key,label in (('duration','Complete response'),('injection_span','Injection span'),('first_receive_latency','First receive')):
        axes[0].plot([r['c2c_hops'] for r in a],[r[key] for r in a],'o-',label=label)
    axes[0].set_xlabel('C2C hops (+ one HB link)');axes[0].set_ylabel('Cycles');axes[0].legend()
    for offset,key,label in ((-.18,'isolated_injection_span','Isolated'),(.18,'original_injection_span','Full-work background')):
        axes[1].bar([i+offset for i in range(len(comparisons))],[r[key] for r in comparisons],width=.34,label=label)
    axes[1].set_xticks(range(len(comparisons)),['4×4 first','4×4 second','6×6 first','6×6 second'])
    axes[1].set_ylabel('Injection span (cycles)');axes[1].legend()
    fig.tight_layout();fig.savefig(output/'mechanism.svg');fig.savefig(output/'mechanism.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();analyze(a.root,a.output)
