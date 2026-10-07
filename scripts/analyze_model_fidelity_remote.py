"""Audit existing accepted events and compare two network abstractions, without simulation."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess
from wafer_sim.analysis.model_fidelity import analyze_saved
from wafer_sim.io import write_json, digest


def main():
    if platform.node().split('.')[0] != 'eex005': raise SystemExit('Run on eex005')
    parser = argparse.ArgumentParser()
    for name in ('direct', 'tree', 'output'): parser.add_argument(name, type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(['git', '-C', str(repo), 'status', '--porcelain']): raise ValueError('Clean source required')
    if not args.output.is_absolute(): raise ValueError('Fresh absolute output required')
    args.output.mkdir(exist_ok=False)
    summary, details = analyze_saved(args.direct, args.tree)
    write_json(args.output/'SUMMARY.json', summary)
    write_json(args.output/'DETAILS.json', details)
    for name, rows in [('applications', summary['rows']), ('placement_gaps', summary['pairs'])]:
        with (args.output/f'{name}.csv').open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    write_json(args.output/'ANALYZED.json', dict(passed=True,
        source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir()) if p.is_file()},
        source_runs=summary['source_runs'], new_simulations=0))
    print({k:v for k,v in summary.items() if k not in ('rows','pairs')})


if __name__ == '__main__': main()
