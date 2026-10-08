"""Read accepted runs only: objective-specific accuracy and feedback reconvergence."""
import argparse
import csv
from pathlib import Path
import platform
import subprocess

from wafer_sim.analysis.boundary_selection import prediction_objectives, feedback_reconvergence
from wafer_sim.analysis.memory_service_study import analyze
from wafer_sim.io import read_json, write_json, object_digest, digest


def main():
    if platform.node().split('.')[0] != 'eex005':
        raise SystemExit('Run readback on eex005; keep raw events there')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if not args.run.is_absolute() or not args.output.is_absolute():
        raise ValueError('Use absolute paths and a fresh output directory')
    args.output.mkdir(exist_ok=False)
    result = analyze(args.run)  # Hashes and independent audits; no native run/replay.
    archive = Path('docs/results/memory-service-isolation-001/analysis/SUMMARY.json')
    saved = read_json(archive)
    for key in ('rows', 'interactions'):
        if object_digest(saved[key]) != object_digest(result[key]):
            raise ValueError('Readback differs from accepted summary: ' + key)
    objectives = prediction_objectives(result['rows'], result['acceptance']['registration'])
    pairs, joins, operands = [], [], []
    for case in dict.fromkeys(row['case'] for row in result['rows']):
        shape, contract = case.split('__')
        pipeline = read_json(args.run / case / 'pipeline-0/execution.json')
        bounded = read_json(args.run / case / 'bounded-0/execution.json')
        pair, case_joins, case_operands = feedback_reconvergence(pipeline, bounded)
        scope = dict(shape=shape, memory_contract=contract)
        pairs.append(dict(**scope, **pair))
        joins.extend(dict(**scope, **j) for j in case_joins)
        operands.extend(dict(**scope, **r) for r in case_operands)
    for name, rows in (('prediction_objectives', objectives), ('feedback_pairs', pairs),
                       ('reduction_joins', joins), ('operand_reads', operands)):
        with (args.output / (name + '.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    write_json(args.output / 'SUMMARY.json', dict(
        prediction_objectives=objectives, feedback_pairs=pairs, reduction_joins=joins,
        scope='Conditional declared target, existing complete runs only; bounded is not hardware ground truth'))
    write_json(args.output / 'VALIDATION.json', dict(
        passed=True, host=platform.node(),
        analysis_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        run=str(args.run), source_commit=result['acceptance']['source_commit'],
        complete_manifest_sha256=digest(args.run / 'COMPLETE.json'),
        archived_summary_sha256=digest(archive), archived_rows_and_interactions_equal=True,
        checked_artifact_count=result['acceptance']['checked_artifact_count'],
        independently_audited_executions=len(result['acceptance']['checked']),
        new_simulations=0, new_native_replays=0, tests_rerun=False,
        artifacts_sha256={f.name: digest(f) for f in sorted(args.output.iterdir()) if f.is_file()},
    ))
    print('readback:', len(objectives), 'cells;', len(pairs), 'pairs;', len(joins), 'joins')


if __name__ == '__main__':
    main()
