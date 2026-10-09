"""Private receipt entry points keep the old host/root authorization boundaries."""
from pathlib import Path
import unittest
from unittest.mock import patch

from wafer_sim.experiments.server import require_active_server, runtime_root
from wafer_sim.experiments.revalidate_periphery import main
from wafer_sim import remote


class ExperimentServerTests(unittest.TestCase):
    def test_public_host_and_retired_host_cannot_start_private_receipts(self):
        for host in ('public-machine', 'eex005'):
            with patch('platform.node', return_value=host), patch('wafer_sim.experiments.revalidate_periphery.read_study') as read:
                with self.assertRaises(RuntimeError): main()
                read.assert_not_called()

    def test_registered_root_limits_and_legacy_imports_are_preserved(self):
        self.assertIs(remote.require_active_server, require_active_server)
        self.assertIs(remote.runtime_root, runtime_root)
        with patch('platform.node', return_value='ee4e072'), patch.dict('os.environ', {'WAFER_REMOTE_ROOT': '/tmp/not-project'}):
            with self.assertRaises(ValueError): require_active_server()
        with patch('platform.node', return_value='ee4e072'), patch.dict('os.environ', {'WAFER_REMOTE_ROOT': '/Projects/haoning/wafer_simulator/runs'}):
            self.assertEqual(require_active_server(), Path('/Projects/haoning/wafer_simulator/runs'))
