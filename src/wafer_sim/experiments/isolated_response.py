"""Small native-only isolation study, with frozen physical and execution code."""
import argparse
from dataclasses import asdict
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.adapters.wafer_machine import compile_machine, export_booksim
from wafer_sim.architecture.wafer_machine import from_config
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.isolated_response import progress
from wafer_sim.execution.plan import Transfer
from wafer_sim.experiments.wafer_machine import replay
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server

REPO=Path(__file__).resolve().parents[3]
FROZEN=['src/wafer_sim/execution','src/wafer_sim/architecture','src/wafer_sim/workloads',
        'src/wafer_sim/adapters','patches','third_party','configs/wafer_machine.json']


def machine(side,reg):
    cfg=read_json(REPO/reg['machine']);cfg['array']=[side,side]
    return compile_machine(from_config(cfg))


def semantic_config(path):
    values={}
    for line in path.read_text().splitlines():
        if '=' in line:
            k,v=line.split('=',1);values[k.strip()]=v.strip().removesuffix(';')
    for k in ('trace_file','trace_report'): values.pop(k)
    return values


def cases(accepted,reg):
    done=read_json(accepted/'COMPLETE.json');saved=read_json(REPO/'docs/results/spatial-scaling-001/COMPLETE.json')
    if done!=saved or not done['complete'] or (accepted/'FAILED.json').exists(): raise ValueError('Unaccepted background evidence')
    backgrounds={};identities={};descriptors=[]
    side=reg['isolated_array_side'];c=machine(side,reg)
    for h in reg['c2c_hops']:
        path=[c.router_ids['m0']]+[c.router_ids[f'c{r*side}'] for r in range(h+1)]
        descriptors.append(dict(name=f'distance-{h}',kind='distance',side=side,c2c_hops=h,
            source_memory=reg['source_bank'],destination_memory=f'sram-{h*side}',ready=0,token='response',data='response',path=path))
    for item in reg['matched_messages']:
        side=item['side'];prefix=f'{side}-remote_balanced-S-rep-0'
        if side not in backgrounds:
            names=[f'{prefix}/execution.json',f'{prefix}/critical_chain.json',
                f'{prefix}/rapidchiplet/booksim2/src/rc_configs/network.conf',
                f'{prefix}/rapidchiplet/booksim2/src/rc_topologies/network.anynet']
            for name in names:
                sha=digest(accepted/name)
                if sha!=done['artifacts_sha256'][name]:raise ValueError('Background hash mismatch')
                identities[name]=sha
            backgrounds[side]=read_json(accepted/names[0])
        result=backgrounds[side];m=next(m for m in result['network_messages'] if m['token']==item['token'])
        chain=read_json(accepted/f'{prefix}/critical_chain.json')
        if m['bytes']!=reg['payload_bytes'] or item['token'] not in {s.get('token') for s in chain['segments']}:
            raise ValueError('Probe is not the registered critical response')
        paths={tuple(f['router_path']) for f in m['flits']}
        if len(paths)!=1:raise ValueError('Matched route is not unique')
        path=list(next(iter(paths)))
        if not m['source_memory'].startswith('dram-') or not m['destination_memory'].startswith('sram-'):
            raise ValueError('Expected complete DRAM response')
        descriptors.append(dict(name=f"matched-{side}-"+item['token'].split('/')[0],kind='matched',side=side,
            c2c_hops=len(path)-2,source_memory=m['source_memory'],destination_memory=m['destination_memory'],
            ready=m['ready'],token=item['token'],data=m['data'],path=path))
    return descriptors,backgrounds,identities


