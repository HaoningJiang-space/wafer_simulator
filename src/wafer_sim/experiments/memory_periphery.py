"""Registered six-cell memory organization/policy comparison on hn072."""
import argparse
import ast
from collections import Counter
from dataclasses import asdict
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

from wafer_sim.adapters.memory_periphery import compile_periphery, bind_periphery, TransactionPolicy
from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine, export_booksim
from wafer_sim.adapters.online_booksim import OnlineBookSim
from wafer_sim.adapters.scaling_layout import place_scaled, capacity_bound
from wafer_sim.architecture.wafer_machine import from_config
from wafer_sim.analysis.memory_periphery import audit_periphery, transaction_timing
from wafer_sim.analysis.wafer_machine import audit_machine
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.experiments.memory_abstraction import REPO, FROZEN
from wafer_sim.experiments.isolated_response import semantic_config
from wafer_sim.experiments.wafer_machine import replay
from wafer_sim.experiments.transfer_granularity import Meter, native_peak, usage
from wafer_sim.execution.plan import Placement
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.remote import require_active_server
from wafer_sim.workloads.memory_machine import build
from wafer_sim.workloads.spatial import Workload, DataObject, Operation

REGISTRATION = 'configs/memory_periphery.json'


def registration():
    reg = read_json(REPO/REGISTRATION)
    return reg, read_json(REPO/reg['base_registration'])


def component_work(case, size):
    data, operations, homes, compute = [], [], {}, {}
    count = 2 if case == 'two_banks' else 1
    for i in range(count):
        x, y, op = f'x{i}', f'y{i}', f'f{i}'
        write = case == 'write'
        data.extend((DataObject(x, 64 if write else size, None, False, 'Registered component'),
                     DataObject(y, size if write else 64, op, True, 'Registered component')))
        operations.append(Operation(op, (x,), (y,), (('mac', 256),), 0, (), 'Policy component'))
        compute[op] = f'c{i}'
        homes[x] = f'sram-{i}' if write else f'dram-0-{i}'
        homes[y] = 'dram-0-0' if write else f'sram-{i}'
    return Workload(tuple(data), tuple(operations)), Placement(compute, homes)


def prepare(condition, layout=None, component=None):
    reg, base = registration()
    if condition not in reg['conditions']: raise ValueError('Unregistered condition')
    cfg = read_json(REPO/base['machine']); cfg['array'] = [reg['side'], reg['side']]
    machine = from_config(cfg)
    c = compile_machine(machine) if condition == 'v1_whole' else compile_periphery(machine)
    policy = TransactionPolicy('pipeline' if condition == 'shared_pipeline' else 'whole',
                               reg['chunk_bytes'], reg['window_chunks'])
    if component is not None:
        if component not in reg['component_cases']: raise ValueError('Unregistered component')
        w, p = component_work(component, reg['component_bytes'])
    else:
        if layout not in reg['layouts']: raise ValueError('Unregistered layout')
        w, metadata = build(reg['side']**2, **base['per_worker']); p = place_scaled(metadata, reg['side'], layout)
    b, tx = bind_periphery(w, c, p, policy)
    bound = capacity_bound(b)
    physical = dict(inventory=asdict(machine), target=asdict(c.target), timing=asdict(c.timing))
    identity = dict(condition=condition, layout=layout, component=component, physical=physical,
        workload=asdict(w), placement=asdict(p), transaction_policy=asdict(policy),
        transactions=tx, plans={k: asdict(v) for k, v in b.plans.items()}, capacity_bound=bound)
    return c, w, p, b, tx, policy, identity


def function_identity(path, names, reference):
    old = subprocess.check_output(['git', '-C', str(REPO), 'show', reference+':'+path], text=True)
    def functions(source):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(source).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names}
    before, after = functions(old), functions((REPO/path).read_text())
    if set(before) != set(names) or before != after: raise ValueError('Changed frozen binding function: '+path)
    return {name: object_digest(before[name]) for name in names}


