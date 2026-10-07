"""Read back registered complete runs, service characterization and host cost."""
from pathlib import Path
from statistics import median
from dataclasses import asdict

from wafer_sim.adapters import wow
from wafer_sim.adapters.spatial import bind
from wafer_sim.adapters.timing import TimedTarget
from wafer_sim.adapters.transformer import place_block
from wafer_sim.adapters.wow_target import build_wow_target
from wafer_sim.analysis.model_fidelity import compare_execution
from wafer_sim.analysis.online_network import audit_messages
from wafer_sim.analysis.timing import audit
from wafer_sim.analysis.transfer_granularity import isolated_comparison, summarize_isolated
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.analysis.packet_pipeline import audit_pipeline
from wafer_sim.adapters.packet_pipeline import contract as pipeline_contract
from wafer_sim.execution.plan import ExecutionPolicy
from wafer_sim.io import digest, object_digest, read_json
from wafer_sim.workloads.transformer import build_block


def stats(values):
    return dict(median=median(values),minimum=min(values),maximum=max(values),samples=len(values))


def compare_messages(reference,candidate):
    original={m['token']:m for m in reference};proposed={m['token']:m for m in candidate}
    if len(original)!=len(reference) or len(proposed)!=len(candidate) or set(original)!=set(proposed):
        raise ValueError('Message comparison does not cover identical logical transfers')
    rows=[]
    for token,m in original.items():
        p=proposed[token]
        if any(m[k]!=p[k] for k in ('source','destination','bytes','expected_flits')):
            raise ValueError('Candidate message work differs')
        fine=m['finish']-m['ready'];rough=p['finish']-p['ready']
        if min(fine,rough)<=0: raise ValueError('Nonpositive message service')
        fixed={tuple(f['router_path']) for f in p['flits']}
        same=len(fixed)==1 and all(tuple(f['router_path']) in fixed for f in m['flits'])
        rows.append(dict(token=token,source=m['source'],destination=m['destination'],bytes=m['bytes'],
            reference_ready=m['ready'],candidate_ready=p['ready'],reference_finish=m['finish'],candidate_finish=p['finish'],
            reference_service_cycles=fine,candidate_service_cycles=rough,
            error_cycles=rough-fine,ape_percent=100*abs(rough/fine-1),matched_paths=same))
    return rows


def residual_link_order(reference,candidate,comparisons):
    """Locate the first link divergence of the worst same-path message.

    A read-only diagnostic selected by error magnitude, not a tuned model rule.
    Packet ordinals are ordered by injection, never joined by simulator flit ID.
    """
    eligible=[r for r in comparisons if r['matched_paths'] and r['error_cycles']]
    if not eligible: return None
    selected=max(eligible,key=lambda r:r['ape_percent']);token=selected['token']
    a=next(m for m in reference if m['token']==token);b=next(m for m in candidate if m['token']==token)
    differences=[]
    for ordinal,(f,g) in enumerate(zip(sorted(a['flits'],key=lambda f:f['injected']),
                                     sorted(b['flits'],key=lambda f:f['injected']))):
        for x,y in zip(f['link_arrivals'],g['link_arrivals']):
            if x['cycle']-a['ready']!=y['cycle']-b['ready']:
                differences.append(dict(packet_ordinal=ordinal,source=x['source'],destination=x['destination'],
                    reference_relative_cycle=x['cycle']-a['ready'],candidate_relative_cycle=y['cycle']-b['ready']))
    if not differences: return dict(selected_message=token,first_link_divergence=None)
    first=min(differences,key=lambda r:r['reference_relative_cycle'])
    edge=first['source'],first['destination'];operation=token.rsplit('/phase/',1)[0]
    events={}
    for backend,messages,origin in [('booksim',reference,a['ready']),('packet_pipeline',candidate,b['ready'])]:
        rows=[]
        for m in messages:
            if m['token'].rsplit('/phase/',1)[0]!=operation or m['destination']!=a['destination']: continue
            for ordinal,f in enumerate(sorted(m['flits'],key=lambda f:f['injected'])):
                for h in f['link_arrivals']:
                    if (h['source'],h['destination'])==edge:
                        rows.append(dict(backend=backend,token=m['token'],source_endpoint=m['source'],
                            packet_ordinal=ordinal,cycle=h['cycle'],relative_cycle=h['cycle']-origin))
        events[backend]=sorted(rows,key=lambda r:r['relative_cycle'])
    return dict(selected_message=token,first_link_divergence=first,edge=edge,events=events,
        identical_link_arrival_slots=[r['relative_cycle'] for r in events['booksim']]==[
            r['relative_cycle'] for r in events['packet_pipeline']],
        selection='largest same-path message service APE; first divergent link timestamp')


