"""Fixed weak-scaling demand, legal geometry and non-dominating staging."""
from collections import Counter
from pathlib import Path
import unittest

from wafer_sim.io import read_json
from wafer_sim.architecture.wafer_machine import from_config, validate
from wafer_sim.adapters.wafer_machine import compile_machine, bind_machine
from wafer_sim.adapters.memory_machine_workload import place
from wafer_sim.adapters.scaling_layout import place_scaled, capacity_bound
from wafer_sim.workloads.memory_machine import build


class SpatialScalingTests(unittest.TestCase):
    def test_all_registered_sizes_and_layouts_fit_declared_budgets(self):
        root = Path(__file__).resolve().parents[1]
        base = read_json(root/'configs/wafer_machine.json')
        for side in (4, 6, 7):
            c = compile_machine(from_config(dict(base, array=[side, side])))
            validate(c.physical)
            work, meta = build(side*side, 32, 128)
            self.assertEqual(meta['macs'], side*side*1048576)
            self.assertEqual(len(work.operations), 2*side*side)
            for layout in ('local', 'remote_balanced', 'clustered_local'):
                p = place_scaled(meta, side, layout); b, _ = bind_machine(work, c, p)
                bound = capacity_bound(b)
                self.assertTrue(bound['passed'])
                self.assertLessEqual(max(n for k, n in bound['all_live_upper_bytes'].items()
                    if k.startswith('controller-') and k.endswith('/buffer')), 589824)

    def test_remote_is_bijective_and_cluster_has_bounded_distance(self):
        for side in (4, 6, 7):
            _, meta = build(side*side, 32, 128)
            remote = place_scaled(meta, side, 'remote_balanced')
            clustered = place_scaled(meta, side, 'clustered_local')
            load = Counter()
            for worker in range(side*side):
                bank = int(clustered.data[f'w{worker}'].split('-')[1]); load[bank] += 1
                r, c = divmod(worker, side); rr, cc = divmod(bank, side)
                self.assertLessEqual(abs(r-rr)+abs(c-cc), 2)
            self.assertLessEqual(max(load.values()), 4)
            self.assertEqual(len({remote.data[f'w{i}'] for i in range(side*side)}), side*side)
            self.assertEqual(remote.compute, clustered.compute)

    def test_four_square_keeps_accepted_local_remote_mapping(self):
        _, meta = build(16, 32, 128)
        self.assertEqual(place_scaled(meta, 4, 'local'), place(meta, 'near'))
        self.assertEqual(place_scaled(meta, 4, 'remote_balanced'), place(meta, 'opposite'))

    def test_eight_square_not_silently_accepted_on_same_circle(self):
        base = read_json(Path(__file__).resolve().parents[1]/'configs/wafer_machine.json')
        with self.assertRaises(ValueError): compile_machine(from_config(dict(base, array=[8, 8])))