def export_equivalence(c, directory, seed, reference):
    """Same directory: absolute config paths cannot explain a hash difference."""
    directory.mkdir()
    namespace = {'__name__': 'archived_v1_export'}
    source = subprocess.check_output(['git', '-C', str(REPO), 'show',
        reference+':src/wafer_sim/adapters/wafer_machine.py'], text=True)
    exec(compile(source, '<pinned-v1-adapter>', 'exec'), namespace)
    old = namespace['export_booksim'](c, directory, seed)
    topology = old.parent.parent/'rc_topologies/network.anynet'
    before = dict(config=digest(old), topology=digest(topology), semantics=semantic_config(old))
    new = export_booksim(c, directory, seed)
    after = dict(config=digest(new), topology=digest(topology), semantics=semantic_config(new))
    if before != after: raise ValueError('v1 exported bytes changed')
    return dict(passed=True, archived_source_sha256=object_digest(source), **after)


def finish(output, **fields):
    write_json(output/'COMPLETE.json', dict(complete=True, **fields,
        artifacts_sha256={str(p.relative_to(output)): digest(p) for p in sorted(output.rglob('*')) if p.is_file()}))


def worker(output, condition, layout, component, input_path):
    root = require_active_server(); reg, base = registration()
    output.mkdir(); meter = Meter(); started = time.perf_counter(); own_cpu = time.process_time()
    with meter.phase('graph_binding_preparation'): c, w, p, b, tx, policy, identity = prepare(condition, layout, component)
    if object_digest(identity) != object_digest(read_json(input_path)): raise ValueError('Frozen input changed')
    sys.path.insert(0, str(REPO/'third_party/nw-design-for-wsi'))
    with meter.phase('network_configuration'): config = export_booksim(c, output, base['network_seed'])
    write_json(output/'NETWORK_BEHAVIOR.json', dict(semantic_config=semantic_config(config),
        binary_sha256=digest(root/'build/booksim-online/online_booksim'),
        native_defaults=dict(vc_allocator='islip', sw_allocator='islip', arb_type='round_robin',
                             alloc_iters=1, speculative=0, hold_switch_for_packet=0),
        defaults_source='third_party/nw-design-for-wsi/rapidchiplet/booksim2/src/booksim_config.cpp',
        defaults_source_sha256=digest(REPO/'third_party/nw-design-for-wsi/rapidchiplet/booksim2/src/booksim_config.cpp')))
    child_cpu = usage(resource.RUSAGE_CHILDREN)
    with meter.phase('network_initialization'):
        native = OnlineBookSim(root/'build/booksim-online/online_booksim', config, output, flit_bytes=c.physical.flit_bytes)
    try:
        with meter.phase('execution'): result = execute(b, c.timing, network=native, cycle_limit=base['cycle_limit'])
        peak = native_peak(native)
        with meter.phase('network_close_serialization'): native.close()
    finally: native.abort()
    native_cpu = usage(resource.RUSAGE_CHILDREN)-child_cpu
    with meter.phase('result_serialization'): write_json(output/'execution.json', result)
    with meter.phase('independent_audit'):
        checked = audit_periphery(w, p, c, b, tx, policy, read_json(output/'execution.json'))
        if any(o['capacity_wait_cycles'] for o in result['operations'].values()): raise ValueError('Unexpected capacity waits')
        if condition != 'shared_pipeline': audit_machine(w, p, c, b, result)
        if condition == 'v1_whole' and component is None:
            reference = [r for r in read_json(REPO/'docs/results/spatial-scaling-001/SUMMARY.json')
                         if r['side'] == reg['side'] and r['layout'] == layout and r['model'] == 'S']
            if not reference or {r['execution_sha256'] for r in reference} != {object_digest(result)}:
                raise ValueError('Accepted v1 execution events changed')
        write_json(output/'AUDIT.json', checked)
        write_json(output/'critical_chain.json', critical_chain(b, result))
        timings = transaction_timing(b, tx, result); write_json(output/'TRANSACTIONS.json', timings)
    row = dict(condition=condition, layout=layout, component=component, application_cycles=result['application_cycles'],
        execution_sha256=object_digest(result), input_sha256=object_digest(identity),
        physical_sha256=object_digest(identity['physical']),
        work_placement_sha256=object_digest(dict(workload=identity['workload'], placement=identity['placement'])),
        phases=meter.rows, native_cpu_seconds=native_cpu, python_cpu_seconds=time.process_time()-own_cpu,
        worker_body_wall_seconds=time.perf_counter()-started, native_peak_rss_kib=peak,
        python_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        logical_transactions=len(tx), native_messages=len(result['network_messages']),
        native_flits=sum(len(m['flits']) for m in result['network_messages']),
        payload_bytes=checked['payload_bytes'], control_bytes=checked['control_bytes'],
        physical_kind_flits=checked['physical_kind_flits'],
        resources=result['resources'], peak_bytes=result['peak_bytes'],
        bank_channel_overlap=overlap_summary(result), passed=checked['passed'],
        load=os.getloadavg(), affinity=sorted(os.sched_getaffinity(0)),
        output_bytes_before_measurement=sum(p.stat().st_size for p in output.rglob('*') if p.is_file()))
    write_json(output/'MEASURED.json', row)


