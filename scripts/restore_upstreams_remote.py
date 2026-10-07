"""Restore only the pinned source trees used by this project, on eex005."""
import argparse
import json
from pathlib import Path
import platform
import subprocess


def git(*args):
    return subprocess.check_output(["git", *map(str, args)], text=True).strip()


def main():
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Runtime source restoration belongs on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Inspect existing trees without cloning")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    root = Path("/home/wangziheng/wafer_simulator")
    entries = json.loads((project / "configs/upstream_repositories.json").read_text())["repositories"]
    for entry in entries:
        mode, kind, commit_and_path = git("-C", project, "ls-tree", "HEAD", entry["path"]).split(maxsplit=2)
        commit = commit_and_path.split()[0]
        if mode != "160000" or kind != "commit" or commit != entry["commit"]:
            raise ValueError(f"Gitlink and source lock differ: {entry['path']}")
        url = git("-C", project, "config", "-f", ".gitmodules", f"submodule.{entry['path']}.url")
        if url != entry["mirror"]:
            raise ValueError("Source mirror and .gitmodules differ")
        dest = root / entry["runtime_path"]
        if not dest.exists():
            if args.check:
                raise ValueError(f"Missing source checkout: {dest}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "--no-checkout", entry["mirror"], str(dest)], check=True)
            subprocess.run(["git", "-C", str(dest), "checkout", "--detach", entry["commit"]], check=True)
        status = git("-C", dest, "status", "--porcelain", "--untracked-files=all").splitlines()
        caches = [line for line in status if line.startswith("?? ") and
                  "__pycache__/" in line[3:] and line.endswith(".pyc")]
        changed = [line for line in status if line not in caches]
        if git("-C", dest, "rev-parse", "HEAD") != entry["commit"] or changed:
            raise ValueError(f"Existing source is changed or at another revision; preserved: {dest}")
        print(json.dumps(dict(path=str(dest), commit=entry["commit"], mirror=entry["mirror"],
                              authored_source_clean=True, ignored_runtime_bytecode_files=len(caches))))


if __name__ == "__main__":
    main()
