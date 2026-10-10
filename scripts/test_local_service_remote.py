"""Same-source receipt for the bounded local-service diagnostics."""
from pathlib import Path
import subprocess
import sys
import unittest

from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import digest, write_json

root = require_active_server()
repo = Path(__file__).resolve().parents[1]
output = Path(sys.argv[1])
if not output.is_absolute() or not output.is_relative_to(root/'runs') or output.exists():
    raise ValueError('Fresh absolute server test directory required')
if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']):
    raise ValueError('Clean committed source required')
output.mkdir()
suite = unittest.TestLoader().discover(str(repo/'tests'), pattern='test_local_service.py')
with (output/'tests.log').open('w') as log:
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
write_json(output/'TESTS.json', dict(passed=result.wasSuccessful(), modules=['test_local_service'],
    tests=result.testsRun, tests_log=str(output/'tests.log'), tests_log_sha256=digest(output/'tests.log'),
    source_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
    executable_sha256=digest(Path(sys.executable).resolve()), python=sys.version))
if not result.wasSuccessful():
    raise SystemExit(1)
