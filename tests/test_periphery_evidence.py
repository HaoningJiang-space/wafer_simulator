"""Reject internally hashed but semantically wrong saved summary rows."""
import copy
from pathlib import Path
import tempfile
import unittest

from test_memory_periphery import fixture
from wafer_sim.analysis.memory_periphery import audit_periphery
from wafer_sim.analysis.periphery_evidence import event_fields, checked_row, validate_rows
from wafer_sim.execution.timing import execute
from wafer_sim.io import write_json, read_json, digest


def evidence():
    c, w, p, policy, b, tx = fixture(64)
    result = execute(b, c.timing); checked = audit_periphery(w, p, c, b, tx, policy, result)
    identity = dict(condition='shared_pipeline', layout='clustered_local', component=None,
                    physical={}, workload={}, placement={})
    measured = event_fields(identity, result, checked); measured['python_cpu_seconds'] = 1.0
    row = dict(measured, directory='clustered_local-shared_pipeline-rep-0', repetition=0, process_wall_seconds=1.0)
    return identity, result, checked, measured, row, dict(wall_seconds=1.0)


class PeripheryEvidenceTests(unittest.TestCase):
    def test_self_consistent_manifest_cannot_validate_a_wrong_summary_makespan(self):
        identity, result, checked, measured, row, process = evidence()
        measured['application_cycles'] -= 1; row['application_cycles'] -= 1
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, value in (('execution.json', result), ('MEASURED.json', measured), ('SUMMARY.json', [row])):
                write_json(root/name, value)
            write_json(root/'COMPLETE.json', {'artifacts_sha256': {p.name: digest(p) for p in root.iterdir()}})
            self.assertTrue(all(digest(root/n) == sha for n, sha in read_json(root/'COMPLETE.json')['artifacts_sha256'].items()))
            with self.assertRaisesRegex(ValueError, 'audited execution: application_cycles'):
                checked_row(row, measured, process, identity, result, checked)

    def test_native_counts_and_measurement_cost_are_independently_cross_checked(self):
        identity, result, checked, measured, row, process = evidence()
        checked_row(row, measured, process, identity, result, checked)
        for field in ('native_messages', 'native_flits'):
            bad_m = dict(measured); bad_r = dict(row); bad_m[field] += 1; bad_r[field] += 1
            with self.assertRaisesRegex(ValueError, 'audited execution'):
                checked_row(bad_r, bad_m, process, identity, result, checked)
        with self.assertRaisesRegex(ValueError, 'MEASURED'):
            checked_row(row, dict(measured, python_cpu_seconds=2.0), process, identity, result, checked)

    def test_duplicate_repetition_directory_and_missing_cell_are_rejected(self):
        reg = dict(conditions=['whole'], layouts=['A'], component_cases=['read'], repetitions=3)
        rows = [dict(condition='whole', layout='A', component=None, repetition=i, directory=f'A-whole-rep-{i}') for i in range(3)]
        rows += [dict(condition='whole', layout=None, component='read', repetition=0, directory='component-read-whole')]
        validate_rows(rows, reg)
        bad = copy.deepcopy(rows); bad[1] = dict(bad[0])
        with self.assertRaisesRegex(ValueError, 'Duplicate'): validate_rows(bad, reg)
        bad = copy.deepcopy(rows); bad[1]['directory'] = bad[0]['directory']
        with self.assertRaisesRegex(ValueError, 'directory'): validate_rows(bad, reg)
        with self.assertRaisesRegex(ValueError, 'Missing'): validate_rows(rows[:-1], reg)