def overlap_summary(result):
    """Duration with both bank and channel serializers busy; latency excluded."""
    points = []
    for e in result['services']:
        kind = 'channel' if e['resource'].endswith('/channel') else 'bank' if e['resource'].startswith(('dram-', 'host-memory/')) else None
        if kind is not None:
            points.extend(((e['start'], kind, 1), (e['resource_released'], kind, -1)))
    occupied = Counter(); previous = total = 0
    for cycle, kind, delta in sorted(points):
        if occupied['bank'] and occupied['channel']: total += cycle-previous
        occupied[kind] += delta; previous = cycle
    return dict(global_simultaneous_serializer_cycles=total,
                scope='Any bank and any channel; not a causal application-time contribution')


def gate(output, tests):
    root = require_active_server(); reg, base = registration()
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain']): raise ValueError('Clean source required')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = read_json(tests)
    if (not receipt['passed'] or receipt['source_commit'] != commit or 'test_memory_periphery' not in receipt['modules'] or
            digest(receipt['tests_log']) != receipt['tests_log_sha256']): raise ValueError('Same-source passing tests required')
    frozen = [p for p in FROZEN if p != 'src/wafer_sim/adapters/wafer_machine.py'] + [
        'src/wafer_sim/architecture/spatial.py', 'src/wafer_sim/architecture/timing.py',
        'src/wafer_sim/workloads/spatial.py', 'src/wafer_sim/adapters/scaling_layout.py',
        'src/wafer_sim/adapters/timing.py', 'configs/spatial_scaling.json',
        'docs/results/spatial-scaling-001', 'docs/results/independent-spatial-service-001']
    if subprocess.check_output(['git', '-C', str(REPO), 'diff', reg['reference_commit'], '--name-only', '--', *frozen]):
        raise ValueError('Frozen inventory, work, executor, services, upstream or evidence changed')
    functions = {
        'wafer_machine': function_identity('src/wafer_sim/adapters/wafer_machine.py', ['compile_machine', 'bind_machine'], reg['reference_commit']),
        'spatial': function_identity('src/wafer_sim/adapters/spatial.py', ['bind', 'network_from_wow'], reg['reference_commit'])}
    binary = root/'build/booksim-online/online_booksim'
    expected = read_json(REPO/'docs/results/spatial-scaling-001/STARTED.json')['binary_sha256']
    if digest(binary) != expected: raise ValueError('Accepted binary changed')
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[-2:])
    output.mkdir(); (output/'inputs').mkdir()
    write_json(output/'STARTED.json', dict(source_commit=commit, registration=reg, base_registration=base,
        tests_receipt=receipt, tests_sha256=digest(tests), binary_sha256=expected,
        frozen_paths=frozen, frozen_function_ast_sha256=functions,
        host=platform.node(), platform=platform.platform(), python=sys.version,
        executable_sha256=digest(Path(sys.executable).resolve()),
        accepted_reference_started_sha256=digest(REPO/'docs/results/spatial-scaling-001/STARTED.json'),
        packages=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines(),
        affinity=sorted(os.sched_getaffinity(0)), load=os.getloadavg(),
        source_hashes={str(p.relative_to(REPO)): digest(p) for p in [*sorted((REPO/'src').rglob('*.py')),
            REPO/REGISTRATION, REPO/reg['base_registration'], REPO/base['machine'], REPO/'docs/MEMORY_PERIPHERY_PROTOCOL.md']}))
    return binary


