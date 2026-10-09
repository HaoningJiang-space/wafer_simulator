"""Portable API/readback, event equivalence and independent policy rejection."""
import copy
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from public_cases import inputs
from test_collective_timing import case as collective_case
from wafer_sim.adapters.periphery_case import compile_case, case_from_record
from wafer_sim.adapters.memory_periphery import TransactionPolicy
from wafer_sim.analysis.periphery_input import audit_input
from wafer_sim.analysis.timing import audit
from wafer_sim.execution.timing import execute
from wafer_sim.io import read_json, object_digest

FIXTURE = Path(__file__).resolve().parent/'fixtures/public-periphery'


class PublicPeripheryTests(unittest.TestCase):
    def test_full_event_and_state_equivalence_to_pre_refactor_cases(self):
        baseline = read_json(FIXTURE/'EXPECTED.json')
        self.assertEqual(baseline['baseline_commit'], 'f91824d171917e0e58824b97a1d2a2bff2e4cf51')
        for row in baseline['cases']:
            with self.subTest(name=row['name']):
                if row['name'] == 'collective_rank_local':
                    binding, timing = collective_case(4); result = execute(binding, timing)
                    self.assertEqual(object_digest(result), row['execution_sha256'])
                    self.assertEqual(object_digest(audit(binding, timing, result)), row['audit_sha256'])
                    continue
                machine, work, placement, shared, kind = inputs(row['name'])
                case = compile_case(machine, work, placement, TransactionPolicy(kind),
                                    interface_organization='controller' if shared else 'bank')
                record = case.to_record()
                self.assertEqual(object_digest(record), row['input_sha256'])
                result = execute(case.binding, case.compiled.timing)
                self.assertEqual(object_digest(result), row['execution_sha256'])
                for section, expected in row['event_sections_sha256'].items():
                    self.assertEqual(object_digest(result[section]), expected, section)
                restored = case_from_record(record)
                self.assertEqual(tuple(restored.binding.plans), tuple(case.binding.plans))
                self.assertEqual(execute(restored.binding, restored.compiled.timing), result)
                if row['complete']:
                    self.assertEqual(object_digest(audit_input(record, result)), row['audit_sha256'])
                else:
                    with self.assertRaisesRegex(ValueError, 'Incomplete'): audit_input(record, result)

    def test_saved_events_audit_without_application_lowering_or_native_process(self):
        record = read_json(FIXTURE/'controller_pipeline_read-INPUT.json')
        result = read_json(FIXTURE/'controller_pipeline_read-EXECUTION.json')
        expected = read_json(FIXTURE/'controller_pipeline_read-AUDIT.json')
        with (patch('wafer_sim.adapters.periphery_case.bind_periphery', side_effect=AssertionError('rebind')),
                patch('wafer_sim.adapters.wafer_machine.bind_machine', side_effect=AssertionError('rebind')),
                patch('subprocess.Popen', side_effect=AssertionError('process'))):
            self.assertEqual(audit_input(record, result), expected)
        restored = case_from_record(record)
        self.assertEqual(execute(restored.binding, restored.compiled.timing), result)

    def test_faulty_supplied_plan_and_self_consistent_execution_still_fail(self):
        record = read_json(FIXTURE/'controller_pipeline_read-INPUT.json')
        record['plans']['f0']['output_requirements'] = [['y0', [0]]]
        case = case_from_record(record)
        result = execute(case.binding, case.compiled.timing)
        self.assertLess(result['output_ready']['y0'], result['operations']['f0']['retired'])
        with self.assertRaisesRegex(ValueError, 'publication'): audit_input(record, result)

    def test_modified_physical_services_and_discarded_plan_fields_fail(self):
        record = read_json(FIXTURE/'controller_pipeline_read-INPUT.json')
        bad = copy.deepcopy(record); bad['physical']['timing']['services'][0]['rate_numerator'] += 1
        with self.assertRaisesRegex(ValueError, 'target/timing'): case_from_record(bad)
        bad = copy.deepcopy(record); bad['plans']['f0']['phases'][0]['hidden_work'] = 1
        with self.assertRaisesRegex(ValueError, 'restoration'): case_from_record(bad)
        bad = copy.deepcopy(record); bad['plans']['extra'] = bad['plans']['f0']
        with self.assertRaisesRegex(ValueError, 'operation plan'): case_from_record(bad)
        bad = copy.deepcopy(record); bad['workload']['operations'][0]['collective'] = {'kind': 'allreduce'}
        with self.assertRaisesRegex(ValueError, 'ordinary'): case_from_record(bad)

    def test_public_imports_and_cli_work_with_private_dependencies_blocked(self):
        # Fresh interpreter makes accidental imports visible even when the
        # formal full-suite runner has already loaded historical study modules.
        script = '''
import importlib.abc, sys, platform, subprocess
from unittest.mock import patch
class BlockPrivate(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('wafer_sim.experiments', 'wafer_sim.remote', 'wafer_sim.adapters.online_booksim')):
            raise AssertionError('Private dependency: '+fullname)
sys.meta_path.insert(0, BlockPrivate())
from wafer_sim.adapters.periphery_case import case_from_record
from wafer_sim.analysis.periphery_input import audit_input
from wafer_sim.analysis import memory_periphery_study, periphery_mechanism_study
from wafer_sim.cli import main
from wafer_sim.io import read_json
with patch.object(platform, 'node', return_value='public-machine'), patch.object(subprocess, 'Popen', side_effect=AssertionError('process')):
    main(['audit-periphery', '--input', sys.argv[1], '--execution', sys.argv[2], '--output', sys.argv[3]])
assert read_json(sys.argv[3]) == read_json(sys.argv[4])
print('public audit passed')
'''
        with tempfile.TemporaryDirectory() as tmp:
            completed = subprocess.run([sys.executable, '-c', script,
                str(FIXTURE/'controller_pipeline_read-INPUT.json'),
                str(FIXTURE/'controller_pipeline_read-EXECUTION.json'), str(Path(tmp)/'audit.json'),
                str(FIXTURE/'controller_pipeline_read-AUDIT.json')],
                env={**os.environ, 'WAFER_REMOTE_ROOT': '/unavailable-private-path'}, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn('public audit passed', completed.stdout)
