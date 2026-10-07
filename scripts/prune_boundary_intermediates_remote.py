"""Archive superseded boundary receipts and prune only enumerated intermediates."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

ROOT = Path('/home/wangziheng/wafer_simulator')
RUNS = {
    'memory-boundary-001': 'Failed before application: local clock initialization; superseded by 004',
    'memory-boundary-002': 'Unaccepted shared-path coverage; superseded by 004',
    'memory-boundary-003': 'Failed actual shared-link gate; superseded by 004',
    'memory-boundary-analysis-001': 'Superseded analysis of unaccepted run 002',
    'memory-boundary-analysis-002': 'Superseded analysis of unaccepted run 002',
    **{f'memory-boundary-tests-{i:03d}': 'Superseded by same-source accepted tests 005' for i in range(1, 5)},
}
BUILDS = ('booksim-fixed', 'booksim-node-reuse', 'booksim-runtime-opt', 'booksim-topology-ref')
KEEP = {'STARTED.json', 'FAILED.json', 'COMPLETE.json', 'MECHANISMS_COMPLETE.json',
        'LAUNCHES.json', 'SEMANTICS.json', 'ANALYZED.json', 'ACCEPTANCE.json',
        'SUMMARY.json', 'INPUT_CONFIG.json', 'INPUT.json', 'MEASURED.json',
        'AUDIT.json', 'SHARED_PATH.json', 'PHASE_MAP.json'}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def unused(roots):
    roots = tuple(str(p) for p in roots)
    excluded = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            links = [proc/'cwd', proc/'exe', *list((proc/'fd').iterdir())]
            for link in links:
                try:
                    target = os.readlink(link)
                except FileNotFoundError:
                    continue
                if any(target == p or target.startswith(p+'/') for p in roots):
                    raise RuntimeError(f'Live reference: {proc.name} {target}')
        except FileNotFoundError:
            continue
        except PermissionError:
            # Nondumpable SSH session daemons have the user's UID, but their
            # child shells/jobs are separate processes and remain checked.
            try:
                command = (proc/'comm').read_text().strip()
            except FileNotFoundError:
                continue
            if command not in ('sshd', '(sd-pam)'):
                raise
            excluded.append(dict(pid=int(proc.name), command=command,
                                 reason='Nondumpable session helper; user child processes checked'))
    return excluded


def main():
    if platform.node().split('.')[0] != 'eex005':
        raise SystemExit('Run only on eex005')
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path)
    p.add_argument('--apply', action='store_true')
    a = p.parse_args()
    if not a.output.is_absolute() or a.output.exists():
        raise ValueError('Fresh absolute output required')
    required = [ROOT/'runs/memory-boundary-004/COMPLETE.json',
                ROOT/'runs/memory-boundary-analysis-003/ANALYZED.json',
                ROOT/'runs/memory-boundary-tests-005/SEMANTICS.json']
    if not all(f.is_file() for f in required):
        raise ValueError('Accepted evidence missing')
    retained = {}
    for name in ('memory-boundary-004', 'memory-boundary-analysis-003', 'memory-boundary-tests-005'):
        for f in (ROOT/'runs'/name).rglob('*'):
            if f.is_file():
                retained[str(f)] = sha(f)
    for name in (*BUILDS, 'booksim', 'booksim-reference', 'booksim-csr-frontier', 'booksim-boundary'):
        for f in (ROOT/'build'/name).rglob('*'):
            if f.is_file() and (f.name in ('booksim', 'endpoint_booksim') or f.suffix in ('.cpp', '.hpp', '.h', '.patch')):
                retained[str(f)] = sha(f)
    retained[str(ROOT/'build/booksim-online/online_booksim')] = sha(ROOT/'build/booksim-online/online_booksim')
    roots = [ROOT/'runs'/n for n in RUNS] + [ROOT/'build'/n for n in BUILDS]
    excluded = unused(roots)
    entries = []
    for name, reason in RUNS.items():
        run = ROOT/'runs'/name
        if not run.is_dir() or run.is_symlink():
            raise ValueError(f'Expected original directory: {run}')
        if not any((run/n).is_file() for n in ('FAILED.json','COMPLETE.json','ANALYZED.json','SEMANTICS.json')):
            raise ValueError(f'No terminal receipt: {run}')
        for f in sorted(run.rglob('*')):
            if f.is_symlink():
                raise ValueError(f'Unexpected symlink: {f}')
            if f.is_file():
                st = f.stat()
                entries.append(dict(path=str(f), sha256=sha(f), bytes=st.st_size,
                    allocated_bytes=st.st_blocks*512 if st.st_nlink == 1 else 0,
                    mtime_ns=st.st_mtime_ns, reason=reason,
                    archive=f.name in KEEP or f.suffix in ('.csv', '.log')))
    for name in BUILDS:
        build = ROOT/'build'/name
        tracked = set(subprocess.check_output(['git','-C',str(build),'ls-files'], text=True).splitlines())
        for f in sorted(build.rglob('*.o')):
            if f.is_symlink() or str(f.relative_to(build)) in tracked:
                raise ValueError('Not an untracked generated object')
            st = f.stat()
            entries.append(dict(path=str(f), sha256=sha(f), bytes=st.st_size,
                allocated_bytes=st.st_blocks*512 if st.st_nlink == 1 else 0,
                mtime_ns=st.st_mtime_ns, reason='Obsolete optimization build object; source and binary retained', archive=False))
    a.output.mkdir()
    record = dict(applied=False, source_commit=subprocess.check_output(['git','rev-parse','HEAD'], text=True).strip(),
                  process_check_exclusions=excluded,
                  entries=entries, retained_sha256=retained,
                  logical_bytes=sum(e['bytes'] for e in entries),
                  allocated_bytes=sum(e['allocated_bytes'] for e in entries))
    write(a.output/'PLAN.json', record)
    if a.apply:
        for e in entries:
            if e['archive']:
                target = a.output/'receipts'/Path(e['path']).relative_to(ROOT)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(e['path'], target)
                if sha(target) != e['sha256']:
                    raise ValueError('Receipt copy mismatch')
        record['process_check_exclusions_before_delete'] = unused(roots)
        for e in entries:
            f = Path(e['path']); st = f.stat()
            if st.st_size != e['bytes'] or st.st_mtime_ns != e['mtime_ns'] or sha(f) != e['sha256']:
                raise ValueError('Candidate changed after inspection')
        for e in entries:
            Path(e['path']).unlink()
        for name in RUNS:
            run = ROOT/'runs'/name
            for d in sorted((d for d in run.rglob('*') if d.is_dir()), key=lambda d: len(d.parts), reverse=True):
                d.rmdir()
            run.rmdir()
        for path, digest in retained.items():
            if sha(Path(path)) != digest:
                raise ValueError('Retained evidence changed')
        record.update(applied=True, retained_hashes_rechecked=True,
            archive_bytes=sum(f.stat().st_size for f in (a.output/'receipts').rglob('*') if f.is_file()))
        write(a.output/'PRUNED.json', record)
    print({k:record[k] for k in ('applied','logical_bytes','allocated_bytes')})


if __name__ == '__main__':
    main()
