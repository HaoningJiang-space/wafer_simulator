"""Semantic cross-checks between saved events, inputs and measurement rows."""
import hashlib
import subprocess

from wafer_sim.io import object_digest, digest


# These changes strengthen acceptance or correct physical port validation.
# Historical source bytes remain verifiable in Git; recreated input identities
# and unchanged event hashes, not a blanket source exemption, establish reuse.
COMPATIBLE_READER_FIXES = frozenset({
    'src/wafer_sim/analysis/memory_periphery.py',
    'src/wafer_sim/analysis/memory_periphery_study.py',
    'src/wafer_sim/architecture/wafer_machine.py',
    'src/wafer_sim/adapters/wafer_machine.py',
    'src/wafer_sim/adapters/memory_periphery.py',
    'src/wafer_sim/experiments/memory_periphery.py',
})


def verify_source(repo, start):
    changed = {}
    for name, sha in start['source_hashes'].items():
        current = digest(repo/name)
        if current == sha: continue
        if name not in COMPATIBLE_READER_FIXES: raise ValueError('Changed frozen run source: '+name)
        archived = subprocess.check_output(['git', '-C', str(repo), 'show', start['source_commit']+':'+name])
        if hashlib.sha256(archived).hexdigest() != sha: raise ValueError('Archived source disagrees with run receipt')
        changed[name] = dict(archived_sha256=sha, current_sha256=current)
    return changed


def validate_rows(rows, reg):
    expected = {(condition, layout, None, rep)
                for condition in reg['conditions'] for layout in reg['layouts'] for rep in range(reg['repetitions'])}
    expected |= {(condition, None, component, 0) for condition in reg['conditions'] for component in reg['component_cases']}
    seen, directories = set(), set()
    for row in rows:
        key = (row['condition'], row['layout'], row['component'], row['repetition'])
        if type(row['repetition']) is not int or key not in expected or key in seen:
            raise ValueError('Duplicate or unregistered condition/layout/repetition')
        name = (f"{row['layout']}-{row['condition']}-rep-{row['repetition']}" if row['component'] is None else
                f"component-{row['component']}-{row['condition']}")
        if row['directory'] != name or name in directories:
            raise ValueError('Duplicate or mismatched saved directory')
        seen.add(key); directories.add(name)
    if seen != expected: raise ValueError('Missing registered saved executions')


def event_fields(identity, result, checked):
    makespan = max(r['finish'] for r in result['operations'].values())
    if makespan != checked['execution']['application_cycles'] or makespan != result['application_cycles']:
        raise ValueError('Audit makespan differs from operation events')
    return dict(condition=identity['condition'], layout=identity['layout'], component=identity['component'],
        application_cycles=makespan, execution_sha256=object_digest(result), input_sha256=object_digest(identity),
        physical_sha256=object_digest(identity['physical']),
        work_placement_sha256=object_digest(dict(workload=identity['workload'], placement=identity['placement'])),
        logical_transactions=checked['logical_transactions'], native_messages=len(result.get('network_messages', [])),
        native_flits=sum(len(m['flits']) for m in result.get('network_messages', [])),
        payload_bytes=checked['payload_bytes'], control_bytes=checked['control_bytes'],
        physical_kind_flits=checked['physical_kind_flits'], resources=result['resources'], peak_bytes=result['peak_bytes'],
        passed=checked['passed'])


def checked_row(row, measured, process, identity, result, checked):
    extra = {'directory', 'repetition', 'process_wall_seconds'}
    if set(row) != set(measured) | extra:
        raise ValueError('SUMMARY and MEASURED fields differ')
    for name in measured:
        if object_digest(row[name]) != object_digest(measured[name]):
            raise ValueError('SUMMARY differs from MEASURED: '+name)
    if object_digest(row['process_wall_seconds']) != object_digest(process['wall_seconds']):
        raise ValueError('SUMMARY process cost differs from PROCESS')
    derived = event_fields(identity, result, checked)
    for name, value in derived.items():
        if object_digest(row[name]) != object_digest(value):
            raise ValueError('Summary differs from audited execution: '+name)
    # Report event-derived values even though all stored values now agree.
    return {**measured, **derived, **{k: row[k] for k in extra}}
