"""Readback of profiling observations, separate from baseline performance."""
import pstats

from wafer_sim.io import digest, object_digest, read_json


def checked_worker(directory, reference, manifest, mode):
    # Authenticate the existing comparison target before trusting its summary.
    for name in ('execution.json', 'MEASURED.json', 'online_protocol.jsonl'):
        key = str((reference/name).relative_to(reference.parent))
        if digest(reference/name) != manifest['artifacts_sha256'][key]:
            raise ValueError('Changed reference profile input: '+key)
    actual, expected = read_json(directory/'execution.json'), read_json(reference/'execution.json')
    if not actual['complete'] or object_digest(actual) != object_digest(expected):
        raise ValueError('Profiling changed execution events')
    if digest(directory/'online_protocol.jsonl') != digest(reference/'online_protocol.jsonl'):
        raise ValueError('Profiling changed native protocol')
    measured = read_json(directory/'MEASURED.json')
    checked = read_json(directory/'AUDIT.json')
    if measured['status'] != checked['status'] or measured['execution_sha256'] != object_digest(actual):
        raise ValueError('Invalid profiling worker audit')
    row = dict(mode=mode,application_cycles=actual['application_cycles'],
        exact_reference_execution=True,exact_reference_protocol=True,
        execution_sha256=object_digest(actual),protocol_sha256=digest(directory/'online_protocol.jsonl'),
        worker_phases=measured['phases'],native_total_cpu_seconds=measured['native_total_cpu_seconds'])
    if mode == 'native_sections':
        native=read_json(directory/'NATIVE_PROFILE.json')
        record=read_json(directory/'online_network.json')
        if (not native['complete'] or native['step_calls'] != record['final']['steps'] or
                native['observe_calls'] != native['step_calls'] or
                native['retired_record_calls'] != record['final']['flits'] or
                native['native_step_excluding_retire_record_seconds'] < 0):
            raise ValueError('Incomplete or inconsistent native profile')
        row.update(native_sections=native,native_binary_sha256=record['identity']['binary_sha256'])
    else:
        stats=pstats.Stats(str(directory/'worker.prof'))
        functions=[dict(file=k[0],line=k[1],function=k[2],primitive_calls=v[0],calls=v[1],
                        self_seconds=v[2],cumulative_seconds=v[3]) for k,v in stats.stats.items()]
        row.update(python_profile=dict(total_seconds=stats.total_tt,
            scope='Whole worker functions excluding initial driver imports; elapsed time includes native waits',
            functions=sorted(functions,key=lambda f:f['self_seconds'],reverse=True)))
    return row
