"""Self-consistent hash rewrites must not hide bad saved state or summaries."""
import argparse
import gzip
import json
import shutil
import subprocess
from pathlib import Path
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import read_json,write_json,digest
from wafer_sim.analysis.causal_compressibility import readback,encoded

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('campaign',type=Path);parser.add_argument('output',type=Path)
parser.add_argument('--readback',type=Path,required=True)
args=parser.parse_args();root=require_active_server();repo=Path(__file__).resolve().parents[1]
if not args.output.is_absolute() or not args.output.is_relative_to(root/'runs') or args.output.exists():raise ValueError('Fresh server output required')
if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean main required')
receipt=read_json(args.readback/'VERIFIED.json')
if not receipt['readback_passed'] or receipt['audit_manifest_sha256']!=digest(args.campaign/'COMPLETE.json') or receipt['result_sha256']!=digest(args.campaign/'RESULTS.json'):
    raise ValueError('Authenticated accepted readback required')
args.output.mkdir();probes=[]
for fault in ('wrong_remaining_guard','duplicated_boundary','wrong_coverage_summary'):
    clone=args.output/fault;shutil.copytree(args.campaign,clone)
    case=clone/'single-long';summary=read_json(clone/'RESULTS.json');checked=read_json(case/'CHECKED.json')
    if fault=='wrong_coverage_summary':
        checked['observed_covered_cycles']+=1
    else:
        with gzip.open(case/'STATES.jsonl.gz','rt') as stream:rows=[json.loads(line) for line in stream]
        if fault=='wrong_remaining_guard':rows[100]['remaining'][0][0]+=1
        else:rows.append(rows[-1])
        with gzip.open(case/'STATES.jsonl.gz','wt') as stream:
            for row in rows:stream.write(encoded(row)+'\n')
        checked['states_sha256']=digest(case/'STATES.jsonl.gz')
    summary['rows'][0]=checked;write_json(case/'CHECKED.json',checked);write_json(clone/'RESULTS.json',summary)
    manifest=read_json(clone/'COMPLETE.json')
    manifest['artifacts_sha256']={name:digest(clone/name) for name in manifest['artifacts_sha256']}
    write_json(clone/'COMPLETE.json',manifest)
    try:readback(clone,clone/'UNEXPECTED_READBACK')
    except ValueError as error:probes.append(dict(name=fault,rejected=True,reason=str(error),hashes_recomputed=True))
    else:raise AssertionError('Fault accepted: '+fault)
write_json(args.output/'CHECKED.json',dict(passed=True,probes=probes,native_executions=0,
    source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
    audit_manifest_sha256=digest(args.campaign/'COMPLETE.json'),readback_receipt_sha256=digest(args.readback/'VERIFIED.json'),
    script_sha256=digest(Path(__file__).resolve())))
print('Rejected',len(probes),'self-consistent saved-data faults; zero Native executions')
