"""Declared interfaces, fragment conservation and causal policy regressions."""
import copy
from dataclasses import replace
from pathlib import Path
import unittest

from wafer_sim.architecture.wafer_machine import from_config
from wafer_sim.architecture.spatial import Target
from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine
from wafer_sim.adapters.memory_periphery import compile_periphery, bind_periphery, TransactionPolicy
from wafer_sim.adapters.spatial import validate_target
from wafer_sim.analysis.memory_periphery import audit_periphery
from wafer_sim.execution.plan import Placement
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json
from wafer_sim.workloads.spatial import Workload, DataObject, Operation


def fixture(size=65536, write=False, two_inputs=False):
    cfg = read_json(Path(__file__).resolve().parents[1]/'configs/wafer_machine.json'); cfg['array'] = [2, 2]
    c = compile_periphery(from_config(cfg))
    data = [DataObject('x', size, None, False, 'fixture'), DataObject('y', size, 'f', True, 'fixture')]
    inputs = ('x',)
    homes = {'x': 'sram-0' if write else 'dram-0-0', 'y': 'dram-0-1' if write else 'sram-0'}
    if two_inputs:
        data.append(DataObject('z', size, None, False, 'fixture')); inputs += ('z',); homes['z'] = 'dram-0-1'
    w = Workload(tuple(data), (Operation('f', inputs, ('y',), (('mac', 256),), 0, (), 'fixture'),))
    p = Placement({'f': 'c0'}, homes); policy = TransactionPolicy('pipeline')
    b, tx = bind_periphery(w, c, p, policy)
    return c, w, p, policy, b, tx


class MemoryPeripheryTests(unittest.TestCase):
    def test_shared_interface_has_one_endpoint_but_distinct_bank_ports(self):
        c, *_ = fixture()
        self.assertEqual(c.endpoints['dram-0-0'], c.endpoints['dram-0-1'])
        self.assertNotEqual(c.endpoints['sram-0'], c.endpoints['dram-0-0'])
        self.assertEqual(len(c.target.network.endpoint_routers), 9)
        self.assertEqual(len(c.timing.endpoints), 9)
        self.assertEqual(len({s.resource for s in c.timing.services if s.resource.startswith('dram-')}), 8)
        validate_target(c.target)

    def test_undeclared_alias_and_inconsistent_interface_ownership_rejected(self):
        c, *_ = fixture()
        with self.assertRaisesRegex(ValueError, 'One memory region'):
            validate_target(Target(c.target.memory, c.target.compute, c.target.network))
        first = c.target.network_interfaces[0]
        bad = replace(first, memory_regions=('dram-0-0',))
        with self.assertRaisesRegex(ValueError, 'ownership'):
            validate_target(replace(c.target, network_interfaces=(bad, *c.target.network_interfaces[1:])))

    def test_storage_partition_count_does_not_multiply_controller_interfaces(self):
        c, *_ = fixture(); m = c.physical
        bank = next(s for s in m.stores if s.id == 'dram-0-0')
        m = replace(m, stores=(*m.stores, replace(bank, id='dram-0-2')))
        new = compile_periphery(m)
        self.assertEqual(len(new.timing.endpoints), len(c.timing.endpoints))
        self.assertEqual(new.endpoints['dram-0-2'], c.endpoints['dram-0-0'])

    def test_single_fragment_retains_whole_object_timing_for_read_and_write(self):
        for write in (False, True):
            c, w, p, policy, b, tx = fixture(64, write)
            old, _ = bind_periphery(w, c, p, TransactionPolicy('whole'))
            r = execute(b, c.timing); whole = execute(old, c.timing)
            self.assertEqual(r['application_cycles'], whole['application_cycles'])
            self.assertTrue(audit_periphery(w, p, c, b, tx, policy, r)['passed'])

    def test_partial_last_fragment_has_exact_bytes_and_one_control(self):
        for write in (False, True):
            c, w, p, policy, b, tx = fixture(65537, write)
            self.assertEqual([x['bytes'] for x in tx[0]['chunks']], [4096]*16 + [1])
            r = execute(b, c.timing)
            checked = audit_periphery(w, p, c, b, tx, policy, r)
            self.assertEqual(checked['payload_bytes']['write' if write else 'read'], 65537)
            command = r['resources']['controller-0/command']
            self.assertEqual(command['requests'], 1); self.assertEqual(command['work']['bytes'], 16)

    def test_bank_latency_overlaps_and_window_waits_for_destination_commit(self):
        c, w, p, policy, b, tx = fixture(); r = execute(b, c.timing)
        phases = {x['phase']: x for x in r['phases']}
        chunks = tx[0]['chunks']
        services = {e['token']: e for e in r['services'] if e['resource'] == 'dram-0-0/port'}
        first, second = (services[f"f/phase/{chunks[j]['source_phase']}"] for j in (0, 1))
        self.assertEqual(first['resource_released'], second['start'])
        self.assertLess(second['start'], first['finish'])
        for j in range(4, len(chunks)):
            self.assertGreaterEqual(phases[chunks[j]['source_phase']]['ready'],
                                    phases[chunks[j-4]['destination_phase']]['finish'])
        audit_periphery(w, p, c, b, tx, policy, r)

    def test_independent_operands_remain_sequential_and_reservations_unchanged(self):
        c, w, p, policy, b, tx = fixture(two_inputs=True); r = execute(b, c.timing)
        whole, _ = bind_machine(w, c, p)
        self.assertEqual(b.plans['f'].reservations, whole.plans['f'].reservations)
        phases = {x['phase']: x for x in r['phases']}
        first_end = max(phases[x['destination_phase']]['finish'] for x in tx[0]['chunks'])
        self.assertEqual(phases[tx[1]['request_phase']]['ready'], first_end)
        self.assertEqual(r['output_ready']['y'], r['operations']['f']['retired'])
        audit_periphery(w, p, c, b, tx, policy, r)

    def test_offset_and_window_dependency_tampering_fail_independent_audit(self):
        c, w, p, policy, b, tx = fixture(); r = execute(b, c.timing)
        bad = copy.deepcopy(tx); bad[0]['chunks'][1]['offset'] -= 1
        with self.assertRaisesRegex(ValueError, 'offset'):
            audit_periphery(w, p, c, b, bad, policy, r)
        plan = b.plans['f']; deps = list(plan.dependencies)
        deps[tx[0]['chunks'][4]['source_phase']] = (tx[0]['command_phase'],)
        wrong = replace(b, plans={'f': replace(plan, dependencies=tuple(deps))})
        altered = execute(wrong, c.timing)
        with self.assertRaisesRegex(ValueError, 'causal/window'):
            audit_periphery(w, p, c, wrong, tx, policy, altered)

    def test_missing_ack_early_publication_and_truncation_are_not_complete(self):
        c, w, p, policy, b, tx = fixture(write=True); r = execute(b, c.timing)
        early = copy.deepcopy(r); early['output_ready']['y'] -= 1
        with self.assertRaises(ValueError): audit_periphery(w, p, c, b, tx, policy, early)
        missing = copy.deepcopy(tx); missing[0]['ack_phase'] = missing[0]['chunks'][-1]['payload_phase']
        with self.assertRaises(ValueError): audit_periphery(w, p, c, b, missing, policy, r)
        with self.assertRaises(TimeoutError): execute(b, c.timing, cycle_limit=1)

    def test_invalid_policy_rejected_before_execution(self):
        for kwargs in ({'kind': 'magic'}, {'chunk_bytes': 0}, {'window_chunks': True}):
            with self.assertRaises(ValueError): TransactionPolicy(**kwargs)
