"""Capture f91824d behavior before API refactoring, on hn072 only."""
import argparse
from dataclasses import asdict
from pathlib import Path
import platform
import subprocess
import sys

from wafer_sim.adapters.wafer_machine import compile_machine
from wafer_sim.adapters.memory_periphery import compile_periphery, bind_periphery, TransactionPolicy
from wafer_sim.analysis.memory_periphery import audit_periphery
from wafer_sim.analysis.timing import audit
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json, write_json, object_digest, digest
from wafer_sim.remote import require_active_server

BASELINE = 'f91824d171917e0e58824b97a1d2a2bff2e4cf51'


def main():
    require_active_server()
    p = argparse.ArgumentParser(); p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--fixtures', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    head = subprocess.check_output(['git', '-C', str(args.repo), 'rev-parse', 'HEAD'], text=True).strip()
    if head != BASELINE or subprocess.check_output(['git', '-C', str(args.repo), 'status', '--porcelain']):
        raise ValueError('Clean, pinned pre-refactor source required')
    # The fixture generator is delivered alongside this capture script, outside
    # the pinned checkout. Its bytes are recorded, not silently part of baseline.
    sys.path.insert(0, str(args.fixtures)); sys.path.insert(0, str(args.repo/'tests'))
    from public_cases import NAMES, inputs
    from test_collective_timing import case as collective_case
    args.output.mkdir(exist_ok=False)
    rows = []
    for name in NAMES:
        machine, w, placement, shared, kind = inputs(name, args.repo)
        compiled = compile_periphery(machine) if shared else compile_machine(machine)
        policy = TransactionPolicy(kind)
        binding, transactions = bind_periphery(w, compiled, placement, policy)
        record = dict(condition=None, layout=None, component=None,
            physical=dict(inventory=asdict(machine), target=asdict(compiled.target), timing=asdict(compiled.timing)),
            workload=asdict(w), placement=asdict(placement), transaction_policy=asdict(policy),
            transactions=transactions, plans={op: asdict(plan) for op, plan in binding.plans.items()})
        result = execute(binding, compiled.timing)
        if result['complete']:
            checked = audit_periphery(w, placement, compiled, binding, transactions, policy, result)
        else:
            try: audit_periphery(w, placement, compiled, binding, transactions, policy, result)
            except ValueError: checked = dict(rejected_incomplete=True)
            else: raise AssertionError('Incomplete baseline accepted')
        for suffix, value in (('INPUT', record), ('EXECUTION', result), ('AUDIT', checked)):
            write_json(args.output/f'{name}-{suffix}.json', value)
        rows.append(dict(name=name, input_sha256=object_digest(record), execution_sha256=object_digest(result),
            audit_sha256=object_digest(checked), complete=result['complete'], application_cycles=result['application_cycles'],
            event_sections_sha256={field: object_digest(result[field]) for field in
                ('services', 'phases', 'operations', 'output_ready', 'storage', 'resources', 'peak_bytes')}))
    binding, timing = collective_case(4); result = execute(binding, timing)
    checked = audit(binding, timing, result)
    write_json(args.output/'collective_rank_local-EXECUTION.json', result)
    rows.append(dict(name='collective_rank_local', execution_sha256=object_digest(result),
                     audit_sha256=object_digest(checked), application_cycles=result['application_cycles']))
    write_json(args.output/'EXPECTED.json', dict(baseline_commit=head, host=platform.node(), cases=rows,
        script_sha256=digest(__file__), fixtures_sha256=digest(args.fixtures/'public_cases.py'),
        scope='Pure Python event/state equivalence; not native application timing'))
    write_json(args.output/'COMPLETE.json', dict(complete=True, artifacts_sha256={
        f.name: digest(f) for f in args.output.iterdir() if f.is_file()}))
    print(dict(baseline_commit=head, cases=len(rows), output=str(args.output)))


if __name__ == '__main__': main()
