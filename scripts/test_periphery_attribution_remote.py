"""Remote receipt for the new observational reader; no model tests changed."""
import argparse
from pathlib import Path
import subprocess
import sys
import unittest

from wafer_sim.io import digest, write_json
from wafer_sim.remote import require_active_server


def main():
    require_active_server()
    p = argparse.ArgumentParser(); p.add_argument('output', type=Path); args = p.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if not args.output.is_absolute() or args.output.exists(): raise ValueError('Fresh absolute output required')
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']): raise ValueError('Clean source required')
    args.output.mkdir(); sys.path.insert(0, str(repo/'tests'))
    suite = unittest.defaultTestLoader.loadTestsFromName('test_periphery_attribution')
    log = args.output/'tests.log'
    with log.open('w') as stream: result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    write_json(args.output/'SEMANTICS.json', dict(passed=result.wasSuccessful(), tests=result.testsRun,
        source_commit=subprocess.check_output(['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip(),
        modules=['test_periphery_attribution'], tests_log=str(log), tests_log_sha256=digest(log)))
    print(log.read_text()); raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__': main()
