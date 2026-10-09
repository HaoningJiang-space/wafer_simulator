"""Portable pure-Python semantic regressions; no native builds/server/Git gates."""
from pathlib import Path
import sys
import unittest

MODULES = ('test_spatial', 'test_collectives', 'test_collective_values',
           'test_collective_timing', 'test_tree_collective', 'test_wafer_machine',
           'test_memory_abstraction', 'test_memory_periphery', 'test_periphery_evidence',
           'test_periphery_attribution', 'test_public_periphery')


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tests'))
    suite = unittest.defaultTestLoader.loadTestsFromNames(MODULES)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__': main()
