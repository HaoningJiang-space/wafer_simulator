"""Remote same-machine U0/U1/S comparison, with isolated execution metering."""
import argparse
from dataclasses import asdict
import gc
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine, export_booksim
from wafer_sim.adapters.memory_machine_workload import place
from wafer_sim.adapters.memory_abstraction import project
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.adapters.uniform_memory_network import UniformMemoryNetwork
from wafer_sim.architecture.wafer_machine import from_config
from wafer_sim.analysis.memory_abstraction import audit, audit_projection
from wafer_sim.analysis.wafer_machine import audit_machine
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.timing import execute
from wafer_sim.experiments.transfer_granularity import Meter, usage, native_peak
from wafer_sim.experiments.wafer_machine import replay
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.workloads.memory_machine import build

REPO = Path(__file__).resolve().parents[3]
FROZEN = ['src/wafer_sim/execution', 'patches', 'third_party',
    'src/wafer_sim/architecture/wafer_machine.py', 'src/wafer_sim/adapters/wafer_machine.py',
    'src/wafer_sim/workloads/memory_machine.py', 'src/wafer_sim/adapters/memory_machine_workload.py',
    'configs/wafer_machine.json', 'configs/wafer_machine_validation.json']


def prepare(layout, model, reg):
    machine = from_config(read_json(REPO/reg['machine']))
    compiled = compile_machine(machine)
    work, meta = build(**reg['workload'])
    placement = place(meta, layout)
    base, transactions = bind_machine(work, compiled, placement)
    binding, timing, spec = project(compiled, base, model)
    audit_projection(compiled, base, binding, timing, spec)
    # Original machine/work/layout identity is identical across the three models.
    physical_input = dict(machine=asdict(machine), target=asdict(compiled.target), timing=asdict(compiled.timing),
        workload=asdict(work), placement=asdict(placement), transactions=transactions,
        plans={k: asdict(v) for k, v in base.plans.items()}, capacities={k: asdict(v) for k, v in base.memory.items()})
    projected_input = dict(contract=spec, homes=dict(binding.homes), timing=asdict(timing),
        plans={k: asdict(v) for k, v in binding.plans.items()}, capacities={k: asdict(v) for k, v in binding.memory.items()})
    return compiled, work, placement, base, binding, timing, spec, physical_input, projected_input


def worker(output, layout, model, profile, repetitions):
    reg = read_json(REPO/'configs/wafer_machine_validation.json')
    binary = Path(reg['runtime'])/'build/booksim-online/online_booksim'
    output.mkdir(exist_ok=False)
    meter = Meter()
    with meter.phase('graph_binding_preparation'):
        c, work, placement, base, binding, timing, spec, physical, projected = prepare(layout, model, reg)
    write_json(output/'INPUT.json', dict(physical=physical, projection=projected))
    write_json(output/'PREPARATION.json', meter.rows)
    old = {r['data_placement']: r for r in read_json(REPO/'docs/results/wafer-machine-001/SUMMARY.json')}[layout]
    if object_digest(physical) != old['input_sha256']:
        raise ValueError('Underlying input changed from accepted machine')
    sys.path.insert(0, str(REPO/'third_party/nw-design-for-wsi'))
    for rep in range(repetitions):
        directory = output/f'rep-{rep}'; directory.mkdir()
        gc.collect()
        meter = Meter(); child = usage(resource.RUSAGE_CHILDREN)
        with meter.phase('network_configuration'):
            config = export_booksim(c, directory, reg['network_seed'])
        with meter.phase('network_initialization'):
            native = OnlineBookSim(binary, config, directory, flit_bytes=c.physical.flit_bytes)
            client = native if model == 'S' else UniformMemoryNetwork(native, spec)
        try:
            with meter.phase('execution'):
                result = execute(binding, timing, network=client, cycle_limit=reg['cycle_limit'])
            if not result['complete']: raise ValueError('Incomplete complete-work experiment')
            peaks = dict(python_lifetime_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                         native_peak_rss_kib=native_peak(native))
            with meter.phase('network_close_serialization'): client.close()
        finally: client.abort()
        child_cpu = usage(resource.RUSAGE_CHILDREN)-child
        with meter.phase('result_serialization'): write_json(directory/'execution.json', result)
        with meter.phase('independent_audit'):
            checked = audit(c, base, binding, timing, spec, result)
            if model == 'S':
                checked['physical'] = audit_machine(work, placement, c, binding, result)
                if object_digest(result) != old['execution_sha256']:
                    raise ValueError('S no longer reproduces accepted complete event hash')
            reread = audit(c, base, binding, timing, spec, read_json(directory/'execution.json'))
            if reread != {k: v for k, v in checked.items() if k != 'physical'}:
                raise ValueError('Serialized audit disagrees')
            chain = critical_chain(binding, result)
            write_json(directory/'AUDIT.json', checked)
            write_json(directory/'critical_chain.json', chain)
        row = dict(model=model, layout=layout, profile=profile, repetition=rep,
            physical_input_sha256=object_digest(physical), projection_sha256=object_digest(projected),
            execution_sha256=object_digest(result), application_cycles=result['application_cycles'],
            phases=meter.rows, native_total_cpu_seconds=child_cpu, **peaks,
            status=checked['status'], chain_cycles=chain['cycles'],
            messages=checked['logical_messages'], bytes=checked['logical_message_bytes'], work=checked['work_by_unit'],
            native_messages=len(result.get('native_network_messages', result['network_messages'])),
            native_flits=sum(len(m['flits']) for m in result.get('native_network_messages', result['network_messages'])),
            capacity_wait_sum_cycles=sum(o['capacity_wait_cycles'] for o in result['operations'].values()),
            resource_queue_waits={k: v['queue_wait_cycles'] for k, v in result['resources'].items() if v['queue_wait_cycles']},
            load=os.getloadavg(), affinity=sorted(os.sched_getaffinity(0)))
        write_json(directory/'MEASURED.json', row)
        del result, chain


