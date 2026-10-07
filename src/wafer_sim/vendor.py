"""Verify vendored bytes and restore an exact, offline author Git worktree.

Source files live in the main repository. The manifest retains the original
commit object and tree entries, so legacy adapters/build worktrees can keep
using author commit IDs without fetching an external repository.
"""
import base64
import hashlib
import os
from pathlib import Path
import subprocess

from wafer_sim.io import read_json


def source_bytes(directory, entry):
    path = Path(directory) / entry["path"]
    data = os.fsencode(os.readlink(path)) if entry["mode"] == "120000" else path.read_bytes()
    oid = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"] or oid != entry["oid"]:
        raise ValueError(f"Vendored source identity differs: {path}")
    return data


def verify(directory, manifest):
    for entry in manifest["files"]:
        source_bytes(directory, entry)
    return dict(files=len(manifest["files"]), bytes=sum(e["bytes"] for e in manifest["files"]))


def restore(project, entry, destination):
    """Create a new detached checkout only; never overwrite an existing one."""
    project, destination = Path(project), Path(destination)
    manifest = read_json(project / entry["manifest"])
    if manifest["commit"] != entry["commit"]:
        raise ValueError("Source lock and manifest differ")
    source = project / entry["path"]
    verify(source, manifest)
    destination.mkdir(parents=True, exist_ok=False)
    def git(*args, data=None):
        return subprocess.check_output(["git", "-C", str(destination), *args], input=data).strip()
    git("init", "--quiet")
    for file in manifest["files"]:
        actual = git("hash-object", "-w", "--stdin", data=source_bytes(source, file)).decode()
        if actual != file["oid"]:
            raise ValueError("Restored blob identity differs")
    # Preserve unused nested gitlinks as tree metadata; no nested source is
    # fetched. None is consumed by this project's source/build adapters.
    git("update-index", "-z", "--index-info", data=base64.b64decode(manifest["source_tree_index_base64"]))
    if git("write-tree").decode() != manifest["root_tree"]:
        raise ValueError("Restored author tree differs")
    commit = git("hash-object", "-t", "commit", "-w", "--stdin",
                 data=base64.b64decode(manifest["commit_object_base64"])).decode()
    if commit != entry["commit"]:
        raise ValueError("Restored author commit differs")
    # Author history is not needed to build this exact snapshot. Mark the
    # retained commit as a shallow boundary instead of inventing parent objects.
    (destination / ".git/shallow").write_text(commit + "\n")
    git("update-ref", "--no-deref", "HEAD", commit)
    git("checkout-index", "--all")
    verify(destination, manifest)
    return manifest
