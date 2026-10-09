"""Private hn072 receipt workflow, separate from portable input/event auditing."""
import argparse
from pathlib import Path

from wafer_sim.analysis.memory_periphery_study import run as read_study
from wafer_sim.experiments.server import require_active_server


def main():
    require_active_server()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--tests', type=Path, required=True)
    args = p.parse_args()
    read_study(args.source, args.output, args.tests, repo=Path(__file__).resolve().parents[3])


if __name__ == '__main__': main()
