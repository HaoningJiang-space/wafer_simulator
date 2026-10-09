"""Bounded provenance bridge for the unchanged registered v1 D1 hypothesis."""
import hashlib
import subprocess

from wafer_sim.io import digest

# Reviewed validators/public-interface extraction and this study's orchestration.
# Candidate network algorithms, timing/storage, workloads and controls are never
# exempt. Actual registered v1 input identities must also match accepted D0/S.
FROZEN_V1_COMPATIBLE = frozenset({
    'src/wafer_sim/architecture/wafer_machine.py',
    'src/wafer_sim/architecture/memory_periphery.py',
    'src/wafer_sim/adapters/wafer_machine.py',
    'src/wafer_sim/experiments/spatial_scaling.py',
})
COMPONENT_SOURCE_COMPATIBLE = FROZEN_V1_COMPATIBLE | {
    'src/wafer_sim/adapters/spatial.py', 'src/wafer_sim/cli.py', 'src/wafer_sim/remote.py',
    'src/wafer_sim/experiments/shared_spatial_service.py',
    'src/wafer_sim/analysis/shared_spatial_study.py',
}


def archived_hash(repo, commit, name):
    data = subprocess.check_output(['git', '-C', str(repo), 'show', commit+':'+name])
    return hashlib.sha256(data).hexdigest()


def verify_frozen_v1(repo, commit, paths):
    changed = subprocess.check_output(['git', '-C', str(repo), 'diff', commit,
        '--name-only', '--', *paths], text=True).splitlines()
    if set(changed) - FROZEN_V1_COMPATIBLE:
        raise ValueError('Unreviewed frozen v1 source change: '+str(sorted(set(changed)-FROZEN_V1_COMPATIBLE)))
    result = {}
    for name in changed:
        exists = subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', commit+':'+name],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
        if not exists and name != 'src/wafer_sim/architecture/memory_periphery.py':
            raise ValueError('Unexpected added frozen source')
        result[name] = dict(archived_sha256=archived_hash(repo, commit, name) if exists else None,
                            current_sha256=digest(repo/name))
    return result


def verify_saved_sources(repo, start):
    changed = {}
    for name, sha in start['source_hashes'].items():
        current = digest(repo/name)
        if current == sha: continue
        if name not in COMPONENT_SOURCE_COMPATIBLE:
            raise ValueError('Changed unreviewed D1 source: '+name)
        if archived_hash(repo, start['source_commit'], name) != sha:
            raise ValueError('Archived D1 source differs from original receipt')
        changed[name] = dict(archived_sha256=sha, current_sha256=current)
    return changed


def backend_identity(model, spec, result):
    expected = {'D0': 'independent_spatial_service', 'D1': 'shared_spatial_service', 'S': 'booksim'}
    if model not in expected or spec['model'] != model or result.get('network_backend') != expected[model]:
        raise ValueError('Explicit model/backend identity mismatch')
    return dict(machine_organization='v1-bank-endpoints', transaction_policy='whole',
                selected_model=model, network_backend=expected[model])
