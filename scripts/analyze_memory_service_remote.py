"""Audit all memory-contract cells, replay native protocols, plot model interaction."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.memory_service_study import analyze
from wafer_sim.analysis.boundary_study import replay
from wafer_sim.experiments.memory_boundary import prepare
from wafer_sim.io import read_json, write_json, digest


def main():
    if platform.node().split('.')[0]!='eex005':raise SystemExit('Run on eex005')
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    if not a.output.is_absolute():raise ValueError('Fresh absolute output')
    a.output.mkdir(exist_ok=False)
    result=analyze(a.run);checks=[]
    for launch in read_json(a.run/'LAUNCHES.json'):
        if launch['repeat']!=0:continue
        directory=Path(launch['worker']);d=read_json(directory.parent/'INPUT_CONFIG.json')
        _,_,exported,_=prepare(d)
        check=replay(directory,d,exported,a.output/('replay-'+launch['case']+'-'+launch['mode']))
        checks.append(dict(case=launch['case'],mode=launch['mode'],**check))
    result['acceptance']['endpoint_replays']=checks
    for key,name in (('rows','application.csv'),('messages','messages.csv'),('costs','cost.csv'),
                     ('source_windows','source_windows.csv'),('interactions','interaction.csv')):
        with (a.output/name).open('w') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(result[key][0]));writer.writeheader();writer.writerows(result[key])
    write_json(a.output/'SUMMARY.json',{k:v for k,v in result.items() if k not in ('messages','costs','acceptance')})
    write_json(a.output/'ACCEPTANCE.json',result['acceptance'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    for ax,shape in zip(axes,('s16','s64')):
        for mode,color in (('serial','#777777'),('pipeline','#3388bb'),('bounded','#d68135')):
            ys=[next(r['application_cycles'] for r in result['rows'] if r['shape']==shape and
                     r['mode']==mode and r['memory_contract']==c) for c in ('request_atomic','burst_256')]
            ax.plot([0,1],ys,marker='o',color=color,label=mode,linestyle='--' if mode=='bounded' else '-')
        ax.set_xticks([0,1],['request atomic','256 B bursts']);ax.set_ylabel('Application cycles');ax.set_title(shape)
        ax.legend()
    fig.savefig(a.output/'interaction.png',dpi=160);plt.close(fig)
    write_json(a.output/'ANALYZED.json',dict(passed=True,host=platform.node(),
        analysis_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        input_manifest_sha256=digest(a.run/'COMPLETE.json'),
        artifacts_sha256={str(f.relative_to(a.output)):digest(f) for f in sorted(a.output.rglob('*')) if f.is_file()}))
    print(result['interactions'])
    print('checked artifacts',result['acceptance']['checked_artifact_count'],'replays',len(checks))


if __name__=='__main__':main()
