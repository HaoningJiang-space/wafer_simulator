"""Extract compact critical windows from authenticated source-order readback."""
import argparse
import hashlib
import json
from pathlib import Path
import socket


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(source, output):
    if not output.is_absolute() or output.exists():
        raise ValueError('Fresh absolute output required')
    checked = json.loads((source / 'CHECKED.json').read_text())
    if not checked['passed']:
        raise ValueError('Failed source readback')
    for name in ('DETAILS.json', 'RESULTS.json'):
        if sha(source / name) != checked['artifacts_sha256'][name]:
            raise ValueError('Changed source readback: ' + name)
    details = json.loads((source / 'DETAILS.json').read_text())
    results = json.loads((source / 'RESULTS.json').read_text())
    keys = [(row['side'], row['layout']) for row in details]
    if len(keys) != len(set(keys)) or set(keys) != {
        (n, p) for n in (4, 6, 7)
        for p in ('local', 'clustered_local', 'remote_balanced')
    }:
        raise ValueError('Missing or duplicated application cell')
    compact = dict(applications=results['applications'], windows=[
        dict(side=row['side'], layout=row['layout'], **window)
        for row in details for window in row['critical_sharing_windows']
        if window['other_flits'] > 0
    ], scope='Post-prediction sink-arrival windows; not grants, credits or queue occupancy')
    output.mkdir()
    artifact = output / 'CRITICAL_WINDOWS.json'
    artifact.write_text(json.dumps(compact, sort_keys=True, indent=2) + '\n')
    receipt = dict(passed=True, host=socket.gethostname(), analysis_source_commit=checked['source_commit'],
        derivation_script_sha256=sha(Path(__file__).resolve()),
        inputs_sha256={name: sha(source / name) for name in ('CHECKED.json', 'DETAILS.json', 'RESULTS.json')},
        artifacts_sha256={artifact.name: sha(artifact)})
    (output / 'DERIVED.json').write_text(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
    print(dict(passed=True, applications=len(keys), shared_windows=len(compact['windows'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    main(args.source, args.output)
