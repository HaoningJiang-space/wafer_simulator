"""Reproduce the target-execution/native-interface semantic test receipt."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest

from wafer_sim.io import digest, write_json


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Run on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean source required")
    if not args.output.is_absolute():
        raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    sys.path.insert(0, str(repo / "tests"))
    os.environ["WAFER_ONLINE_TEST_OUTPUT"] = str(args.output / "native")
    modules = ["test_spatial", "test_collectives", "test_collective_values", "test_timed_execution",
               "test_transformer", "test_collective_timing", "test_tree_collective", "test_spatial_traffic",
               "test_online_booksim", "test_wow_target", "test_model_fidelity", "test_transfer_granularity", "test_packet_pipeline", "test_memory_boundary", "test_boundary_design", "test_group_sharing", "test_wafer_machine"]
    modules.append('test_memory_abstraction')
    suite = unittest.defaultTestLoader.loadTestsFromNames(modules)
    log = args.output / "tests.log"
    with log.open("w") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    write_json(args.output / "SEMANTICS.json", dict(host=platform.node(), python=sys.version,
        source_commit=subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        passed=result.wasSuccessful(), tests=result.testsRun, modules=modules,
        tests_log=str(log), tests_log_sha256=digest(log)))
    print(log.read_text()[-2000:])
    raise SystemExit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
