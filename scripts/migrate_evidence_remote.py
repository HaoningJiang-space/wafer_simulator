"""Inventory, verify and retire exact project copies across the two servers.

Transfer uses tar separately. This tool never deletes an unverified unique
artifact; apply requires a verified copy/archive receipt and a fresh full
source-content verification. Source checkout and Git repository are preserved.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import tarfile
import time

OLD = Path('/home/wangziheng/wafer_simulator')
NEW = Path('/Projects/haoning/wafer_simulator/archive/eex005')
PARTS = ('runs', 'downloads', 'build', 'profiles', 'logs', 'upstream', 'deps', '.venv')


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def save(path, value):
    with path.open('x') as stream: json.dump(value, stream, indent=2, sort_keys=True)


def process_check(root, strict=True):
    wanted = tuple(str(root/p)+'/' for p in PARTS)
    blocked, protected = [], []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid(): continue
        try:
            if proc.stat().st_uid != os.getuid(): continue
            comm = (proc/'comm').read_text().strip()
            links = [proc/'cwd', proc/'exe', *list((proc/'fd').iterdir())]
            names = []
            for link in links:
                try: names.append(os.readlink(link))
                except FileNotFoundError: pass
            for line in (proc/'maps').read_text().splitlines():
                fields = line.split(None, 5)
                if len(fields) == 6: names.append(fields[-1])
            if any(n.rstrip('/')+'/' == p or n.startswith(p) for n in names for p in wanted):
                blocked.append(dict(pid=int(proc.name), process=comm))
        except FileNotFoundError: continue
        except PermissionError:
            try: comm = (proc/'comm').read_text().strip()
            except OSError: comm = 'uninspectable'
            if comm not in {'sshd', '(sd-pam)', 'systemd'}:
                raise RuntimeError('Cannot inspect user process '+proc.name+' '+comm)
            protected.append(dict(pid=int(proc.name), process=comm))
    if blocked and strict: raise RuntimeError('Live project references: '+json.dumps(blocked))
    return dict(no_accessible_live_references=not blocked, live_references=blocked, protected_processes=protected)


def inventory(root):
    entries = []
    for part in PARTS:
        directory = root/part
        if directory.is_symlink() or not directory.is_dir(): raise ValueError('Expected real directory '+part)
        for parent, dirs, files in os.walk(directory, followlinks=False):
            for name in sorted(dirs+files):
                p = Path(parent)/name; s = p.lstat()
                row = dict(path=str(p.relative_to(root)), mode=stat.S_IMODE(s.st_mode), mtime_ns=s.st_mtime_ns)
                if stat.S_ISLNK(s.st_mode): row.update(kind='symlink', target=os.readlink(p))
                elif stat.S_ISDIR(s.st_mode): continue
                elif stat.S_ISREG(s.st_mode):
                    row.update(kind='file', size=s.st_size, sha256=digest(p))
                    after = p.stat()
                    if (s.st_size, s.st_mtime_ns, s.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                        raise ValueError('Changed while hashing '+str(p))
                else: raise ValueError('Non-file entry '+str(p))
                entries.append(row)
    return dict(parts=list(PARTS), entries=sorted(entries, key=lambda e:e['path']),
        file_bytes=sum(e.get('size', 0) for e in entries), source=str(OLD), destination=str(NEW))


def verify(root, manifest):
    if manifest['parts'] != list(PARTS): raise ValueError('Changed cleanup scope')
    actual = inventory(root)
    # tar may preserve a different timestamp resolution; content/mode/path must match.
    norm = lambda rows: [{k:v for k,v in r.items() if k != 'mtime_ns'} for r in rows]
    if norm(actual['entries']) != norm(manifest['entries']): raise ValueError('Archive content, file set or mode differs')
    return dict(passed=True, files=len(actual['entries']), file_bytes=actual['file_bytes'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('inventory', 'verify', 'verify-archive', 'retire'))
    p.add_argument('--manifest', required=True, type=Path)
    p.add_argument('--receipt', type=Path)
    p.add_argument('--destination-receipt', type=Path)
    p.add_argument('--archive', type=Path)
    args = p.parse_args(); host = platform.node().split('.')[0]
    if args.action == 'inventory':
        if host != 'eex005': raise ValueError('Inventory the retired host only')
        # Readers may remain while taking a read-only, content-stable inventory.
        # Retirement still strictly rejects every live reference.
        live = process_check(OLD, strict=False)
        m = inventory(OLD); m.update(process_check=live, created_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        save(args.manifest, m)
        print(dict(files=len(m['entries']), bytes=m['file_bytes'], manifest_sha256=digest(args.manifest)), flush=True)
    elif args.action == 'verify':
        if host != 'ee4e072': raise ValueError('Verify destination only')
        m = json.loads(args.manifest.read_text()); checked = verify(NEW, m)
        checked.update(manifest_sha256=digest(args.manifest), destination=str(NEW), host=host,
                       verified_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        save(args.receipt, checked); print(checked, flush=True)
    elif args.action == 'verify-archive':
        if host != 'eex005': raise ValueError('Cold archive stays on the original evidence host')
        manifest = json.loads(args.manifest.read_text())
        expected = {r['path']: r for r in manifest['entries']}; seen = {}; restored = []
        restore_dir = args.receipt.parent/'restore-check'; restore_dir.mkdir(exist_ok=False)
        with tarfile.open(args.archive, 'r|gz') as tar:
            for member in tar:
                if member.isdir(): continue
                name = member.name.removeprefix('./')
                if name not in expected or name in seen: raise ValueError('Unexpected archive member '+name)
                want = expected[name]
                if member.mode != want['mode']: raise ValueError('Changed archived mode '+name)
                if member.issym():
                    if want['kind'] != 'symlink' or member.linkname != want['target']: raise ValueError('Changed symlink '+name)
                    seen[name] = dict(kind='symlink')
                elif member.islnk():
                    target = member.linkname.removeprefix('./')
                    if target not in seen or seen[target].get('sha256') != want.get('sha256'):
                        raise ValueError('Unverified archive hardlink '+name)
                    seen[name] = seen[target]
                elif member.isfile():
                    h = hashlib.sha256(); stream = tar.extractfile(member); count = 0
                    # Materialize representative binary/array/JSON files as well
                    # as independently decoding every archived file.
                    suffix = Path(name).suffix
                    take = (name.endswith('booksim-online/online_booksim') or
                            (suffix in {'.npy', '.json'} and suffix not in {r['suffix'] for r in restored}))
                    dest = restore_dir/str(len(restored)) if take else None
                    out = dest.open('wb') if take else None
                    try:
                        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
                            h.update(chunk); count += len(chunk)
                            if out: out.write(chunk)
                    finally:
                        if out: out.close()
                    if want['kind'] != 'file' or count != want['size'] or h.hexdigest() != want['sha256']:
                        raise ValueError('Corrupt archived content '+name)
                    seen[name] = dict(kind='file', sha256=h.hexdigest())
                    if take:
                        if digest(dest) != want['sha256']: raise ValueError('Restore readback differs')
                        restored.append(dict(path=name, restored_path=str(dest), suffix=suffix, sha256=want['sha256']))
                else: raise ValueError('Unsupported archive member '+name)
        if set(seen) != set(expected): raise ValueError('Incomplete archive')
        checked = dict(passed=True, host=host, destination=str(args.archive.resolve()),
            archive_sha256=digest(args.archive), archive_bytes=args.archive.stat().st_size,
            manifest_sha256=digest(args.manifest), files=len(seen), file_bytes=manifest['file_bytes'],
            restored_samples=restored, format='pax tar + gzip; all member bytes independently decoded')
        save(args.receipt, checked); print({k:v for k,v in checked.items() if k != 'restored_samples'}, flush=True)
    else:
        if host != 'eex005': raise ValueError('Retire source copies only')
        m = json.loads(args.manifest.read_text()); destination = json.loads(args.destination_receipt.read_text())
        archive = Path(destination['destination'])
        verified_archive = (destination['host']=='eex005' and archive.parent == args.manifest.parent
            and archive.is_file() and digest(archive) == destination.get('archive_sha256'))
        verified_new = destination['destination']==str(NEW) and destination['host']=='ee4e072'
        if (not destination['passed'] or destination['manifest_sha256'] != digest(args.manifest)
                or not (verified_archive or verified_new)):
            raise ValueError('Missing verified destination')
        checked = verify(OLD, m); live = process_check(OLD)
        before = shutil.disk_usage(OLD)
        # A verified full copy remains at the receipt's destination.
        for part in PARTS: shutil.rmtree(OLD/part)
        os.sync()
        after = shutil.disk_usage(OLD)
        save(args.receipt, dict(retired=True, source=str(OLD), destination=destination,
            source_rechecked=checked, process_check=live, removed_directories=list(PARTS),
            free_bytes_before=before.free, free_bytes_after=after.free,
            observed_free_byte_change=after.free-before.free,
            preserved=['source', 'source.git', 'migration receipts'],
            scope='Verified duplicate relocation; accepted evidence retained at destination'))
        print(dict(retired=True, observed_free_byte_change=after.free-before.free), flush=True)


if __name__ == '__main__': main()
