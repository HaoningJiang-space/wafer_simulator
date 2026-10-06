"""Reuse the pinned ATLAHS event parser without changing its author sources."""
from pathlib import Path
import pickle
import subprocess
import sys

from wafer_sim.io import digest, write_json

UPSTREAM_COMMIT = "fb51a99f908e550318056ebb3e084f3d2fff55bd"


def extract(upstream, sqlite_directory, output):
    upstream, sqlite_directory, output = map(lambda p: Path(p).resolve(), (upstream, sqlite_directory, output))
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM_COMMIT or subprocess.check_output(
            ["git", "-C", str(upstream), "status", "--porcelain"], text=True).strip():
        raise ValueError("ATLAHS author checkout must be clean at the recorded pin")
    files = sorted(sqlite_directory.glob("*.sqlite"))
    if len(files) != 4:
        raise ValueError("The complete four-host capture requires four SQLite exports")
    output.mkdir(parents=True, exist_ok=False)
    generator = upstream / "goal_gen/ai/nccl_goal_generator"
    sys.path.insert(0, str(generator))
    from generator_modules.nsys_events import get_nsys_events
    from generator_modules.manipulate_events import merge_nsys_events, get_events_parallel_group

    init, nccl, kernels, comm, hosts, intervals = get_nsys_events(str(sqlite_directory))
    # Preserve the original typed dictionaries. This file is generated locally,
    # hashed below and must only be loaded with that hash checked.
    merged = merge_nsys_events(nccl, kernels, comm)
    missing = [(host, gpu, stream, i) for host, gs in merged.items() for gpu, ss in gs.items()
               for stream, es in ss.items() for i, e in enumerate(es)
               if "ts_gpu_start" not in e or "ts_gpu_end" not in e]
    if missing:
        write_json(output / "MISSING_GPU_TIMES.json", dict(count=len(missing), examples=missing[:20]))
        raise ValueError("Author merge did not match every NCCL event to GPU timestamps")
    groups = get_events_parallel_group(merged)
    bundle = dict(groups=groups, init=init, comm=comm, hosts=hosts, intervals=intervals,
                  merged=merged, kernels=kernels)
    with (output / "events.pkl").open("wb") as f:
        pickle.dump(bundle, f, protocol=5)
    for name, value in (("grouped_events", groups), ("comm_info", comm), ("host_mapping", hosts),
                         ("profile_intervals", intervals)):
        write_json(output / f"{name}.json", value)
    counts = dict(hosts=len(groups), gpus=sum(len(gs) for gs in groups.values()),
                  streams=sum(len(ss) for gs in groups.values() for ss in gs.values()),
                  groups=sum(len(es) for gs in groups.values() for ss in gs.values() for es in ss.values()))
    if counts["hosts"] != 4 or counts["gpus"] != 16:
        raise ValueError(f"Source capture cardinality differs: {counts}")
    manifest = dict(passed=True, upstream_commit=revision, counts=counts,
        scope="Author event extraction only; equivalence to the published GOAL has not been established",
        sqlite_sha256={str(p): digest(p) for p in files},
        generator_source_sha256={str(p.relative_to(upstream)): digest(p) for p in generator.rglob("*.py")},
        bundle_sha256=digest(output / "events.pkl"),
        artifacts_sha256={p.name: digest(p) for p in output.iterdir() if p.is_file()})
    write_json(output / "EXTRACTED.json", manifest)
    return manifest