def run(output,accepted,tests):
    root=require_active_server();reg=read_json(REPO/'configs/isolated_response.json')
    if not output.is_absolute() or output.exists():raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain']):raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    if subprocess.check_output(['git','-C',str(REPO),'diff',reg['frozen_commit'],'--name-only','--',*FROZEN]):
        raise ValueError('Frozen machine/network/execution changed')
    receipt=read_json(tests)
    if (not receipt['passed'] or receipt['source_commit']!=commit or 'test_isolated_response' not in receipt['modules']
            or digest(receipt['tests_log'])!=receipt['tests_log_sha256']):raise ValueError('Same-source passing tests required')
    binary=root/'build/booksim-online/online_booksim'
    expected=read_json(REPO/'docs/results/spatial-scaling-001/STARTED.json')['binary_sha256']
    if digest(binary)!=expected:raise ValueError('Native binary changed')
    descriptors,_,identities=cases(accepted,reg)
    config=accepted/'6-remote_balanced-S-rep-0/rapidchiplet/booksim2/src/rc_configs/network.conf'
    semantics=semantic_config(config)
    sys.path.insert(0,str(REPO/'third_party/nw-design-for-wsi'))
    output.mkdir();write_json(output/'CASES.json',descriptors)
    write_json(output/'STARTED.json',dict(source_commit=commit,registration=reg,host=platform.node(),
        python=sys.version,packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        accepted_root=str(accepted),accepted_sources=identities,binary_sha256=expected,tests=receipt,
        frozen_paths=FROZEN,semantic_network_config=semantics,
        source_hashes={str(p.relative_to(REPO)):digest(p) for p in [*sorted((REPO/'src').rglob('*.py')),
            REPO/'configs/isolated_response.json',REPO/reg['machine'],REPO/'docs/ISOLATED_RESPONSE_PROTOCOL.md']}))
    try:
        rows=[]
        for desc in descriptors:
            c=machine(desc['side'],reg);hashes=set()
            for rep in range(reg['repetitions']):
                directory=output/f"{desc['name']}-rep-{rep}";directory.mkdir()
                conf=export_booksim(c,directory,reg['seed'])
                if semantic_config(conf)!=semantics:raise ValueError('Changed router/link policy')
                oldtop=accepted/f"{desc['side']}-remote_balanced-S-rep-0/rapidchiplet/booksim2/src/rc_topologies/network.anynet"
                if digest(conf.parent.parent/'rc_topologies/network.anynet')!=digest(oldtop):raise ValueError('Changed physical graph')
                write_json(directory/'INPUT.json',dict(machine=asdict(c.physical),response=desc,bytes=reg['payload_bytes']))
                client=OnlineBookSim(binary,conf,directory,flit_bytes=c.physical.flit_bytes)
                try:
                    client.advance(desc['ready'])
                    t=Transfer(desc['data'],desc['source_memory'],desc['destination_memory'],
                        c.endpoints[desc['source_memory']],c.endpoints[desc['destination_memory']],reg['payload_bytes'])
                    client.submit(desc['token'],t,desc['ready'])
                    limit=desc['ready']+reg['cycle_budget']
                    while client.pending and client.now<limit:client.advance(limit)
                    if client.pending:raise TimeoutError('Isolated response did not complete')
                    record=client.close()
                finally:client.abort()
                if len(record['messages'])!=1:raise ValueError('Other traffic entered isolation')
                checked=audit_messages(c.target.network,record['messages']);m=record['messages'][0];p=progress(m)
                if any(r['routers']!=desc['path'] for r in p['routes']):raise ValueError('Unexpected actual route')
                hashes.add(object_digest(m));write_json(directory/'AUDIT.json',checked);write_json(directory/'PROGRESS.json',p)
                rows.append(dict(name=desc['name'],repetition=rep,**p));print(desc['name'],rep,p['duration'],p['injection_span'],flush=True)
            if len(hashes)!=1:raise ValueError('Repeated native events differ')
            first=output/f"{desc['name']}-rep-0";replay(c,binary,first,first/'replay',reg['seed'])
        write_json(output/'SUMMARY.json',rows)
        write_json(output/'COMPLETE.json',dict(complete=True,source_commit=commit,conditions=len(descriptors),responses=len(rows),
            native_replays=len(descriptors),scope=reg['scope'],artifacts_sha256={str(p.relative_to(output)):digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    except BaseException as exc:
        write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc)));raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--accepted',required=True,type=Path);p.add_argument('--tests',required=True,type=Path)
    a=p.parse_args();run(a.output,a.accepted,a.tests)
