"""Clean-source G2.1 semantic tests on hn072, including guard faults."""
from pathlib import Path
import subprocess
import sys
import unittest
from wafer_sim.experiments.server import require_active_server
from wafer_sim.io import digest,write_json

root=require_active_server();repo=Path(__file__).resolve().parents[1];out=Path(sys.argv[1])
if not out.is_absolute() or not out.is_relative_to(root/'runs') or out.exists():raise ValueError('Fresh server output required')
if subprocess.check_output(['git','-C',str(repo),'status','--porcelain']):raise ValueError('Clean main required')
out.mkdir();suite=unittest.TestLoader().discover(str(repo/'tests'),pattern='test_causal_macro_single.py')
with (out/'tests.log').open('w') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
write_json(out/'TESTS.json',dict(passed=result.wasSuccessful(),tests=result.testsRun,
    source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
    tests_log_sha256=digest(out/'tests.log'),python=sys.version,executable_sha256=digest(Path(sys.executable).resolve())))
if not result.wasSuccessful():raise SystemExit(1)
