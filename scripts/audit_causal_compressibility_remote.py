"""Read-only G1 state-pattern audit on hn072; no Native execution or batching."""
import argparse
import gzip
import subprocess
import time
from pathlib import Path
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json,digest,object_digest
from wafer_sim.analysis.causal_compressibility import observe,audit_patterns,encoded

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('campaign',type=Path);parser.add_argument('output',type=Path)
args=parser.parse_args();root=require_active_server();repo=Path(__file__).resolve().parents[1]
if not args.output.is_absolute() or not args.output.is_relative_to(root/'runs') or args.output.exists():
    raise ValueError('Fresh server audit output required')
if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']): raise ValueError('Clean main source required')
reg=read_json(repo/'configs/causal_compressibility.json')
if digest(repo/'configs/causal_closure.json')!=reg['g1_registration_sha256'] or digest(repo/'src/wafer_sim/adapters/causal_merge.py')!=reg['predictor_sha256']:
    raise ValueError('Changed G1 predictor or registered demand/contract')
g1=read_json(repo/'configs/causal_closure.json');manifest=read_json(args.campaign/'COMPLETE.json')
if not manifest['complete'] or not manifest['accuracy_passed'] or (args.campaign/'FAILED.json').exists():
    raise ValueError('Accepted G1 campaign required')
args.output.mkdir();source=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
files=['configs/causal_compressibility.json','src/wafer_sim/analysis/causal_compressibility.py','scripts/audit_causal_compressibility_remote.py','src/wafer_sim/adapters/causal_merge.py','src/wafer_sim/architecture/causal_merge.py']
write_json(args.output/'STARTED.json',dict(source_commit=source,source_hashes={p:digest(repo/p) for p in files},
    campaign_manifest_sha256=digest(args.campaign/'COMPLETE.json'),g1_campaign=str(args.campaign.resolve()),
    native_executions=0,skipped_cycles=0,compression_implemented=False))
rows=[]
try:
    for name in reg['cases']:
        case=next(c for c in g1['cases'] if c['name']==name);directory=args.output/name;directory.mkdir()
        original=args.campaign/name
        for filename in ('INPUT.json','PREDICTION.json'):
            if digest(original/filename)!=manifest['artifacts_sha256'][name+'/'+filename]: raise ValueError('Changed accepted G1 input/prediction')
        inp=read_json(original/'INPUT.json')
        expected=dict(contract=dict(g1['contract'],capacity_flits=case.get('capacity_flits',g1['contract']['capacity_flits'])),messages=case['messages'])
        if inp!=expected: raise ValueError('Changed external input')
        before=time.perf_counter();result,observer=observe(inp['contract'],inp['messages'],g1['cycle_limit'])
        capture_seconds=time.perf_counter()-before
        if object_digest(result)!=object_digest(read_json(original/'PREDICTION.json')): raise ValueError('Observation changed complete prediction')
        before=time.perf_counter();checked=audit_patterns(result,observer,reg['minimum_repetitions']);analysis_seconds=time.perf_counter()-before
        with gzip.open(directory/'STATES.jsonl.gz','wt') as stream:
            for row in observer.rows:stream.write(encoded(row)+'\n')
        checked.update(name=name,capacity_flits=inp['contract']['capacity_flits'],prediction_unchanged=True,
            input_sha256=digest(original/'INPUT.json'),prediction_sha256=digest(original/'PREDICTION.json'),
            states_sha256=digest(directory/'STATES.jsonl.gz'),capture_seconds=capture_seconds,analysis_seconds=analysis_seconds)
        write_json(directory/'CHECKED.json',checked);rows.append(checked)
        print(name,'cycles',checked['processed_cycles'],'covered',checked['observed_covered_cycles'],
            'busy covered',checked['busy_service_cycles_covered'],'chains',checked['parametric_pattern_chains'],flush=True)
    write_json(args.output/'RESULTS.json',dict(rows=rows,audit_complete=True,native_executions=0,
        compression_implemented=False,skipped_cycles=0,timing_scope='Instrumented audit cost only, not simulator speedup'))
    artifacts={str(p.relative_to(args.output)):digest(p) for p in args.output.rglob('*') if p.is_file()}
    write_json(args.output/'COMPLETE.json',dict(complete=True,source_commit=source,artifacts_sha256=artifacts,
        native_executions=0,compression_implemented=False,skipped_cycles=0))
except BaseException as error:
    write_json(args.output/'FAILED.json',dict(complete=False,error=repr(error),source_commit=source,native_executions=0))
    raise
