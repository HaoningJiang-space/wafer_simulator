"""Remote complete-work acceptance for a separately defined wafer computer."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys

from wafer_sim.architecture.wafer_machine import from_config,validate
from wafer_sim.adapters.wafer_machine import compile_machine,bind_machine,export_booksim
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.analysis.wafer_machine import audit_machine
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.transfer_granularity import Meter,native_peak,usage
from wafer_sim.io import read_json,write_json,digest,object_digest
from wafer_sim.workloads.memory_machine import build,place_data


def replay(compiled,binary,directory,output,seed):
    output.mkdir()
    config=export_booksim(compiled,output,seed)
    client=OnlineBookSim(binary,config,output,flit_bytes=compiled.physical.flit_bytes)
    rows=[json.loads(line) for line in (directory/'online_protocol.jsonl').read_text().splitlines()]
    count=0
    try:
        for i in range(1,len(rows),2):
            request=rows[i]['request']; expected=rows[i+1]['reply']
            if client._request(request)!=expected:raise ValueError('Native command replay diverged')
            count+=1
        client.process.stdin.close()
        if client.process.wait(timeout=60)!=0:raise ValueError('Replay native exit failed')
    finally:client.abort()
    receipt=dict(passed=True,commands=count,binary_sha256=digest(binary),
                 scope='Recorded network command/reply equivalence, not hardware measurement')
    write_json(output/'REPLAY.json',receipt)
    return receipt


def run(output,tests):
    if platform.node().split('.')[0]!='eex005':raise RuntimeError('Run only on eex005')
    repo=Path(__file__).resolve().parents[3];output=Path(output);tests=Path(tests)
    if not output.is_absolute():raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean source required')
    commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
    receipt=read_json(tests)
    if not receipt['passed'] or receipt['source_commit']!=commit or 'test_wafer_machine' not in receipt['modules']:
        raise ValueError('Passing same-source machine and regression tests required')
    if digest(receipt['tests_log'])!=receipt['tests_log_sha256']:raise ValueError('Changed test log')
    reg=read_json(repo/'configs/wafer_machine_validation.json')
    frozen=subprocess.check_output(['git','-C',str(repo),'diff',reg['frozen_execution_commit'],
        '--name-only','--','src/wafer_sim/execution','patches','third_party'],text=True).splitlines()
    if frozen:raise ValueError('Execution/native source changed: '+str(frozen))
    runtime=Path(reg['runtime']);binary=runtime/'build/booksim-online/online_booksim'
    accepted=read_json(runtime/'runs/group-sharing-001/STARTED.json')
    if digest(binary)!=accepted['binaries']['accepted_online']:raise ValueError('Frozen network binary changed')
    # Only the already bundled RapidChiplet config writer is reused; no author
    # placement generator is involved in constructing this candidate machine.
    sys.path.insert(0,str(repo/'third_party/nw-design-for-wsi'))
    output.mkdir(exist_ok=False)
    machine=from_config(read_json(repo/reg['machine']));compiled=compile_machine(machine)
    work,initial,meta=build(**reg['workload'])
    if len(compiled.target.compute)!=reg['workload']['workers']:raise ValueError('Work must cover declared compute tiles')
    affinity=sorted(os.sched_getaffinity(0))[-2:];os.sched_setaffinity(0,affinity)
    write_json(output/'STARTED.json',dict(source_commit=commit,registration=reg,
        machine=asdict(machine),geometry_check=validate(machine),workload=asdict(work),workload_metadata=meta,
        tests_receipt=receipt,tests_sha256=digest(tests),binary_sha256=digest(binary),
        frozen_execution_commit=reg['frozen_execution_commit'],frozen_paths_unchanged=True,
        native_build=accepted.get('build_source'),native_build_manifest_sha256=accepted.get('build_manifest_sha256'),
        source_hashes={str(p.relative_to(repo)):digest(p) for p in [*sorted((repo/'src').rglob('*.py')),
            repo/reg['machine'],repo/'configs/wafer_machine_validation.json',repo/'docs/WAFER_MACHINE.md',
            repo/'third_party/nw-design-for-wsi/rapidchiplet/booksim_wrapper.py']},
        host=platform.node(),python=sys.version,executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable,'-m','pip','freeze'],text=True).splitlines(),
        affinity=affinity,load=os.getloadavg(),scope=reg['scope']))
    rows=[];prepared={}
    try:
        # Freeze all bindings and physical endpoints before any execution.
        for mode in reg['data_placements']:
            directory=output/mode;directory.mkdir()
            place=place_data(initial,reg['workload']['workers'],mode)
            binding,transactions=bind_machine(work,compiled,place)
            identity=dict(machine=asdict(machine),target=asdict(compiled.target),timing=asdict(compiled.timing),
                workload=asdict(work),placement=asdict(place),transactions=transactions,
                plans={k:asdict(v) for k,v in binding.plans.items()},
                capacities={k:asdict(v) for k,v in binding.memory.items()})
            write_json(directory/'INPUT.json',identity)
            prepared[mode]=(place,binding,identity)
        for mode,(place,binding,identity) in prepared.items():
            directory=output/mode;meter=Meter();child=usage(resource.RUSAGE_CHILDREN)
            with meter.phase('network_configuration'):
                config=export_booksim(compiled,directory,reg['network_seed'])
            with meter.phase('network_initialization'):
                client=OnlineBookSim(binary,config,directory,flit_bytes=machine.flit_bytes)
            try:
                with meter.phase('execution'):
                    result=execute(binding,compiled.timing,network=client,cycle_limit=reg['cycle_limit'])
                if not result['complete']:raise ValueError('Incomplete full work: '+mode)
                peaks=dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                           native_peak_rss_kib=native_peak(client))
                with meter.phase('network_close_serialization'):client.close()
            finally:client.abort()
            child_cpu=usage(resource.RUSAGE_CHILDREN)-child
            with meter.phase('result_serialization'):write_json(directory/'execution.json',result)
            with meter.phase('independent_audit'):
                checked=audit_machine(work,place,compiled,binding,result)
                # Re-read the serialized result independently as well.
                if checked!=audit_machine(work,place,compiled,binding,read_json(directory/'execution.json')):
                    raise ValueError('Serialized result audit differs')
                write_json(directory/'AUDIT.json',checked)
                chain=critical_chain(binding,result);write_json(directory/'critical_chain.json',chain)
            with meter.phase('native_command_replay'):
                replay_receipt=replay(compiled,binary,directory,directory/'replay',reg['network_seed'])
            row=dict(data_placement=mode,application_cycles=result['application_cycles'],
                operations=len(result['operations']),logical_work_sha256=object_digest(asdict(work)),
                input_sha256=object_digest(identity),execution_sha256=object_digest(result),
                phases=meter.rows,native_total_cpu_seconds=child_cpu,**peaks,
                status=checked['status'],messages=checked['messages'],payload_bytes=checked['payload_bytes'],
                control_bytes=checked['control_bytes'],native_flits=checked['native_flits'],
                physical_kind_flits=checked['physical_kind_flits'],critical_chain_cycles=chain['cycles'],
                command_replay=replay_receipt,
                timing_scope='Single acceptance run; Python lifetime RSS; no comparative speedup claim')
            write_json(directory/'MEASURED.json',row);rows.append(row)
            write_json(output/'SUMMARY.json',rows)
            print(mode,result['application_cycles'],checked['messages'],flush=True)
        if len(rows)!=len(reg['data_placements']) or len({r['logical_work_sha256'] for r in rows})!=1:
            raise ValueError('Incomplete cells or unequal logical work')
        write_json(output/'COMPLETE.json',dict(all_registered_work_complete=True,source_commit=commit,
            application_cases=len(rows),artifacts_sha256={str(p.relative_to(output)):digest(p)
                for p in sorted(output.rglob('*')) if p.is_file()}))
    except BaseException as exc:
        write_json(output/'FAILED.json',dict(type=type(exc).__name__,message=str(exc)));raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True);parser.add_argument('--tests',required=True)
    args=parser.parse_args();run(args.output,args.tests)


if __name__=='__main__':main()
