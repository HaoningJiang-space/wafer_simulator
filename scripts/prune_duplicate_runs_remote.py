"""Remove only byte-identical bulk copies in named obsolete runs on eex005.

Keep original audit/configuration/log evidence, accepted reference 002, current
006 and M1. Each removed path has a retained canonical path and exact hash.
"""
import argparse
import os
from pathlib import Path
import platform
import subprocess

from wafer_sim.io import digest, write_json

ROOT = Path("/home/wangziheng/wafer_simulator")
OBSOLETE = ("llama16-full-001", "llama16-full-003-topology-ref",
            "llama16-full-004-runtime-opt", "llama16-full-005-node-reuse")
CANONICAL = ROOT / "runs/llama16-full-006-csr-frontier"
BULK = ("trace.json", "events.jsonl", "checked_events.npy")


def unused(paths):
    wanted = {str(p) for p in paths}
    directories = {str(p.parent) + "/" for p in paths}
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            links = [process / "cwd", *list((process / "fd").iterdir())]
            for link in links:
                try:
                    target = os.readlink(link)
                    if target in wanted or any(target.startswith(d) for d in directories):
                        raise RuntimeError(f"Candidate has a live process reference: {process.name}, {target}")
                except FileNotFoundError:
                    continue
        except (FileNotFoundError, PermissionError):
            continue


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Cleanup is restricted to eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not args.output.is_absolute() or not (CANONICAL / "COMPLETE.json").is_file():
        raise ValueError("Fresh absolute receipt path and accepted canonical run required")
    args.output.mkdir(parents=True, exist_ok=False)
    entries, kept_hashes = [], {}
    for name in OBSOLETE:
        run = ROOT / "runs" / name
        if not ((run / "COMPLETE.json").is_file() or (run / "EXCLUDED.json").is_file()):
            raise ValueError("Candidate run lacks terminal evidence")
        for placement in ("baseline", "ours_rotated"):
            for filename in BULK:
                source, kept = run / placement / filename, CANONICAL / placement / filename
                if not source.exists():
                    continue
                if source.is_symlink() or kept.is_symlink() or not kept.is_file():
                    raise ValueError("Cleanup requires regular files")
                stat = source.stat()
                if stat.st_size != kept.stat().st_size:
                    raise ValueError("Bulk copy sizes differ; preserve candidate")
                if str(kept) not in kept_hashes:
                    kept_hashes[str(kept)] = digest(kept)
                sha = digest(source)
                if sha != kept_hashes[str(kept)]:
                    raise ValueError("Bulk copy contents differ; preserve candidate")
                entries.append(dict(removed_path=str(source), retained_path=str(kept), sha256=sha,
                                    bytes=stat.st_size, mtime_ns=stat.st_mtime_ns))
    unused([Path(e["removed_path"]) for e in entries])
    manifest = dict(source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                    entries=entries, logical_bytes=sum(e["bytes"] for e in entries), applied=False,
                    scope="Exact duplicate bulk copies only; unique audit/log/configuration evidence retained")
    write_json(args.output / "PLAN.json", manifest)
    before = os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize
    if args.apply:
        for entry in entries:
            source = Path(entry["removed_path"])
            stat = source.stat()
            if (stat.st_size, stat.st_mtime_ns) != (entry["bytes"], entry["mtime_ns"]):
                raise ValueError("Candidate changed after identity check")
            source.unlink()
        for path, sha in kept_hashes.items():
            if digest(path) != sha:
                raise ValueError("Canonical evidence changed")
        after = os.statvfs(ROOT).f_bavail * os.statvfs(ROOT).f_frsize
        manifest.update(applied=True, observed_free_byte_change=after-before, canonical_hashes_rechecked=True)
        write_json(args.output / "PRUNED.json", manifest)
    print(f"files={len(entries)} logical_bytes={manifest['logical_bytes']} applied={args.apply}")


if __name__ == "__main__":
    main()
