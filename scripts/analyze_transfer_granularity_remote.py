"""Independent readback; no application simulation is launched."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess
from wafer_sim.analysis.transfer_study import analyze
from wafer_sim.io import digest,write_json


def plot(summary,path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    if 'pipeline_cycles' in summary['rows'][0]:
        fig,axes=plt.subplots(1,3,figsize=(11,3.6),layout='constrained')
        rows=summary['rows'];x=list(range(len(rows)))
        comparisons=[('Application completion','application_ape_percent','pipeline_application_ape_percent'),
            ('Isolated service: worst case',None,'pipeline_isolated_max_ape_percent'),
            ('Application messages: worst case','coarse_message_max_ape_percent','pipeline_message_max_ape_percent')]
        for ax,(title,old,new) in zip(axes,comparisons):
            original=[r[old] if old else r['isolated']['max_matched_ape_percent'] for r in rows]
            ax.bar([v-.18 for v in x],original,.36,color='#247BA0',label='Whole message')
            ax.bar([v+.18 for v in x],[r[new] for r in rows],.36,color='#D35E32',label='Packet pipeline')
            ax.set(xticks=x,xticklabels=[r['case'] for r in rows],title=title,ylabel='Absolute percentage error (%)')
            ax.grid(axis='y',alpha=.2)
        axes[0].legend(frameon=False)
        fig.savefig(path,dpi=180);plt.close(fig);return
    fig,axes=plt.subplots(1,2,figsize=(9,3.6),layout='constrained')
    colors={'s16':'#247BA0','s64':'#D35E32'}
    for case in ('s16','s64'):
        points=sorted({(r['physical_links'],r['error_cycles']) for r in summary['isolated_transfers']
                       if r['case']==case and r['matched_path']})
        axes[0].plot([p[0] for p in points],[p[1] for p in points],marker='o',color=colors[case],label=case)
    axes[0].set(xlabel='Physical links on matched path',ylabel='Coarse minus native service (cycles)',
                title='Isolated complete transfers')
    axes[0].legend(frameon=False);axes[0].grid(alpha=.2)
    rows=summary['rows'];x=list(range(len(rows)))
    axes[1].bar([v-.18 for v in x],[r['application_ape_percent'] for r in rows],.36,
                color='#247BA0',label='Application APE')
    axes[1].bar([v+.18 for v in x],[r['isolated']['max_matched_ape_percent'] for r in rows],.36,
                color='#D35E32',label='Max isolated service APE')
    axes[1].set(xticks=x,xticklabels=[r['case'] for r in rows],ylabel='Absolute percentage error (%)',
                title='Accuracy depends on the predicted quantity')
    axes[1].legend(frameon=False);axes[1].grid(axis='y',alpha=.2)
    fig.savefig(path,dpi=180);plt.close(fig)


def main():
    if platform.node().split('.')[0]!='eex005': raise SystemExit('Run on eex005')
    parser=argparse.ArgumentParser();parser.add_argument('run',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']): raise ValueError('Clean analysis source required')
    if not args.output.is_absolute(): raise ValueError('Fresh absolute output required')
    args.output.mkdir(exist_ok=False)
    summary,details,acceptance=analyze(args.run)
    write_json(args.output/'SUMMARY.json',summary)
    write_json(args.output/'DETAILS.json',details)
    write_json(args.output/'ACCEPTANCE.json',acceptance)
    fields=('case','sequence','reference_cycles','coarse_cycles','error_cycles','application_ape_percent',
            'application_target_met','complete_operations','message_count','logical_message_bytes','native_flits','peak_region_bytes')
    if 'pipeline_cycles' in summary['rows'][0]:
        fields+=('pipeline_cycles','pipeline_application_ape_percent','pipeline_isolated_max_ape_percent',
            'pipeline_message_mape_percent','pipeline_message_max_ape_percent','pipeline_application_target_met','pipeline_isolated_target_met')
        messages=[dict(case=case,context=context,**row) for case,detail in details.items()
            for context,rows in [('application',detail['pipeline']['messages']),('isolated',detail['pipeline']['isolated_messages'])] for row in rows]
        with (args.output/'pipeline_messages.csv').open('w') as f:
            w=csv.DictWriter(f,list(messages[0]));w.writeheader();w.writerows(messages)
        residuals={case:detail['pipeline']['residual'] for case,detail in details.items()}
        write_json(args.output/'RESIDUAL.json',residuals)
        events=[dict(case=case,**row) for case,r in residuals.items() if r and r['first_link_divergence']
                for rows in r['events'].values() for row in rows]
        if events:
            with (args.output/'shared_link_order.csv').open('w') as f:
                w=csv.DictWriter(f,list(events[0]));w.writeheader();w.writerows(events)
    with (args.output/'application.csv').open('w') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(summary['rows'])
    fields=('case','source','destination','bytes','flits','physical_links','matched_path','reference_cycles',
            'coarse_cycles','error_cycles','absolute_percentage_error','serialization_cycles','latency_cycles',
            'first_injection_wait_cycles','injection_span_cycles','ejection_span_cycles','first_flit_completion_boundary')
    with (args.output/'isolated.csv').open('w') as f:
        w=csv.DictWriter(f,fields,extrasaction='ignore');w.writeheader();w.writerows(summary['isolated_transfers'])
    with (args.output/'cost.csv').open('w') as f:
        fields=('case','mode','backend','metric','median','minimum','maximum','samples')
        w=csv.DictWriter(f,fields);w.writeheader()
        for row in summary['costs']:
            for metric,values in row['metrics'].items():
                w.writerow(dict(case=row['case'],mode=row['mode'],backend=row['backend'],metric=metric,**values))
    plot(summary,args.output/'accuracy.png')
    write_json(args.output/'ANALYZED.json',dict(passed=True,host=platform.node(),
        analysis_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        input_manifest_sha256=acceptance['complete_manifest_sha256'],
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
    print([(r['case'],r['reference_cycles'],r['coarse_cycles'],r['isolated']) for r in summary['rows']])
    print('Readback passed:',acceptance['checked_artifact_count'],'artifacts,',acceptance['repeated_full_executions'],'complete executions')


if __name__=='__main__': main()
