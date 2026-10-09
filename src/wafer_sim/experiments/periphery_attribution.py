"""Frozen saved-trace attribution and DMA contract checks; no simulations."""
import argparse
from collections import Counter, defaultdict
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
import time

from wafer_sim.analysis.periphery_attribution import (
    chain_accounting, supply_and_dma, message_tags, network_profile,
    compare_packet_facts, transaction_key, fragments)
from wafer_sim.analysis.memory_periphery import audit_periphery
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.adapters.periphery_case import case_from_record
from wafer_sim.analysis.periphery_mechanism_study import summary, timeline, make_figures, report
from wafer_sim.io import read_json, write_json, digest, object_digest
from wafer_sim.experiments.server import require_active_server

REGISTRATION = 'configs/memory_periphery_attribution.json'
REPO = Path(__file__).resolve().parents[3]


def run(output, tests):
    require_active_server(); reg = read_json(REPO/REGISTRATION); source = Path(reg['source_run'])
    if not output.is_absolute() or output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git', '-C', str(REPO), 'status', '--porcelain']): raise ValueError('Clean analysis source required')
    if subprocess.check_output(['git', '-C', str(REPO), 'diff', reg['frozen_commit'], '--diff-filter=DMRT',
        '--name-only', '--', 'src', 'tests', 'scripts', 'configs', 'patches', 'third_party', 'docs/results']):
        raise ValueError('Pre-existing model, policy, analysis or evidence changed')
    commit = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip()
    receipt = read_json(tests)
    if (not receipt['passed'] or receipt['source_commit'] != commit or receipt['modules'] != ['test_periphery_attribution'] or
            digest(receipt['tests_log']) != receipt['tests_log_sha256']): raise ValueError('Same-source reader regressions required')
    start = read_json(source/'STARTED.json'); complete = read_json(source/'COMPLETE.json')
    if not complete['complete'] or (source/'FAILED.json').exists(): raise ValueError('Incomplete source evidence')
    if digest(source/'COMPLETE.json') != read_json(REPO/'docs/results/memory-periphery-001/CHECKED.json')['completion_sha256']:
        raise ValueError('Changed accepted completion receipt')
    for name, sha in start['source_hashes'].items():
        if digest(REPO/name) != sha: raise ValueError('Changed application source: '+name)
    started = time.perf_counter(); cpu = time.process_time(); output.mkdir()
    files = [REPO/REGISTRATION, REPO/'docs/MEMORY_PERIPHERY_ATTRIBUTION_PROTOCOL.md',
             REPO/'src/wafer_sim/analysis/periphery_attribution.py', Path(__file__),
             REPO/'scripts/test_periphery_attribution_remote.py', REPO/'tests/test_periphery_attribution.py']
    write_json(output/'STARTED.json', dict(source_commit=commit, registration=reg, tests=receipt,
        tests_sha256=digest(tests), source_run=str(source), source_completion_sha256=digest(source/'COMPLETE.json'),
        native_binary_sha256=start['binary_sha256'], application_source_commit=start['source_commit'],
        python=sys.version, python_binary_sha256=digest(Path(sys.executable).resolve()), host=platform.node(),
        packages=subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True).splitlines(),
        source_hashes={str(p.relative_to(REPO)): digest(p) for p in files}, new_simulations=0))
    try:
        for name, sha in complete['artifacts_sha256'].items():
            if digest(source/name) != sha: raise ValueError('Changed saved artifact: '+name)
        rows = [r for r in read_json(source/'SUMMARY.json') if r['component'] is None]
        if len(rows) != 18: raise ValueError('Missing source applications')
        cells, rechecks, facts, orders, profiles, packets, timelines = {}, [], {}, {}, {}, {}, {}
        for row in rows:
            directory = source/row['directory']; key = row['condition']+'/'+row['layout']
            identity = read_json(source/f"inputs/{row['directory']}.json")
            case = case_from_record(identity)
            c, w, p, b, tx, policy = (case.compiled, case.workload, case.placement, case.binding, case.transactions, case.policy)
            if object_digest(identity) != row['input_sha256']: raise ValueError('Binding identity changed')
            result = read_json(directory/'execution.json')
            if object_digest(result) != row['execution_sha256']: raise ValueError('Changed result object')
            if audit_periphery(w, p, c, b, tx, policy, result) != read_json(directory/'AUDIT.json'):
                raise ValueError('Existing completion audit changed')
            chain = critical_chain(b, result)
            if object_digest(chain) != object_digest(read_json(directory/'critical_chain.json')):
                raise ValueError('Recorded critical chain changed')
            commands = Counter()
            with (directory/'online_protocol.jsonl').open() as stream:
                import json
                for line in stream:
                    if line.startswith('{"request":'): commands[json.loads(line)['request']['command']] += 1
            if set(commands) != {'submit', 'advance', 'close'} or commands['submit'] != len(result['network_messages']) or commands['close'] != 1:
                raise ValueError('Source used another native endpoint protocol')
            rechecks.append(dict(directory=row['directory'], execution_sha256=row['execution_sha256'],
                chain_sha256=object_digest(chain), passed=True, protocol_commands=dict(commands)))
            if row['repetition'] == 0:
                tags, phase_tx = message_tags(tx, c)
                if set(tags) != {m['token'] for m in result['network_messages']}: raise ValueError('Missing/extra message roles')
                account = chain_accounting(result, chain, tags, phase_tx)
                supply = supply_and_dma(c, tx, result)
                network, fact, order = network_profile(c, result, tags, account['selected_messages'], reg['activity_bin_cycles'])
                profile = dict(chain=account, supply=supply, network=network, native_protocol_commands=dict(commands))
                write_json(output/(row['directory']+'-PROFILE.json'), profile); profiles[key] = profile
                cells[key] = summary(profile)
                if row['condition'].startswith('shared_'):
                    facts[key], orders[key] = fact, order
                if row['layout'] == 'remote_balanced' and row['condition'].startswith('shared_'):
                    example = next(t for t in tx if t['operation'] == 'first17' and t['data'] == 'w17')
                    timelines[row['condition']] = timeline(example, result)
                if row['condition'] == 'shared_pipeline':
                    previous = 'shared_whole/'+row['layout']
                    packets[row['layout']] = compare_packet_facts(facts.pop(previous), facts.pop(key), orders.pop(previous), orders.pop(key))
            print('checked', row['directory'], flush=True); del result
        if len(cells) != 6 or len(rechecks) != 18: raise ValueError('Incomplete analysis')
        for condition in reg['conditions']:
            for layout in reg['layouts']:
                cell = [r for r in rechecks if r['directory'].startswith(layout+'-'+condition+'-rep-')]
                if len(cell) != 3 or len({r['execution_sha256'] for r in cell}) != 1: raise ValueError('Unstable source repetitions')
        differences = {}
        for layout in reg['layouts']:
            old = profiles['shared_whole/'+layout]; new = profiles['shared_pipeline/'+layout]
            matched = match_movements(old['supply']['movements'], new['supply']['movements'])
            write_json(output/(layout+'-MATCHED_MOVEMENTS.json'), matched)
            buckets = set(old['chain']['totals']) | set(new['chain']['totals'])
            deltas = {k: new['chain']['totals'].get(k, 0)-old['chain']['totals'].get(k, 0) for k in sorted(buckets)}
            app_delta = new['chain']['application_cycles']-old['chain']['application_cycles']
            if sum(deltas.values()) != app_delta: raise ValueError('Critical difference does not close')
            differences[layout] = dict(application_delta=app_delta, critical_accounting_delta=deltas,
                scope='Difference of selected observed chains; not independent causal contributions')
        for controller_budget in ('controller_dma_descriptor_budget', 'controller_fragment_slot_budget', 'endpoint_rx_budget_bytes'):
            if reg[controller_budget] is not None: raise ValueError('No hardware budget is registered for this analysis')
        checks = dict(passed=True, artifact_hashes_checked=len(complete['artifacts_sha256']),
            application_source_hashes_checked=len(start['source_hashes']), applications_reaudited=len(rechecks),
            tests=receipt['tests'], model_policy_unchanged=True, new_simulations=0, checks=rechecks)
        write_json(output/'CHECKED.json', checks)
        write_json(output/'RESULTS.json', dict(cells=cells, critical_differences=differences, packet_comparisons=packets,
            source_run=str(source), descriptor_contract='unmodeled', aggregate_fragment_contract='unmodeled', rx_contract='uncertified',
            hardware_principal_contract='not selected; no hardware budgets', D1_reference='v1 only; unchanged; applications deferred'))
        write_json(output/'EXAMPLE_TIMELINE.json', timelines)
        make_figures(output, cells, timelines)
        elapsed = time.perf_counter()-started; report(output, cells, packets, differences, checks, elapsed)
        write_json(output/'COST.json', dict(wall_seconds=time.perf_counter()-started, cpu_seconds=time.process_time()-cpu,
            python_peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, new_simulations=0,
            scope='Saved-artifact hashing, re-audit, observation derivation, plots and report; no simulator cost'))
        write_json(output/'COMPLETE.json', dict(complete=True, source_commit=commit,
            artifacts_sha256={p.name: digest(p) for p in output.iterdir() if p.is_file()}))
    except BaseException as exc:
        write_json(output/'FAILED.json', dict(type=type(exc).__name__, message=str(exc))); raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tests', type=Path, required=True); args = p.parse_args(); run(args.output, args.tests)