def run(output, tests):
    binary = gate(output, tests); reg, base = registration(); started = time.perf_counter()
    sys.path.insert(0, str(REPO/'third_party/nw-design-for-wsi'))
    try:
        c, *_ = prepare('v1_whole', reg['layouts'][0])
        write_json(output/'V1_EXPORT_EQUIVALENCE.json', export_equivalence(c, output/'v1-export-equivalence',
                   base['network_seed'], reg['reference_commit']))
        jobs = []
        for component in reg['component_cases']:
            for condition in reg['conditions']:
                jobs.append((f'component-{component}-{condition}', condition, None, component, 0))
        # Freeze all inputs before executing even the first component.
        for rep in range(reg['repetitions']):
            conditions = reg['conditions'][rep:] + reg['conditions'][:rep]
            layouts = reg['layouts'] if rep % 2 == 0 else list(reversed(reg['layouts']))
            for layout in layouts:
                for condition in conditions:
                    jobs.append((f'{layout}-{condition}-rep-{rep}', condition, layout, None, rep))
        for name, condition, layout, component, _ in jobs:
            *_, identity = prepare(condition, layout, component)
            write_json(output/f'inputs/{name}.json', identity)
        rows, validation_seconds = [], 0
        for name, condition, layout, component, rep in jobs:
            before = time.perf_counter()
            command = [sys.executable, '-m', 'wafer_sim.experiments.memory_periphery', '--worker', '--output', str(output/name),
                       '--condition', condition, '--input', str(output/f'inputs/{name}.json')]
            if layout is not None: command += ['--layout', layout]
            if component is not None: command += ['--component', component]
            with (output/'worker.log').open('a') as log:
                subprocess.run(command, check=True, stdout=log, stderr=subprocess.STDOUT, timeout=900)
            wall = time.perf_counter()-before
            write_json(output/name/'PROCESS.json', dict(wall_seconds=wall, scope='Fresh worker including imports, writes and audits'))
            row = read_json(output/name/'MEASURED.json'); row.update(directory=name, repetition=rep, process_wall_seconds=wall)
            rows.append(row); write_json(output/'PROGRESS.json', rows)
            if component is not None: validation_seconds += wall
            print(name, row['application_cycles'], flush=True)
        if len(rows) != 27: raise ValueError('Incomplete registered comparison')
        applications = [r for r in rows if r['component'] is None]
        for layout in reg['layouts']:
            a = [r for r in applications if r['layout'] == layout]
            if len({r['work_placement_sha256'] for r in a}) != 1: raise ValueError('Work or mapping changed')
            for condition in reg['conditions']:
                cell = [r for r in a if r['condition'] == condition]
                if len(cell) != 3 or len({r['execution_sha256'] for r in cell}) != 1: raise ValueError('Nonrepeatable or missing cell')
            if len({r['physical_sha256'] for r in a if r['condition'].startswith('shared_')}) != 1:
                raise ValueError('Pipeline comparison changed machine')
            if len({object_digest((r['payload_bytes'], r['control_bytes'])) for r in a}) != 1:
                raise ValueError('Payload or control totals changed')
        replay_rows = []
        for row in rows:
            if row['component'] is None and row['repetition'] != 0: continue
            c, *_ = prepare(row['condition'], row['layout'], row['component']); d = output/row['directory']
            before = time.perf_counter(); receipt = replay(c, binary, d, d/'replay', base['network_seed'])
            replay_rows.append(dict(directory=row['directory'], wall_seconds=time.perf_counter()-before, **receipt))
        write_json(output/'REPLAYS.json', replay_rows); write_json(output/'SUMMARY.json', rows)
        write_json(output/'COST.json', dict(total_wall_seconds=time.perf_counter()-started, calibration_seconds=0,
            component_workers_seconds=validation_seconds, application_workers_seconds=sum(r['process_wall_seconds'] for r in applications),
            replay_seconds=sum(r['wall_seconds'] for r in replay_rows),
            artifact_bytes=sum(p.stat().st_size for p in output.rglob('*') if p.is_file())))
        finish(output, source_commit=read_json(output/'STARTED.json')['source_commit'],
               application_cells=6, application_executions=18, components=9, native_replays=15)
    except BaseException as exc:
        write_json(output/'FAILED.json', dict(type=type(exc).__name__, message=str(exc))); raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--tests', type=Path)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--condition')
    parser.add_argument('--layout'); parser.add_argument('--component'); parser.add_argument('--input', type=Path)
    args = parser.parse_args()
    if args.worker: worker(args.output, args.condition, args.layout, args.component, args.input)
    else: run(args.output, args.tests)
