"""Reuse the pinned ATLAHS event parser without changing its author sources."""
from pathlib import Path
import copy
import os
import pickle
import subprocess
import sys

from wafer_sim.io import digest, read_json, write_json

UPSTREAM_COMMIT = "fb51a99f908e550318056ebb3e084f3d2fff55bd"
HISTORICAL_COMMIT = "e436c1de79619e7bcd9977e2a713f8e4a1f7e8f9"
SOURCE_REVISIONS = {UPSTREAM_COMMIT, HISTORICAL_COMMIT}


def extract(upstream, sqlite_directory, output, revision_expected=UPSTREAM_COMMIT):
    upstream, sqlite_directory, output = map(lambda p: Path(p).resolve(), (upstream, sqlite_directory, output))
    revision = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if revision_expected not in SOURCE_REVISIONS or revision != revision_expected or subprocess.check_output(
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


def regenerate(extracted, upstream, original_goal, output, source_host_order, observe=False):
    """Test a host-order hypothesis through the full author GOAL generator.

    Output is a conversion candidate, never a simulator input or accepted M0
    until it is compared with the unchanged published complete GOAL.
    """
    extracted, upstream, original_goal, output = map(Path, (extracted, upstream, original_goal, output))
    manifest = read_json(extracted / "EXTRACTED.json")
    if digest(extracted / "events.pkl") != manifest["bundle_sha256"]:
        raise ValueError("Locally extracted typed event bundle changed")
    if sorted(source_host_order) != list(range(4)):
        raise ValueError("Host order must retain all four source hosts")
    revision = manifest["upstream_commit"]
    if revision not in SOURCE_REVISIONS or subprocess.check_output(
            ["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip() != revision:
        raise ValueError("Author revision changed")
    for name, sha in manifest["generator_source_sha256"].items():
        if digest(upstream / name) != sha:
            raise ValueError(f"Author generator changed: {name}")
    with (extracted / "events.pkl").open("rb") as f:
        bundle = pickle.load(f)  # Only our hash-checked, locally generated bundle.
    to_goal = {source: goal for goal, source in enumerate(source_host_order)}
    groups = {goal: bundle["groups"][source] for goal, source in enumerate(source_host_order)}
    init = {goal: bundle["init"][source] for goal, source in enumerate(source_host_order)}
    comm = copy.deepcopy(bundle["comm"])
    for info in comm.values():
        for rank in info["rank_To_rankInfo"].values():
            rank["goal_rank"] = to_goal[rank["goal_rank"]]
    generator = upstream / "goal_gen/ai/nccl_goal_generator"
    sys.path.insert(0, str(generator))
    from generator_modules.data_dependency_modules.in_gpu_dependency import get_in_gpu_microevents_dependency
    from generator_modules.data_dependency_modules.inter_node_dependency import get_inter_node_microevents_dependency
    from generator_modules.data_dependency_modules.reduction_copy_time import init_data
    output.mkdir(parents=True, exist_ok=False)
    simple = generator / "npkit_benchmark_results/clariden/npkit_data_summary_Simple.json"
    ll = generator / "npkit_benchmark_results/clariden/npkit_data_summary_LL.json"
    init_data(str(simple), str(ll))
    # The published file has same-host transfer dependencies after its last op.
    # Request the author's complete legacy relation mode; never delete cycles.
    controls = dict(ATLAHS_INTRA_NODE_RECV_REQUIRES_SEND_MODE="all",
                    ATLAHS_ENABLE_INTRA_NODE_RECV_REQUIRES_SEND="0",
                    ATLAHS_DISABLE_INTRA_NODE_RECV_REQUIRES_SEND="0")
    previous = {name: os.environ.get(name) for name in controls}
    os.environ.update(controls)
    candidate = output / "candidate.goal"
    try:
        mapping = get_in_gpu_microevents_dependency(groups, init, comm, str(output / "gpu_events.goal"),
                                                    bundle["intervals"], True)
        from contextlib import nullcontext
        from generator_modules.data_dependency_modules import inter_node_dependency
        from wafer_sim.adapters.atlahs_observer import observe_generator
        observation = observe_generator(inter_node_dependency, groups, output) if observe else nullcontext()
        with observation:
            get_inter_node_microevents_dependency(groups, init, comm, mapping, str(candidate),
                                                  bundle["intervals"], False, True)
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    hashes = dict(original=digest(original_goal), regenerated=digest(candidate))
    result = dict(exact_published_goal_match=hashes["original"] == hashes["regenerated"],
        source_host_order=source_host_order, goal_rank_to_host={to_goal[v]: k for k, v in bundle["hosts"].items()},
        upstream_commit=revision, extracted_manifest_sha256=digest(extracted / "EXTRACTED.json"),
        benchmark_sha256={str(p): digest(p) for p in (simple, ll)}, environment_controls=controls,
        unique_nic=True, zero_red_copy=False, goal_sha256=hashes, source_observer=observe,
        new_simulations_launched=0)
    if not result["exact_published_goal_match"]:
        from itertools import zip_longest
        with original_goal.open() as a, candidate.open() as b:
            for line, (left, right) in enumerate(zip_longest(a, b), 1):
                if left != right:
                    result["first_text_difference"] = dict(line=line, original=left, regenerated=right)
                    break
    write_json(output / "REGENERATION.json", result)
    return result