def run(output, tests):
    if not output.is_absolute(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain']):
        raise ValueError('Clean source required')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    spec = read_json(REPO/'configs/memory_abstraction.json')
    reg = read_json(REPO/spec['base_registration'])
    receipt = read_json(tests)
    if (not receipt['passed'] or receipt['source_commit'] != commit or
        'test_memory_abstraction' not in receipt['modules'] or digest(receipt['tests_log']) != receipt['tests_log_sha256']):
        raise ValueError('Same-source passing tests required')
    if subprocess.check_output(['git', '-C', str(REPO), 'diff', spec['reference_commit'], '--name-only', '--', *FROZEN]):
        raise ValueError('Frozen machine, workload or execution changed')
    binary = Path(reg['runtime'])/'build/booksim-online/online_booksim'
    old = read_json(REPO/'docs/results/wafer-machine-001/STARTED.json')
    if digest(binary) != old['binary_sha256']: raise ValueError('Frozen native binary changed')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:])
    output.mkdir(exist_ok=False)
    write_json(output/'STARTED.json', dict(source_commit=commit, registration=spec, machine_registration=reg,
        tests_receipt=receipt, tests_sha256=digest(tests), binary_sha256=digest(binary),
        frozen_paths=FROZEN, frozen_paths_unchanged=True,
        sources={str(p.relative_to(REPO)): digest(p) for p in [*sorted((REPO/'src').rglob('*.py')),
            *sorted((REPO/'configs').glob('*.json')), REPO/'docs/MEMORY_ABSTRACTION_PROTOCOL.md']},
        host=platform.node(), python=sys.version, executable_sha256=digest(Path(sys.executable).resolve()),
        packages=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines(),
        affinity=sorted(os.sched_getaffinity(0)), load=os.getloadavg(),
        native_build_manifest=old.get('native_build_manifest_sha256')))
    try:
        jobs = []
        for rep in range(spec['cold_repetitions']):
            models = spec['models'][rep:]+spec['models'][:rep]
            for layout in spec['layouts']:
                for model in models: jobs.append((layout, model, 'cold', rep, 1))
        for layout in spec['layouts']:
            for model in reversed(spec['models']):
                jobs.append((layout, model, 'binding_reuse', 0, spec['binding_reuse_repetitions']))
        for layout, model, profile, rep, count in jobs:
            directory = output/f'{layout}-{model}-{profile}-{rep}'
            started = time.perf_counter()
            with (output/'worker.log').open('a') as log:
                subprocess.run([sys.executable, '-m', 'wafer_sim.experiments.memory_abstraction', '--worker', '--output', str(directory),
                    '--layout', layout, '--model', model, '--profile', profile, '--repetitions', str(count)],
                    check=True, stdout=log, stderr=subprocess.STDOUT, timeout=600)
            write_json(directory/'PROCESS.json', dict(wall_seconds=time.perf_counter()-started,
                scope='Whole subprocess including imports, execution, serialization and audits; not backend execution time'))
            print(layout, model, profile, rep, flush=True)
        c, *_ = prepare('near', 'S', reg)
        sys.path.insert(0, str(REPO/'third_party/nw-design-for-wsi'))
        for layout in spec['layouts']:
            for model in spec['models']:
                directory = output/f'{layout}-{model}-cold-0/rep-0'
                meter = Meter()
                with meter.phase('native_command_replay'):
                    replay(c, binary, directory, directory/'replay', reg['network_seed'])
                write_json(directory/'REPLAY_COST.json', meter.rows)
        rows = []
        for path in sorted(output.glob('*/rep-*/MEASURED.json')):
            row = read_json(path); row['directory'] = str(path.parent.relative_to(output)); rows.append(row)
        expected = len(spec['models'])*len(spec['layouts'])*(spec['cold_repetitions']+spec['binding_reuse_repetitions'])
        if len(rows) != expected: raise ValueError('Missing experiment arms')
        for layout in spec['layouts']:
            subset = [r for r in rows if r['layout'] == layout]
            if len({r['physical_input_sha256'] for r in subset}) != 1:
                raise ValueError('Compared different machines/work/layouts')
            for model in spec['models']:
                if len({r['execution_sha256'] for r in subset if r['model'] == model}) != 1:
                    raise ValueError('Nondeterministic execution')
        if len({json.dumps((r['messages'], r['bytes'], r['work']), sort_keys=True) for r in rows}) != 1:
            raise ValueError('Logical work conservation failed across models/layouts')
        write_json(output/'SUMMARY.json', rows)
        write_json(output/'COMPLETE.json', dict(source_commit=commit, completed=True, configurations=9,
            executions=len(rows), native_replays=9,
            artifacts_sha256={str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))
    except BaseException as exc:
        write_json(output/'FAILED.json', dict(type=type(exc).__name__, message=str(exc))); raise


def main():
    if platform.node().split('.')[0] != 'eex005': raise RuntimeError('Remote execution only')
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path); p.add_argument('--tests', type=Path)
    p.add_argument('--worker', action='store_true'); p.add_argument('--layout'); p.add_argument('--model')
    p.add_argument('--profile'); p.add_argument('--repetitions', type=int)
    args = p.parse_args()
    if args.worker: worker(args.output, args.layout, args.model, args.profile, args.repetitions)
    else: run(args.output, args.tests)


if __name__ == '__main__': main()
