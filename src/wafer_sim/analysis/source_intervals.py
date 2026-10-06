"""Read GPU activity inside source intervals, without assigning target costs."""
from collections import Counter
from pathlib import Path
import sqlite3

from wafer_sim.io import digest, read_json, write_json


def covered_time(intervals, begin, end):
    clipped = sorted((max(begin, a), min(end, b)) for a, b in intervals if a < end and b > begin)
    total, frontier = 0, begin
    for a, b in clipped:
        total += max(0, b - max(frontier, a))
        frontier = max(frontier, b)
    return total


def inspect_interval(database, begin, end):
    if end <= begin:
        raise ValueError("Expected a positive measured interval")
    connection = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    with connection:
        candidates = connection.execute("""SELECT DISTINCT k.globalPid, k.deviceId
            FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id
            WHERE k.start=? AND s.value LIKE 'nccl%'""", (end,)).fetchall()
        if len(candidates) != 1:
            connection.close()
            return dict(identified=False, reason="Next NCCL kernel does not uniquely identify process/device",
                        boundary_candidates=candidates)
        pid, device = candidates[0]
        previous = connection.execute("""SELECT k.start,k.end,k.streamId,s.value
            FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id
            WHERE k.end=? AND k.globalPid=? AND k.deviceId=? AND s.value LIKE 'nccl%'""",
            (begin, pid, device)).fetchall()
        kernels = connection.execute("""SELECT k.start,k.end,k.streamId,s.value
            FROM CUPTI_ACTIVITY_KIND_KERNEL k JOIN StringIds s ON k.demangledName=s.id
            WHERE k.globalPid=? AND k.deviceId=? AND k.start<? AND k.end>?
            ORDER BY k.start,k.end""", (pid, device, end, begin)).fetchall()
    connection.close()
    nccl = [(a, b) for a, b, stream, name in kernels if name.startswith("nccl")]
    other = [(a, b) for a, b, stream, name in kernels if not name.startswith("nccl")]
    active = covered_time([(a, b) for a, b, _, _ in kernels], begin, end)
    return dict(identified=True, source_global_pid=pid, source_device_id=device,
        previous_boundary_nccl_kernels=previous, start_ns=begin, end_ns=end, duration_ns=end-begin,
        overlapping_kernel_count=len(kernels), non_nccl_kernel_count=len(other), nccl_kernel_count=len(nccl),
        kernel_union_ns=active, non_nccl_kernel_union_ns=covered_time(other, begin, end),
        nccl_kernel_union_ns=covered_time(nccl, begin, end), not_covered_by_kernel_ns=end-begin-active,
        stream_kernel_counts=dict(Counter(str(stream) for _, _, stream, _ in kernels)),
        category_limit="Non-NCCL kernel activity is not calibrated pure compute; uncovered time is not classified as waiting",
        representative_kernel_names=list(dict.fromkeys(name for _, _, _, name in kernels))[:8])


def analyze_intervals(regenerated, sqlite_directory, output):
    regenerated, sqlite_directory, output = map(Path, (regenerated, sqlite_directory, output))
    stages = read_json(output / "LOCAL_STAGES.json")
    hosts = read_json(regenerated / "REGENERATION.json")["goal_rank_to_host"]
    intervals, databases = [], {}
    for stage in stages["major_stages"]:
        if stage["category"] != "measured_interval":
            continue
        host = hosts[str(stage["host"])]
        candidates = sorted(sqlite_directory.glob(f"nsys_report_{host}*.sqlite"))
        if len(candidates) != 1:
            raise ValueError(f"Source host does not identify one SQLite file: {host}")
        database = candidates[0]
        databases[str(database.resolve())] = database
        record = inspect_interval(database, stage["interval_start_ns"], stage["interval_end_ns"])
        intervals.append(dict(op_id=stage["op_id"], goal_rank=stage["host"], label=stage["label"],
            source_gpu_id=stage["source_gpu"], source_stream_id=stage["source_stream"],
            database=str(database.resolve()), **record))
    result = dict(intervals=intervals, sqlite_sha256={name: digest(p) for name, p in databases.items()},
        local_stages_sha256=digest(output / "LOCAL_STAGES.json"),
        scope="Same-process/device kernel coverage of major source intervals; no time subtraction or target service calibration")
    write_json(output / "INTERVAL_ACTIVITY.json", result)
    return result
