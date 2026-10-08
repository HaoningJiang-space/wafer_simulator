"""Restore pinned runtime trees from this repository alone, on eex005."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wafer_sim.vendor import restore, verify
from wafer_sim.remote import require_active_server


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], text=True).strip()


def main():
    active_root = require_active_server()
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Inspect existing trees without restoring")
    parser.add_argument("--root", type=Path, default=active_root)
    parser.add_argument('--only', nargs='+', help='Restore selected third_party directory names')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = args.root.resolve()
    if not root.is_relative_to(active_root):
        raise ValueError("Runtime sources stay under the remote project root")
    entries = json.loads((project / "configs/upstream_repositories.json").read_text())["repositories"]
    if args.only and not set(args.only) <= {Path(e['path']).name for e in entries}:
        raise ValueError('Unknown source-lock selection')
    for entry in entries:
        if args.only and Path(entry['path']).name not in args.only:
            continue
        manifest = json.loads((project / entry["manifest"]).read_text())
        if manifest["commit"] != entry["commit"]:
            raise ValueError("Manifest and source lock differ")
        checked = verify(project / entry["path"], manifest)
        dest = root / entry["runtime_path"]
        if not dest.exists():
            if args.check:
                raise ValueError(f"Missing source checkout: {dest}")
            restore(project, entry, dest)
        verify(dest, manifest)
        status = git("-C", dest, "status", "--porcelain", "--untracked-files=all").splitlines()
        caches = [line for line in status if line.startswith("?? ") and
                  "__pycache__/" in line[3:] and line.endswith(".pyc")]
        changed = [line for line in status if line not in caches]
        if git("-C", dest, "rev-parse", "HEAD") != entry["commit"] or changed:
            raise ValueError(f"Existing source is changed or at another revision; preserved: {dest}")
        print(json.dumps(dict(path=str(dest), commit=entry["commit"], **checked,
                              authored_source_clean=True, ignored_runtime_bytecode_files=len(caches),
                              external_fetch_required=False)))


if __name__ == "__main__":
    main()
