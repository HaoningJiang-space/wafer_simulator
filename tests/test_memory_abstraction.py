"""Projection budget, asynchronous communication and independent-audit checks."""
import copy
from dataclasses import replace
import unittest

from test_wafer_machine import machine, one_read
from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine
from wafer_sim.adapters.memory_abstraction import project
from wafer_sim.adapters.uniform_memory_network import UniformMemoryNetwork
from wafer_sim.adapters.memory_machine_workload import place
from wafer_sim.analysis.memory_abstraction import audit, audit_projection, audit_network, selection
from wafer_sim.analysis.timed_attribution import critical_chain
from wafer_sim.execution.timing import execute
from wafer_sim.execution.plan import Transfer
from wafer_sim.workloads.memory_machine import build


class ClockNetwork:
    """Semantic clock fixture; never used for native acceptance."""
    def __init__(self):
        self.now, self.messages, self.pending = 0, [], {}

    def submit(self, token, t, cycle):
        self.pending[token] = dict(id=len(self.messages)+len(self.pending), token=token,
            ready=cycle, finish=cycle+7)

    def advance(self, until):
        self.now = min([until]+[m['finish'] for m in self.pending.values()])
        done = [k for k, v in self.pending.items() if v['finish'] == self.now]
        self.messages.extend(self.pending.pop(k) for k in done)
        return done


class MemoryAbstractionTests(unittest.TestCase):
    def test_spatial_and_controller_projections_do_not_change_binding(self):
        c, b, _ = one_read()
        for model in ('U1', 'S'):
            bb, t, spec = project(c, b, model)
            self.assertIs(bb, b); self.assertIs(t, c.timing)
            self.assertTrue(audit_projection(c, b, bb, t, spec)['passed'])

    def test_uniform_pools_totals_once_and_keeps_staging(self):
        c = compile_machine(machine()); w, meta = build(4, 8, 16)
        b, _ = bind_machine(w, c, place(meta, 'single_controller'))
        bb, timing, spec = project(c, b, 'U0')
        self.assertTrue(audit_projection(c, b, bb, timing, spec)['passed'])
        self.assertEqual(bb.memory['uniform/dram'].capacity_bytes, 8*67108864)
        rates = {s.resource: s.rate_numerator/s.rate_denominator for s in timing.services}
        self.assertEqual(rates['uniform/bank'], 8*32)
        self.assertEqual(rates['uniform/channel'], 4*64)
        self.assertEqual(rates['uniform/command'], 4*4)
        for op in b.plans:
            self.assertEqual([a for a in b.plans[op].reservations if a.key[0] == 'controller-staging'],
                             [a for a in bb.plans[op].reservations if a.key[0] == 'controller-staging'])
        self.assertIn('dram-0-0', b.memory)
        self.assertNotIn('uniform/dram', b.memory)

    def test_pool_budget_and_staging_tampering_are_rejected(self):
        c, b, _ = one_read(); bb, t, s = project(c, b, 'U0')
        bad = replace(t, services=tuple(replace(x, rate_numerator=x.rate_numerator*2)
                      if x.resource == 'uniform/bank' else x for x in t.services))
        with self.assertRaisesRegex(ValueError, 'budget'): audit_projection(c, b, bb, bad, s)
        plans = dict(bb.plans); plans['f'] = replace(plans['f'], reservations=tuple(
            a for a in plans['f'].reservations if a.key[0] != 'controller-staging'))
        with self.assertRaisesRegex(ValueError, 'staging'): audit_projection(c, b, replace(bb, plans=plans), t, s)

    def test_uniform_read_is_hand_calculable_and_audited(self):
        c, base, _ = one_read()
        b, t, s = project(c, base, 'U1')
        result = execute(b, t, network=UniformMemoryNetwork(ClockNetwork(), s))
        # Request12 + cmd4 + bank(2+30) + channel1 + response12
        # + staging write1 + operand read1 + compute1 + result write1.
        self.assertEqual(result['application_cycles'], 65)
        self.assertTrue(audit(c, base, b, t, s, result)['passed'])
        self.assertEqual(sum(critical_chain(b, result)['cycles'].values()), 65)
        bad = copy.deepcopy(result); bad['network_messages'][0]['finish'] -= 1
        with self.assertRaisesRegex(ValueError, 'Uniform'): audit_network(b.network, bad)
        bad = copy.deepcopy(result); bad['output_ready']['y'] -= 1
        with self.assertRaises(ValueError): audit(c, base, b, t, s, bad)

    def test_distance_removed_but_readiness_and_tail_padding_preserved(self):
        c, b, _ = one_read(); _, _, s = project(c, b, 'U1')
        network = UniformMemoryNetwork(ClockNetwork(), s)
        for token, size, home in (('local', 64, 'dram-0-0'), ('remote', 65, 'dram-3-0')):
            network.submit(token, Transfer('x', home, 'sram-0', c.endpoints[home], c.endpoints['sram-0'], size), 0)
        self.assertEqual(network.advance(11), [])
        self.assertEqual(network.advance(20), ['local'])
        self.assertEqual(network.now, 12)
        self.assertEqual(network.advance(20), ['remote'])
        self.assertEqual(network.now, 13)
        with self.assertRaises(ValueError): network.advance(12)

    def test_passthrough_stops_uniform_clock_at_native_completion(self):
        c, b, _ = one_read(); _, _, s = project(c, b, 'U1')
        native = ClockNetwork(); n = UniformMemoryNetwork(native, s)
        n.submit('dram', Transfer('x', 'dram-0-0', 'sram-0', 1, 0, 64), 0)
        n.submit('c2c', Transfer('y', 'sram-1', 'sram-0', 2, 0, 64), 0)
        self.assertEqual(n.advance(100), ['c2c']); self.assertEqual(n.now, 7)
        self.assertEqual(n.advance(100), ['dram']); self.assertEqual(n.now, 12)
        self.assertEqual(len(native.messages), 1)

    def test_deadline_is_inclusive_under_uniform_network(self):
        c, base, _ = one_read(); b, t, s = project(c, base, 'U1')
        for limit in (1, 64):
            with self.assertRaises(TimeoutError):
                execute(b, t, network=UniformMemoryNetwork(ClockNetwork(), s), cycle_limit=limit)
        self.assertTrue(execute(b, t, network=UniformMemoryNetwork(ClockNetwork(), s), cycle_limit=65)['complete'])

    def test_tie_does_not_hide_bad_design_selection(self):
        rows = [dict(model=m, layout=p, application_cycles=t)
                for m, values in [('U0', (100, 100, 100)), ('U1', (100, 200, 300)), ('S', (100, 200, 300))]
                for p, t in zip(('near', 'opposite', 'single_controller'), values)]
        result = selection(rows, 10)
        self.assertEqual(result['choices'][0]['reference_regret_max_cycles'], 200)
        self.assertTrue(all(r['selection_disagreement'] for r in result['pairs'] if r['model'] == 'U0'))

    def test_unknown_model_is_not_silently_spatial(self):
        c, b, _ = one_read()
        with self.assertRaises(ValueError): project(c, b, 'typo')
