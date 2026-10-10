"""Real compact-evidence faults after G2.1 accuracy/readback acceptance."""
import argparse
from copy import deepcopy
from pathlib import Path
import subprocess
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json,digest
from wafer_sim.analysis.causal_macro_single import PersistedRun,check_run,compact_reference

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('campaign',type=Path);parser.add_argument('output',type=Path)
parser.add_argument('--readback',type=Path,required=True)
args=parser.parse_args();root=require_active_server();repo=Path(__file__).resolve().parents[1]
if not args.output.is_absolute() or not args.output.is_relative_to(root/'runs') or args.output.exists():raise ValueError('Fresh server output required')
if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean main required')
manifest=read_json(args.campaign/'COMPLETE.json');receipt=read_json(args.readback/'VERIFIED.json')
if (not manifest['complete'] or not manifest['accuracy_passed'] or not receipt['readback_passed'] or
        receipt['campaign_manifest_sha256']!=digest(args.campaign/'COMPLETE.json') or receipt['result_sha256']!=digest(args.readback/'RESULTS.json')):
    raise ValueError('Authenticated accepted G2.1 readback required')
directory=args.campaign/'accuracy-1024-0'
for name in ('MACRO_RECORD.json','G1_REFERENCE.json','G1_BOUNDARIES.json'):
    if digest(directory/name)!=manifest['artifacts_sha256']['accuracy-1024-0/'+name]:raise ValueError('Changed fault-injection evidence')
record=read_json(directory/'MACRO_RECORD.json');reference=read_json(directory/'G1_REFERENCE.json')
boundaries={int(k):v for k,v in read_json(directory/'G1_BOUNDARIES.json').items()}
def verify(candidate):
    check_run(PersistedRun(candidate),reference,boundaries)
    if candidate['compact']!=compact_reference(reference):raise ValueError('Compact summary differs from reference')
verify(record);rows=[]
def probe(name,mutate):
    bad=deepcopy(record);mutate(bad)
    try:verify(bad)
    except ValueError as error:rows.append(dict(name=name,rejected=True,reason=str(error)))
    else:raise AssertionError('Accepted fault: '+name)
def repeat(record,name):return next(s for s in record['evidence'][name] if s['kind']=='repeat')
probe('wrong_repeat_count',lambda r:repeat(r,'service').__setitem__('repetitions',repeat(r,'service')['repetitions']+1))
probe('wrong_credit_template_clock',lambda r:repeat(r,'credit_returns')['template'][0].__setitem__('cycle',repeat(r,'credit_returns')['template'][0]['cycle']+1))
probe('wrong_exit_credit',lambda r:r['metrics']['checkpoints'][-1]['state']['kernel']['source_credits'].__setitem__(0,32))
probe('declared_native_boundary_input',lambda r:r['compact'].__setitem__('native_boundary_inputs',True))
probe('wrong_source_injection_time',lambda r:r['evidence']['injections'][0]['rows'].__setitem__(0,1))
probe('crossed_source_tail',lambda r:r['metrics']['batches'][0].__setitem__('source_remaining_after',0))
probe('missing_exit_checkpoint',lambda r:r['metrics']['checkpoints'].pop())
probe('repeated_checkpoint_identity',lambda r:r['metrics']['checkpoints'].append(deepcopy(r['metrics']['checkpoints'][0])))
args.output.mkdir();write_json(args.output/'CHECKED.json',dict(passed=True,probes=rows,native_executions=0,application_executions=0,
    source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),script_sha256=digest(Path(__file__).resolve()),
    campaign_manifest_sha256=digest(args.campaign/'COMPLETE.json'),readback_receipt_sha256=digest(args.readback/'VERIFIED.json'),
    macro_record_sha256=digest(directory/'MACRO_RECORD.json')))
print('Rejected',len(rows),'saved compact-evidence faults; zero Native/application runs')
