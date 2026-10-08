"""Frozen-worker design comparison; orchestration and result presentation only."""
import argparse
import csv
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from wafer_sim.adapters.wow import export_placement
from wafer_sim.experiments.memory_boundary import prepare, worker
from wafer_sim.io import read_json, write_json, digest, object_digest


def _remote():
    if platform.node().split('.')[0]!='eex005':raise SystemExit('Run on eex005')


def _frozen(repo):
    paths=['src/wafer_sim/'+p for p in ('architecture','adapters','execution','workloads')]
    paths += ['third_party','patches']
    return {p:subprocess.check_output(['git','rev-parse','HEAD:'+p],cwd=repo,text=True).strip() for p in paths}


def run(output, tests, cpus=None):
    _remote();repo=Path(__file__).resolve().parents[3];runtime=repo.parent
    output=Path(output);tests=Path(tests)
    if subprocess.check_output(['git','status','--porcelain'],cwd=repo):raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()
    receipt=read_json(tests)
    if not receipt['passed'] or receipt['source_commit']!=commit or digest(receipt['tests_log'])!=receipt['tests_log_sha256']:
        raise ValueError('Same-source tests required')
    if not output.is_absolute():raise ValueError('Fresh absolute output required')
    reg=read_json(repo/'configs/boundary_design.json');prior=Path(reg['accepted_run'])
    old=read_json(prior/'COMPLETE.json');start=read_json(prior/'STARTED.json')
    if not old['all_registered_work_complete']:raise ValueError('Accepted run incomplete')
    for name,h in old['artifacts_sha256'].items():
        if digest(prior/name)!=h:raise ValueError('Changed accepted artifact: '+name)
    binaries={n:digest(runtime/path) for n,path in {
        'boundary':'build/booksim-boundary/endpoint_booksim',
        'accepted_online':'build/booksim-online/online_booksim',
        'standalone':'build/booksim/rapidchiplet/booksim2/src/booksim'}.items()}
    if binaries!=start['binaries']:raise ValueError('Native binaries changed')
    cpus=sorted(os.sched_getaffinity(0))[-2:] if cpus is None else cpus
    if len(set(cpus))!=2 or not set(cpus)<=os.sched_getaffinity(0):raise ValueError('Two allowed CPUs required')
    output.mkdir(exist_ok=False)
    controls=dict(start['registration']);controls.pop('isolation',None);controls.pop('placement',None)
    controls['design_study']=reg
    write_json(output/'STARTED.json',dict(source_commit=commit,host=platform.node(),python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),registration=controls,
        binaries=binaries,accepted_manifest_sha256=digest(prior/'COMPLETE.json'),
        tests_sha256=digest(tests),affinity=cpus,load=os.getloadavg(),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        frozen_trees=_frozen(repo),source_hashes={str(f.relative_to(repo)):digest(f) for f in
            [*sorted((repo/'src').rglob('*.py')),repo/'configs/boundary_design.json',repo/'docs/BOUNDARY_DESIGN_PROTOCOL.md']},
        build_source=start['build_source'],build_manifest_sha256=start['build_manifest_sha256']))
    launches=[];compatibility={};geometry={}
    try:
        template=read_json(prior/'s16__request_atomic/INPUT_CONFIG.json')
        for placement in reg['placements']:
            dest=output/'geometry'/placement;t0=time.perf_counter()
            export_placement(runtime/'upstream/nw-design-for-wsi',dest,placement,
                template['experiment']['wafer_diameter_mm'],template['experiment']['wafer_utilization'])
            exported=read_json(dest/'network.json')
            if placement=='baseline' and exported!=read_json(template['network_json']):
                raise ValueError('Baseline geometry changed')
            geometry[placement]=dict(directory=str(dest),export_wall_seconds=time.perf_counter()-t0,
                network_sha256=digest(dest/'network.json'),resources=exported['resources'])
        write_json(output/'GEOMETRY.json',geometry)
        for policy in reg['contracts']:
            for shape in reg['cases']:
                for placement in reg['placements']:
                    case='__'.join((shape,policy,placement));base=output/case;base.mkdir()
                    d=read_json(prior/(shape+'__'+policy)/'INPUT_CONFIG.json')
                    d['geometry_directory']=geometry[placement]['directory']
                    d['network_json']=str(Path(d['geometry_directory'])/'network.json')
                    d['boundary']['placement']=placement
                    write_json(base/'INPUT_CONFIG.json',d)
                    _,_,exported,identity=prepare(d)
                    endpoints={e['node']:e for e in exported['endpoints']}
                    write_json(base/'MANIFEST.json',dict(
                        target=dict(placement=placement,resources=exported['resources'],
                            local_resources=identity['resource_contract']['compute_memory_parameters'],
                            boundary=d['boundary'],memory_quantum_bytes=d.get('memory_quantum_bytes'),
                            execution_policy=d['experiment']['execution_policy'],
                            worker_endpoints=identity['worker_endpoints'],
                            worker_locations=[endpoints[e] for e in identity['worker_endpoints']],
                            network_sha256=digest(d['network_json'])),
                        abstractions=dict(network='native_booksim',boundary_models=reg['modes']),
                        implementation=dict(source_commit=commit,binaries=binaries,affinity=cpus,
                            logging='full',measurement='cold subprocess; separate graph/init/execute/serialize/audit'),
                        input_identity=object_digest(identity),
                        logical_workload_identity=object_digest(identity['logical_workload'])))
                # Same implementation and batch: alternate placement and rotate mode order.
                for repeat in range(reg['repetitions']):
                    modes=reg['modes'][repeat:]+reg['modes'][:repeat]
                    places=reg['placements'][repeat%2:]+reg['placements'][:repeat%2]
                    for mode in modes:
                        for placement in places:
                            case='__'.join((shape,policy,placement));base=output/case
                            dest=base/f'{mode}-{repeat}';t0=time.perf_counter();load=os.getloadavg()
                            command=[sys.executable,'-m','wafer_sim.experiments.boundary_design',str(dest),
                                '--worker',str(base/'INPUT_CONFIG.json'),'--mode',mode,'--cpus',','.join(map(str,cpus))]
                            with (base/f'{mode}-{repeat}.log').open('w') as log:
                                p=subprocess.run(command,cwd=repo,stdout=log,stderr=subprocess.STDOUT,timeout=300)
                            if p.returncode:raise RuntimeError('Worker failed: '+str(dest))
                            measured=read_json(dest/'MEASURED.json')
                            if measured['input_identity']!=read_json(base/'MANIFEST.json')['input_identity']:
                                raise ValueError('Worker changed declared input')
                            if placement=='baseline':
                                accepted=read_json(prior/(shape+'__'+policy)/(mode+'-0')/'MEASURED.json')
                                if measured['execution_identity']!=accepted['execution_identity'] or measured['input_identity']!=accepted['input_identity']:
                                    raise ValueError('Baseline input or full-event compatibility failed')
                                compatibility[case+'/'+mode]=dict(exact_events=True,sha256=accepted['execution_identity'])
                            launches.append(dict(case=case,shape=shape,contract=policy,placement=placement,
                                mode=mode,repeat=repeat,worker=str(dest),worker_wall_seconds=time.perf_counter()-t0,
                                load_before=load,load_after=os.getloadavg()))
                            write_json(output/'LAUNCHES.json',launches)
                            print(case,mode,repeat,measured['application_cycles'],flush=True)
        for case in {r['case'] for r in launches}:
            for mode in reg['modes']:
                records=[read_json(Path(r['worker'])/'MEASURED.json') for r in launches if r['case']==case and r['mode']==mode]
                if len(records)!=reg['repetitions'] or len({r['execution_identity'] for r in records})!=1:
                    raise ValueError('Missing or divergent repetition')
        write_json(output/'COMPATIBILITY.json',compatibility)
        write_json(output/'COMPLETE.json',dict(source_commit=commit,all_registered_work_complete=True,
            artifacts_sha256={str(f.relative_to(output)):digest(f) for f in sorted(output.rglob('*')) if f.is_file()}))
    except BaseException as error:
        write_json(output/'FAILED.json',dict(type=type(error).__name__,message=str(error)));raise


