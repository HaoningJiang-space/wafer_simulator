"""Re-audit every arm; independently replay native endpoint command streams."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.boundary_study import analyze,replay
from wafer_sim.experiments.memory_boundary import prepare
from wafer_sim.io import read_json,write_json,digest,object_digest


def table(path,rows):
    with path.open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    if platform.node().split('.')[0]!='eex005':raise SystemExit('Run on eex005')
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    if not a.output.is_absolute():raise ValueError('Fresh absolute output')
    a.output.mkdir(exist_ok=False);result=analyze(a.run)
    replay_records=[]
    for launch in read_json(a.run/'LAUNCHES.json'):
        if launch['repeat']!=0:continue
        d=read_json(Path(launch['worker']).parent/'INPUT_CONFIG.json');_,_,export,_=prepare(d)
        check=replay(Path(launch['worker']),d,export,a.output/f"replay-{launch['case']}-{launch['mode']}")
        replay_records.append(dict(case=launch['case'],mode=launch['mode'],**check))
    result['acceptance']['endpoint_replays']=replay_records
    unchanged={}
    prior=Path('/home/wangziheng/wafer_simulator/runs/transfer-granularity-001')
    for case in ('s16','s64'):
        old=read_json(prior/case/'cold-0-booksim/trial-0/execution.json')
        new=read_json(a.run/case/'serial-0/execution.json')
        unchanged[case]=dict(exact_events=object_digest(old)==object_digest(new),
            old_cycles=old['application_cycles'],new_cycles=new['application_cycles'],
            old_event_sha256=object_digest(old),new_event_sha256=object_digest(new))
        if not unchanged[case]['exact_events']:raise ValueError('Serial compatibility changed accepted events')
    result['acceptance']['serial_compatibility']=unchanged
    for key,name in (('rows','application.csv'),('messages','messages.csv'),('costs','cost.csv'),('source_windows','source_windows.csv')):table(a.output/name,result[key])
    write_json(a.output/'SUMMARY.json',{k:v for k,v in result.items() if k not in ('messages','costs','acceptance')})
    write_json(a.output/'ACCEPTANCE.json',result['acceptance'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4),layout='constrained')
    colors=['#777777','#3388bb','#d68135'];modes=['serial','pipeline','bounded']
    for i,mode in enumerate(modes):
        cycles=[next(r['application_cycles'] for r in result['rows'] if r['case']==c and r['mode']==mode) for c in ('s16','s64')]
        axes[0].bar([j+(i-1)*.24 for j in range(2)],cycles,.24,label=mode,color=colors[i])
    axes[0].set_xticks([0,1],['s16','s64']);axes[0].set_ylabel('Application cycles');axes[0].legend()
    for i,mode in enumerate(modes[1:],1):
        r=read_json(a.run/'s64'/f'{mode}-0/execution.json')
        rows=[e for e in r['boundary']['events'] if e['destination']==0 and e['event'] in ('receive','commit')]
        axes[1].step([0]+[e['cycle'] for e in rows],[0]+[e['rx_slots'] for e in rows],where='post',label=mode,color=colors[i])
    axes[1].axhline(8,color='black',linestyle='--',label='8-slot capacity')
    axes[1].set_xlabel('Simulated cycle (s64)');axes[1].set_ylabel('Root receive slots occupied');axes[1].legend()
    fig.savefig(a.output/'boundary.png',dpi=160);plt.close(fig)
    write_json(a.output/'ANALYZED.json',dict(passed=True,host=platform.node(),
        analysis_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        input_manifest_sha256=digest(a.run/'COMPLETE.json'),
        artifacts_sha256={str(f.relative_to(a.output)):digest(f) for f in sorted(a.output.rglob('*')) if f.is_file()}))
    print([(r['case'],r['mode'],r['application_cycles'],r['ape']) for r in result['rows']])
    print('verified',result['acceptance']['checked_artifact_count'],'artifacts; replays',len(replay_records))

if __name__=='__main__':main()
