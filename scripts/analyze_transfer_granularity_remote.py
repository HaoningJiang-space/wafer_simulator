"""Independent readback; no application simulation is launched."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess
from wafer_sim.analysis.transfer_study import analyze
from wafer_sim.io import digest,write_json


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
    write_json(args.output/'ANALYZED.json',dict(passed=True,host=platform.node(),
        analysis_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        input_manifest_sha256=acceptance['complete_manifest_sha256'],
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))
    print([(r['case'],r['reference_cycles'],r['coarse_cycles'],r['isolated']) for r in summary['rows']])
    print('Readback passed:',acceptance['checked_artifact_count'],'artifacts,',acceptance['repeated_full_executions'],'complete executions')


if __name__=='__main__': main()