def analyze_run(root, output):
    _remote();root=Path(root);output=Path(output)
    if not output.is_absolute():raise ValueError('Fresh absolute output required')
    output.mkdir(exist_ok=False)
    if _frozen(Path(__file__).resolve().parents[3])!=read_json(root/'STARTED.json')['frozen_trees']:
        raise ValueError('Frozen model source changed since run')
    from wafer_sim.analysis.boundary_design import analyze
    from wafer_sim.analysis.boundary_study import replay
    result=analyze(root);checks=[]
    for launch in read_json(root/'LAUNCHES.json'):
        if launch['repeat']!=0:continue
        directory=Path(launch['worker']);d=read_json(directory.parent/'INPUT_CONFIG.json')
        _,_,exported,_=prepare(d)
        check=replay(directory,d,exported,output/('replay-'+launch['case']+'-'+launch['mode']))
        checks.append(dict(case=launch['case'],mode=launch['mode'],**check))
    result['acceptance']['endpoint_replays']=checks
    for key,name in (('rows','cells'),('decision_table','model_decision_table'),('messages','messages'),
                     ('costs','cost'),('source_windows','source_windows'),('attribution','attribution'),
                     ('paired_messages','paired_messages')):
        with (output/(name+'.csv')).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(result[key][0]));writer.writeheader();writer.writerows(result[key])
    write_json(output/'SUMMARY.json',{k:result[k] for k in ('rows','decision_table')})
    write_json(output/'ACCEPTANCE.json',result['acceptance'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(9,4),layout='constrained');rows=result['decision_table']
    colors={'serial':'#777777','pipeline':'#3388bb','bounded':'#d68135'}
    for i,mode in enumerate(colors):
        ax.bar([j+(i-1)*.24 for j in range(len(rows))],[r[mode+'_gap_cycles'] for r in rows],.24,label=mode,color=colors[mode])
    ax.axhspan(-100,100,color='gray',alpha=.12,label='100-cycle indifference band')
    ax.axhline(0,color='black',linewidth=.6);ax.set_ylabel('Baseline - Rotated (cycles); positive favors Rotated')
    ax.set_xticks(range(len(rows)),[r['shape']+'\n'+r['memory_policy'] for r in rows]);ax.legend()
    fig.savefig(output/'design_gap.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    for ax,placement in zip(axes,('baseline','ours_rotated')):
        for i,mode in enumerate(colors):
            vals=[next(c for c in result['costs'] if c['shape']==r['shape'] and c['contract']==r['memory_policy']
                and c['placement']==placement and c['mode']==mode and c['phase']=='execution' and c['metric']=='wall_seconds') for r in rows]
            ax.bar([j+(i-1)*.24 for j in range(len(rows))],[v['median'] for v in vals],.24,label=mode,color=colors[mode],
                yerr=[[v['median']-v['minimum'] for v in vals],[v['maximum']-v['median'] for v in vals]],capsize=2)
        ax.set_title(placement);ax.set_xticks(range(len(rows)),[r['shape']+'\n'+r['memory_policy'] for r in rows])
        ax.set_ylabel('Execution wall seconds; median and range, 3 cold runs');ax.legend()
    fig.savefig(output/'execution_cost.png',dpi=160);plt.close(fig)
    write_json(output/'ANALYZED.json',dict(passed=True,host=platform.node(),
        analysis_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        input_manifest_sha256=digest(root/'COMPLETE.json'),
        artifacts_sha256={str(f.relative_to(output)):digest(f) for f in sorted(output.rglob('*')) if f.is_file()}))
    print(result['decision_table'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output',type=Path)
    p.add_argument('--tests',type=Path);p.add_argument('--analyze',type=Path)
    p.add_argument('--worker',type=Path);p.add_argument('--mode');p.add_argument('--cpus')
    a=p.parse_args();_remote()
    cpus=[int(x) for x in a.cpus.split(',')] if a.cpus else None
    if a.worker:worker(a.worker,a.mode,a.output,cpus)
    elif a.analyze:analyze_run(a.analyze,a.output)
    else:run(a.output,a.tests,cpus)


if __name__=='__main__':main()
