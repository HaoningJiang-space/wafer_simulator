"""Read accepted geometry/resources and pin source evidence; never run a simulator."""
import argparse
from collections import Counter
from pathlib import Path
import platform
import subprocess

from wafer_sim.io import read_json, write_json, digest


def main():
    if platform.node().split('.')[0] != 'eex005': raise SystemExit('Run on eex005')
    parser = argparse.ArgumentParser()
    parser.add_argument('accepted_tree_run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']): raise ValueError('Clean source required')
    if not args.output.is_absolute(): raise ValueError('Fresh absolute output required')
    args.output.mkdir(exist_ok=False)
    complete = read_json(args.accepted_tree_run/'COMPLETE.json')
    if not complete['all_execution_and_reference_checks_passed']: raise ValueError('Accepted run required')
    checked = 0
    for name, expected in complete['artifacts_sha256'].items():
        if digest(args.accepted_tree_run/name) != expected: raise ValueError('Changed accepted artifact '+name)
        checked += 1
    rows = []
    for placement in ('baseline','ours_rotated'):
        directory = args.accepted_tree_run/'memory-32'/placement
        exported, record = read_json(directory/'network.json'), read_json(directory/'execution.json')
        inputs = exported['inputs']
        degree = Counter()
        for link in inputs['links']:
            degree[link['src']] += 1; degree[link['dst']] += 1
        endpoints = Counter(e['router'] for e in exported['endpoints'])
        local = []
        for router, position in enumerate(inputs['placement']['chiplets']):
            chiplet = inputs['chiplets'][position['name']]
            if chiplet['type'] != 'compute': continue
            local.append(dict(router=router, endpoint_count=endpoints[router],
                exported_unit_count=chiplet['unit_count'], external_neighbor_links=degree[router],
                unit_access_latency=chiplet['unit_to_router_latency'],router_latency=chiplet['router_latency']))
        if any(r['endpoint_count']!=r['exported_unit_count'] for r in local): raise ValueError('Endpoint export mismatch')
        endpoint_rates = {e['endpoint']: (e['injection']['rate_numerator']/e['injection']['rate_denominator'])
                          for e in record['timing']['endpoints']}
        rows.append(dict(placement=placement, upstream_commit=exported['upstream_commit'],
            design=exported['design'], compute_routers=local,
            unit_count_histogram=dict(Counter(r['endpoint_count'] for r in local)),
            external_degree_histogram=dict(Counter(r['external_neighbor_links'] for r in local)),
            endpoint_injection_bytes_per_cycle=endpoint_rates,
            compute_resources=len(record['target']['compute']), memory_regions=len(record['target']['memory']),
            local_resource_parameters=record['resource_contract']['compute_memory_parameters'],
            network_frequency_hz=exported['resources']['network_frequency_hz'],
            network_json_sha256=digest(directory/'network.json'),
            execution_json_sha256=digest(directory/'execution.json')))
    paths = [
        'third_party/nw-design-for-wsi/config.py',
        'third_party/nw-design-for-wsi/export_to_rapidchiplet.py',
        'third_party/nw-design-for-wsi/rapidchiplet/booksim_wrapper.py',
        'third_party/nw-design-for-wsi/rapidchiplet/booksim2/src/trafficmanager.cpp',
        'src/wafer_sim/adapters/wow.py','src/wafer_sim/adapters/wow_target.py',
        'src/wafer_sim/adapters/spatial.py','src/wafer_sim/adapters/collectives.py',
        'src/wafer_sim/adapters/online_booksim.py','src/wafer_sim/adapters/native/online_booksim.cpp',
        'src/wafer_sim/execution/timing.py','src/wafer_sim/execution/storage.py']
    write_json(args.output/'BOUNDARY_AUDIT.json',dict(rows=rows,
        paper='https://arxiv.org/html/2603.05266v2#S3.SS2',
        accepted_run=str(args.accepted_tree_run), accepted_artifacts_checked=checked,
        accepted_completion_sha256=digest(args.accepted_tree_run/'COMPLETE.json'),
        source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        source_sha256={p:digest(repo/p) for p in paths},
        scope='Read-only source/accepted-input audit; no simulation, new hardware model or accuracy claim'))
    print([{k:v for k,v in r.items() if k in ('placement','unit_count_histogram','external_degree_histogram')} for r in rows])


if __name__ == '__main__': main()