def reconstruct(descriptor):
    config,wc=descriptor['experiment'],descriptor['workload']
    exported=read_json(descriptor['network_json'])
    cm={k:wc[k] for k in ('region_capacity_bytes','compute_rates','memory_bytes_per_cycle')}
    cm['scope']='Common analytical compute/memory; not calibrated to WoW'
    target,timing,contract=build_wow_target(exported,cm,config['flit_bytes'])
    block=build_block(**wc['block'])
    workers=wow.rank_mapping(exported['endpoints'],block.dimensions['shards'],config['mapping'])
    placement=place_block(block,workers)
    binding=bind(block.workload,target,placement,execution_policy=ExecutionPolicy(**config['execution_policy']))
    identity=dict(logical_workload=asdict(block.workload),tensors=block.tensors,operators=block.operators,
        collectives=block.collectives,mapping=asdict(placement),target=asdict(target),timing=asdict(timing),
        resource_contract=contract,worker_endpoints=workers,execution_policy=config['execution_policy'])
    return binding,timing,identity


def analyze(root):
    root=Path(root)
    complete=read_json(root/'COMPLETE.json')
    if not complete['measurement_complete'] or not complete['all_registered_work_complete']:
        raise ValueError('Incomplete registered work cannot enter the accepted comparison')
    hashes=complete['artifacts_sha256']
    for name,expected in hashes.items():
        if digest(root/name)!=expected: raise ValueError('Changed artifact: '+name)
    started=read_json(root/'STARTED.json');registration=started['registration']
    launches=read_json(root/'LAUNCHES.json')
    rows=[];costs=[];details={};isolated_rows=[];receipts=[]
    backends=registration.get('backends',['booksim','coarse'])
    expected_workers=len(registration['cases'])*len(backends)*(registration['cold_repetitions']+1)
    if len(launches)!=expected_workers: raise ValueError('Missing or extra measurement workers')
    for case in registration['cases']:
        name=case['name'];directory=root/name
        descriptor=read_json(directory/'INPUT_CONFIG.json')
        binding,timing,identity=reconstruct(descriptor)
        target=TimedTarget(binding,timing)
        pipe_model=pipeline_contract(read_json(descriptor['network_json']),descriptor['experiment']['flit_bytes']) if 'packet_pipeline' in backends else None
        workers=[l for l in launches if l['case']==name]
        executions={};identities={};measurements={}
        for launch in workers:
            path=Path(launch['worker']);record=read_json(path/'MEASURED.json')
            expected_input=object_digest(identity)
            if (record['input_identity']!=expected_input or object_digest(read_json(path/'INPUT.json'))!=expected_input
                    or record['affinity']!=started['affinity'] or record['backend']!=launch['backend']):
                raise ValueError('Input, backend or CPU affinity differs')
            expected_trials=registration['graph_reuse_repetitions'] if launch['mode']=='reuse_graph' else 1
            if len(record['trials'])!=expected_trials: raise ValueError('Missing measured repetitions')
            backend=launch['backend'];key=launch['mode'],backend
            for trial in record['trials']:
                td=path/f"trial-{trial['repetition']}"
                result=read_json(td/'execution.json')
                if object_digest(result)!=trial['execution_identity']: raise ValueError('Execution digest mismatch')
                checked=audit(binding,timing,result)
                if checked!=read_json(td/'AUDIT.json'): raise ValueError('Independent audit changed')
                if backend=='booksim':
                    if read_json(td/'online_network.json')['messages']!=result['network_messages']:
                        raise ValueError('Native messages differ from timed execution')
                    reference=read_json(td/'reference/CHECKED.json')
                    if not reference['passed'] or reference['standalone_binary_sha256']!=started['binary_sha256']['standalone']:
                        raise ValueError('Unverified native interface')
                elif backend=='packet_pipeline':
                    if result['packet_contract']!=pipe_model: raise ValueError('Candidate contract differs from pinned config')
                    closed=read_json(td/'pipeline_network.json')
                    if (not closed['complete'] or closed['messages']!=result['network_messages']
                            or closed['packet_services']!=result['packet_services']):
                        raise ValueError('Pipeline close does not match execution evidence')
                receipts.append(dict(case=name,backend=backend,worker=path.name,repetition=trial['repetition'],audit=checked))
                identities.setdefault(backend,set()).add(trial['execution_identity'])
                executions.setdefault(backend,result)
                measured={p['phase']:p for p in trial['measured_phases']}
                validation={p['phase']:p for p in trial['validation_phases']}
                values={p+'_seconds':v['wall_seconds'] for p,v in measured.items()}
                values.update({p+'_seconds':v['wall_seconds'] for p,v in validation.items()})
                values.update(execution_cpu_python_seconds=measured['timed_execution']['python_cpu_seconds'],
                    backend_total_cpu_seconds=sum(p['python_cpu_seconds'] for p in measured.values())+trial['native_total_cpu_seconds'],
                    native_total_cpu_seconds=trial['native_total_cpu_seconds'],
                    backend_total_wall_seconds=sum(p['wall_seconds'] for p in measured.values()),
                    python_peak_rss_kib=trial['python_lifetime_peak_rss_kib'],
                    native_peak_rss_kib=trial['native_lifetime_peak_rss_kib'],
                    rss_separate_peaks_upper_bound_kib=trial['python_lifetime_peak_rss_kib']+trial['native_lifetime_peak_rss_kib'],
                    artifact_bytes=trial['artifact_bytes'],services=len(result['services']),phases=len(result['phases']),
                    packet_services=len(result.get('packet_services',[])))
                if launch['mode']=='cold':
                    # This includes imports/startup/exit/measurement bookkeeping, but excludes
                    # the explicitly timed audit and second native run. Never call raw worker
                    # wall time the network execution cost.
                    values['cold_worker_less_validation_seconds']=launch['worker_wall_seconds']-sum(
                        p['wall_seconds'] for p in trial['validation_phases'])
                measurements.setdefault(key,[]).append(values)
            measurements.setdefault(('setup_'+launch['mode'],backend),[]).append({
                p['phase']+'_seconds':p['wall_seconds'] for p in record['setup_phases']})
        if any(len(v)!=1 for v in identities.values()): raise ValueError('Repeat events differ')
        if 'accepted_reference_run' in registration:
            prior_root=Path(registration['accepted_reference_run']);manifest=read_json(prior_root/'COMPLETE.json')
            if not manifest['all_registered_work_complete']: raise ValueError('Reference was not complete')
            for backend in ('booksim','coarse'):
                relative=f'{name}/cold-0-{backend}/trial-0/execution.json'
                if digest(prior_root/relative)!=manifest['artifacts_sha256'][relative]: raise ValueError('Accepted reference changed')
                if object_digest(read_json(prior_root/relative))!=next(iter(identities[backend])):
                    raise ValueError('Original backend events changed under refinement integration')
        for (mode,backend),samples in sorted(measurements.items()):
            costs.append(dict(case=name,mode=mode,backend=backend,
                metrics={k:stats([s[k] for s in samples]) for k in samples[0]}))
        native,coarse=executions['booksim'],executions['coarse']
        detail=compare_execution(binding,timing,native,coarse)
        fine,rough=native['application_cycles'],coarse['application_cycles']
        ape=100*abs(rough/fine-1)
        isolated=read_json(directory/'isolated/SERVICES.json')
        if isolated['input_identity']!=object_digest(identity): raise ValueError('Isolated input changed')
        rebuilt=[];pipe_isolated=[]
        expected={}
        for op,plan in binding.plans.items():
            for i,phase in enumerate(plan.phases):
                if phase.transfer:
                    t=phase.transfer
                    expected.setdefault((t.source_endpoint,t.destination_endpoint,t.size_bytes),[]).append(f'{op}/phase/{i}')
        seen=set()
        for original in isolated['rows']:
            td=directory/'isolated'/f"transfer-{original['index']}"
            record=read_json(td/'online_network.json')
            audit_messages(binding.network,record['messages'])
            if len(record['messages'])!=1 or not record['complete'] or not record['final']['drained']:
                raise ValueError('Not an isolated complete drained transfer')
            receipt=read_json(td/'reference/CHECKED.json')
            if not receipt['passed'] or receipt['standalone_binary_sha256']!=started['binary_sha256']['standalone']:
                raise ValueError('Isolated reference mismatch')
            m=record['messages'][0];key=m['source'],m['destination'],m['bytes']
            if key in seen or key not in expected or original['logical_tokens']!=expected[key]:
                raise ValueError('Missing, duplicated or foreign component transfer')
            seen.add(key)
            row=isolated_comparison(target,m)
            row.update(index=original['index'],logical_tokens=expected[key])
            if object_digest(row)!=object_digest(original): raise ValueError('Isolated arithmetic changed')
            rebuilt.append(row)
            if pipe_model:
                candidate=read_json(td/'PIPELINE.json')
                if not candidate['complete'] or candidate['packet_contract']!=pipe_model:
                    raise ValueError('Incomplete or different isolated pipeline contract')
                audit_pipeline(binding,timing,candidate['messages'],candidate['packet_services'],pipe_model)
                comparison=compare_messages(record['messages'],candidate['messages'])
                pipe_isolated.extend(comparison)
            flits=sorted(m['flits'],key=lambda f:f['ejected'])
            link_spans=[max(f['link_arrivals'][j]['cycle'] for f in flits)-min(f['link_arrivals'][j]['cycle'] for f in flits)
                        for j in range(len(flits[0]['link_arrivals']))] if row['matched_path'] else None
            isolated_rows.append(dict(case=name,**row,physical_links=len(row['coarse_path'])-1,
                first_flit_completion_boundary=flits[0]['ejected']+1,
                observed_ejection_intervals=[b['ejected']-a['ejected'] for a,b in zip(flits,flits[1:])],
                observed_per_link_arrival_spans=link_spans))
        if seen!=set(expected): raise ValueError('Component matrix incomplete')
        summary=summarize_isolated(rebuilt,registration['message_error_tolerance_percent'])
        if summary!=isolated['summary']: raise ValueError('Component summary mismatch')
        rows.append(dict(case=name,sequence=case['sequence'],reference_cycles=fine,coarse_cycles=rough,
            error_cycles=rough-fine,application_ape_percent=ape,
            application_target_met=ape<=registration['application_error_tolerance_percent'],
            isolated=summary,critical_chain_cycles={k:v['cycles'] for k,v in detail['critical_chains'].items()},
            complete_operations=len(native['operations']),message_count=len(native['network_messages']),
            logical_message_bytes=sum(m['bytes'] for m in native['network_messages']),
            native_flits=sum(m['expected_flits'] for m in native['network_messages']),
            peak_region_bytes=max(native['peak_bytes'].values()),
            full_application_route_mismatched_flits=detail['flits_on_different_path'],
            coarse_network_queue_cycles=detail['coarse_network_queue_cycles'],
            maximum_native_first_injection_wait=max(m['first_inject']-m['ready'] for m in native['network_messages']),
            input_identity=object_digest(identity),repeated_execution_identities={k:next(iter(v)) for k,v in identities.items()}))
        if pipe_model:
            pipeline=executions['packet_pipeline'];pcycles=pipeline['application_cycles']
            comparisons=compare_messages(native['network_messages'],pipeline['network_messages'])
            isolated_matched=[r for r in pipe_isolated if r['matched_paths']]
            detail['pipeline']=dict(messages=comparisons,isolated_messages=pipe_isolated,
                critical_chain=critical_chain(binding,pipeline),
                residual=residual_link_order(native['network_messages'],pipeline['network_messages'],comparisons))
            rows[-1].update(pipeline_cycles=pcycles,pipeline_application_ape_percent=100*abs(pcycles/fine-1),
                pipeline_application_target_met=100*abs(pcycles/fine-1)<=registration['application_error_tolerance_percent'],
                pipeline_isolated_max_ape_percent=max((r['ape_percent'] for r in isolated_matched),default=None),
                pipeline_isolated_matched_paths=len(isolated_matched),
                pipeline_isolated_target_met=all(r['ape_percent']<=registration['message_error_tolerance_percent'] for r in isolated_matched) if isolated_matched else None,
                pipeline_message_mape_percent=sum(r['ape_percent'] for r in comparisons)/len(comparisons),
                pipeline_message_max_ape_percent=max(r['ape_percent'] for r in comparisons),
                pipeline_message_matched_max_ape_percent=max((r['ape_percent'] for r in comparisons if r['matched_paths']),default=None),
                pipeline_packet_services=len(pipeline['packet_services']),
                pipeline_packet_queue_cycles=sum(e['start']-e['ready'] for e in pipeline['packet_services']))
            rows[-1]['coarse_message_max_ape_percent']=max(100*abs(r['service_error_cycles'])/r['reference_duration'] for r in detail['messages'])
            rows[-1]['critical_chain_cycles']['packet_pipeline']=detail['pipeline']['critical_chain']['cycles']
        details[name]=detail
    acceptance=dict(source_run=str(root),source_commit=started['source_commit'],
        complete_manifest_sha256=digest(root/'COMPLETE.json'),checked_artifact_count=len(hashes),
        repeated_full_executions=len(receipts),isolated_transfers=len(isolated_rows),
        independent_audits=receipts,source_run_manifest=complete,
        binary_sha256=started['binary_sha256'],affinity=started['affinity'],
        python=started['python'],packages=started['packages'],
        load_average_range=[min(l['load_before'][0] for l in launches),max(l['load_after'][0] for l in launches)])
    return dict(rows=rows,costs=costs,isolated_transfers=isolated_rows,
                registration=registration,common_cost=read_json(root/'COMMON_COST.json')),details,acceptance
