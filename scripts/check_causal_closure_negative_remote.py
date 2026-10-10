"""Real-data G1 fault injection; no Native execution or reference rewriting."""
from pathlib import Path
import copy
import subprocess
import sys
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json,digest
from wafer_sim.analysis.causal_closure import compare,read_observation

root=require_active_server();campaign=Path(sys.argv[1]);output=Path(sys.argv[2]);repo=Path(__file__).resolve().parents[1]
if not output.is_absolute() or not output.is_relative_to(root/'runs') or output.exists():raise ValueError('Fresh server output required')
if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean source required')
manifest=read_json(campaign/'COMPLETE.json')
if not manifest['complete'] or not manifest['accuracy_passed'] or (campaign/'FAILED.json').exists():raise ValueError('Accepted complete G1 campaign required')
source=campaign/'queued-source';names=('INPUT.json','PREDICTION.json','observed/NETWORK_RESULT.json','observed/OBSERVATION.jsonl')
for name in names:
    if digest(source/name)!=manifest['artifacts_sha256']['queued-source/'+name]:raise ValueError('Changed fault-injection input')
p=read_json(source/'PREDICTION.json');n=read_json(source/'observed/NETWORK_RESULT.json');obs=read_observation(source/'observed/OBSERVATION.jsonl');c=read_json(source/'INPUT.json')['contract']
rows=[]
def probe(name,modified_n,modified_obs,modified_p=p):
    try:
        checked=compare(c,modified_p,modified_n,modified_obs)
        if checked['passed']:raise AssertionError('Fault accepted: '+name)
        rows.append(dict(name=name,rejected=True,mismatches=checked['mismatches'],first_kind=checked['first_discrepancies'][0]['kind']))
    except ValueError as error:rows.append(dict(name=name,rejected=True,reason=str(error)))
bad=copy.deepcopy(n);bad['messages'][0]['flits'][0]['injection_router_arrival']+=1;probe('wrong_upstream_arrival',bad,obs)
bad=copy.deepcopy(obs);next(r for r in bad if r['kind']=='credit_return')['cycle']+=1;probe('wrong_credit_return',n,bad)
bad=copy.deepcopy(n);bad['messages'][1]['generated']-=1;probe('premature_source_generation',bad,obs)
bad=copy.deepcopy(obs);bad.pop(next(i for i,r in enumerate(bad) if r['kind']=='allocate_pre'));bad[-1]['rows_before_end']-=1
probe('missing_allocation_snapshot_with_consistent_footer',n,bad)
bad=copy.deepcopy(obs);next(r for r in bad if r['kind']=='allocate_pre' and r['vc_owner']>=0)['vc_owner']=-1;probe('wrong_vc_ownership',n,bad)
bad=copy.deepcopy(n);bad['messages'][0]['flits'].append(copy.deepcopy(bad['messages'][0]['flits'][0]));probe('duplicated_native_flit',bad,obs)
bad=copy.deepcopy(p);bad['native_boundary_inputs']=True;probe('declared_native_boundary_leak',n,obs,bad)
output.mkdir();write_json(output/'CHECKED.json',dict(passed=True,probes=rows,
    source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),script_sha256=digest(Path(__file__).resolve()),
    inputs_sha256={name:digest(source/name) for name in names},campaign_manifest_sha256=digest(campaign/'COMPLETE.json')))
print('Rejected',len(rows),'real-data faults; zero Native executions')
