"""Independent fixed-contract event and cost comparison, excluding profiled cost."""
from pathlib import Path
import statistics

from wafer_sim.analysis.memory_boundary import audit_occupancy
from wafer_sim.analysis.timing import audit
from wafer_sim.io import digest, object_digest, read_json


def checked_runs(root):
    root=Path(root)
    manifest=read_json(root/'COMPLETE.json')
    if not manifest['all_registered_work_complete']:
        raise ValueError('Incomplete cost probe')
    for name,expected in manifest['artifacts_sha256'].items():
        if digest(root/name)!=expected:
            raise ValueError('Changed probe artifact: '+name)
    started=read_json(root/'STARTED.json')
    rows=read_json(root/'LAUNCHES.json');seen=set();records={}
    for row in rows:
        key=row['shape'],row['repeat']
        if key in seen or row['profiled']!=(row['repeat']==3):
            raise ValueError('Repeated sample or invalid profiler label')
        seen.add(key)
        directory=Path(row['worker'])
        if directory.resolve()!=(root/f'{key[0]}-{key[1]}').resolve():
            raise ValueError('Worker outside registered probe')
        measured=read_json(directory/'MEASURED.json')
        execution=read_json(directory/'execution.json')
        if (not measured['complete'] or measured['affinity']!=started['affinity'] or
                measured['execution_identity']!=object_digest(execution) or
                measured['input_identity']!=object_digest(read_json(directory/'INPUT.json'))):
            raise ValueError('Probe identity, completion or affinity mismatch')
        records[key]=(directory,measured,execution)
    if seen!={(s,r) for s in ('s16','s64') for r in range(4)}:
        raise ValueError('Incomplete probe matrix')
    return started,records,len(manifest['artifacts_sha256'])


def analyze(before,after,accepted,prepare_case):
    old,old_records,old_count=checked_runs(before)
    new,new_records,new_count=checked_runs(after)
    if old['affinity']!=new['affinity'] or old['contract']!=new['contract']:
        raise ValueError('Changed affinity or target contract')
    accepted=Path(accepted)
    if digest(accepted/'COMPLETE.json')!=old['accepted_manifest_sha256'] or (
            old['accepted_manifest_sha256']!=new['accepted_manifest_sha256']):
        raise ValueError('Different accepted input source')
    rows=[];checks=[]
    for shape in ('s16','s64'):
        source=accepted/(shape+'__burst_256');descriptor=source/'INPUT_CONFIG.json'
        # Authenticate every accepted file used here, not merely its manifest.
        manifest=read_json(accepted/'COMPLETE.json')['artifacts_sha256']
        files=[descriptor,source/'bounded-0/execution.json',source/'bounded-0/MEASURED.json',
               source/'bounded-0/online_protocol.jsonl']
        for f in files:
            if digest(f)!=manifest[str(f.relative_to(accepted))]:
                raise ValueError('Changed accepted evidence: '+str(f))
        binding,timing=prepare_case(read_json(descriptor))
        expected=object_digest(read_json(source/'bounded-0/execution.json'))
        expected_network=read_json(source/'bounded-0/MEASURED.json')['network_identity']['binary_sha256']
        expected_protocol=digest(source/'bounded-0/online_protocol.jsonl')
        for label,records in (('before',old_records),('after',new_records)):
            for repeat in range(4):
                directory,measured,execution=records[shape,repeat]
                if (object_digest(execution)!=expected or
                        measured['network_identity']['binary_sha256']!=expected_network or
                        digest(directory/'online_protocol.jsonl')!=expected_protocol):
                    raise ValueError('Event, native binary or complete protocol divergence')
                if not audit(binding,timing,execution)['passed'] or not audit_occupancy(execution['boundary'])['passed']:
                    raise ValueError('Independent service/lifetime audit failed')
                checks.append(dict(version=label,shape=shape,repeat=repeat,execution_sha256=expected,
                    protocol_sha256=expected_protocol,independent_audit=True))
        row=dict(shape=shape,application_cycles=old_records[shape,0][2]['application_cycles'])
        for label,records in (('before',old_records),('after',new_records)):
            samples=[records[shape,r][1] for r in range(3)]
            for phase in ('input_graph_binding','backend_initialization','execution',
                          'close_and_network_serialization','result_serialization','independent_audit'):
                for metric in ('wall_seconds','python_cpu_seconds'):
                    values=[next(p[metric] for p in s['phases'] if p['phase']==phase) for s in samples]
                    row[f'{label}_{phase}_{metric}']=statistics.median(values)
                    if phase=='execution':
                        row[f'{label}_{phase}_{metric}_min']=min(values)
                        row[f'{label}_{phase}_{metric}_max']=max(values)
            row[label+'_python_peak_rss_kib']=max(s['python_lifetime_peak_rss_kib'] for s in samples)
            row[label+'_native_peak_rss_kib']=max(s['native_peak_rss_kib'] for s in samples)
            row[label+'_native_lifetime_cpu_seconds']=statistics.median(s['native_total_cpu_seconds'] for s in samples)
            functions=read_json(records[shape,3][0]/'PROFILE.json')['functions']
            admission=next(f for f in functions if f['file'].endswith('/execution/storage.py') and f['function']=='admission')
            row[label+'_profile_admission_calls']=admission['calls']
            row[label+'_profile_admission_cumulative_seconds']=admission['cumulative_seconds']
        row['execution_speedup']=row['before_execution_wall_seconds']/row['after_execution_wall_seconds']
        row['execution_identity']=expected
        rows.append(row)
    return dict(rows=rows,checks=checks,before_source=old['source_commit'],after_source=new['source_commit'],
        checked_artifacts=old_count+new_count,affinity=new['affinity'],profiled_samples_excluded=True,
        scope='Identical service and native protocol events; implementation cost only; sequential cold batches, not calibrated hardware')
