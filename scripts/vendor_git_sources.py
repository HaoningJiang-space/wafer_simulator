"""One-time Git/source packaging: replace gitlinks by byte-exact source files.

This edits the source tree and Git index only. It does not build, import or run
any upstream code. Original checkouts are moved to an explicit backup directory.
"""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def git(path, *args, **kwargs):
    return subprocess.check_output(["git", "-C", str(path), *args], **kwargs)


def export(project, entry, backup):
    source = project / entry["path"]
    if git(source, "rev-parse", "HEAD").decode().strip() != entry["commit"]:
        raise ValueError(f"Source pin mismatch: {source}")
    subprocess.run(["git", "-C", str(source), "diff", "--exit-code", "HEAD"], check=True)
    listing = git(source, "ls-tree", "-r", "-z", "HEAD")
    commit = git(source, "cat-file", "commit", "HEAD")
    rows = []
    for row in listing.split(b"\0"):
        if row:
            identity, name = row.split(b"\t", 1)
            mode, kind, oid = identity.decode().split()
            path = name.decode()
            if Path(path).is_absolute() or ".." in Path(path).parts or ".git" in Path(path).parts:
                raise ValueError("Unsafe source path")
            rows.append(dict(path=path, mode=mode, kind=kind, oid=oid))
    snapshot = backup / (source.name + "-snapshot")
    snapshot.mkdir()
    files, gitlinks = [], []
    with subprocess.Popen(["git", "-C", str(source), "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
        for row in rows:
            if row["kind"] == "commit":
                gitlinks.append(row)
                continue
            if row["kind"] != "blob" or row["mode"] not in ("100644", "100755", "120000"):
                raise ValueError("Unsupported upstream tree entry")
            process.stdin.write((row["oid"] + "\n").encode()); process.stdin.flush()
            oid, kind, size = process.stdout.readline().split()
            body = process.stdout.read(int(size))
            if oid.decode() != row["oid"] or kind != b"blob" or process.stdout.read(1) != b"\n":
                raise ValueError("Git object export failed")
            dest = snapshot / row["path"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            if row["mode"] == "120000":
                dest.symlink_to(os.fsdecode(body))
            else:
                dest.write_bytes(body)
                dest.chmod(0o755 if row["mode"] == "100755" else 0o644)
            files.append(dict(**row, bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
        process.stdin.close()
        if process.wait():
            raise ValueError("Git object reader failed")
    manifest = dict(upstream=entry["upstream"], commit=entry["commit"],
        root_tree=commit.splitlines()[0].split()[1].decode(),
        commit_object_base64=base64.b64encode(commit).decode(),
        source_tree_index_base64=base64.b64encode(listing).decode(),
        files=files, unused_nested_gitlinks=gitlinks,
        policy="All tracked blobs retained byte-for-byte. Nested optional repositories were not used and are not expanded.")
    name = f"third_party/manifests/{source.name}.json"
    path = project / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    subprocess.run(["git", "-C", str(project), "rm", "--cached", "--", entry["path"]], check=True)
    shutil.move(str(source), str(backup / source.name))
    shutil.move(str(snapshot), str(source))
    # Include upstream tracked files even when its own .gitignore matches them.
    subprocess.run(["git", "-C", str(project), "add", "-f", "--", entry["path"], name], check=True)
    entry.pop("mirror", None)
    entry["manifest"] = name
    print(f"Vendored {source.name}: {len(files)} files, {sum(f['bytes'] for f in files)} bytes", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    args = parser.parse_args()
    args.backup.mkdir(parents=True, exist_ok=False)
    project = Path(__file__).resolve().parents[1]
    path = project / "configs/upstream_repositories.json"
    config = json.loads(path.read_text())
    for entry in config["repositories"]:
        export(project, entry, args.backup)
    path.write_text(json.dumps(config, indent=2) + "\n")
    subprocess.run(["git", "-C", str(project), "rm", ".gitmodules"], check=True)


if __name__ == "__main__":
    main()
