"""Compare two COMPLETE real-capture runs; never compare timed prefixes."""
import argparse
from pathlib import Path
import platform
import time

from wafer_sim.io import digest, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wait-seconds", type=int, default=0)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full event evidence stays on eex005")
    deadline = time.monotonic()+args.wait_seconds
    while True:
        for path in (args.reference, args.candidate):
            if (path / "EXCLUDED.json").exists() or (path / "failures.json").exists():
                raise SystemExit(f"Cannot verify incomplete/excluded run: {path}")
        if all((p / "COMPLETE.json").exists() for p in (args.reference, args.candidate)):
            break
        if time.monotonic() >= deadline:
            raise SystemExit("Full replay equivalence pending: both runs must finish")
        time.sleep(min(60, max(0, deadline-time.monotonic())))
    reference, candidate = (read_json(p / "results.json") for p in (args.reference, args.candidate))
    if {r["placement"] for r in reference} != {r["placement"] for r in candidate}:
        raise ValueError("Placement arms differ")
    checked = []
    for left in reference:
        arm = left["placement"]
        right = next(r for r in candidate if r["placement"] == arm)
        for field in ("work", "application_cycles", "critical_local_work_cycles", "critical_message_cycles",
                      "network_metrics", "resources", "tagged_last_flit_arrived_early"):
            if left[field] != right[field]:
                raise ValueError(f"Full replay mismatch: {arm}/{field}")
        hashes = []
        for name in ("trace.json", "events.jsonl"):
            original = digest(args.reference / arm / name)
            optimized = digest(args.candidate / arm / name)
            if original != optimized:
                raise ValueError(f"Full input/event mismatch: {arm}/{name}")
            hashes.append(dict(file=name, sha256=original))
        checked.append(dict(placement=arm, exact_full_event_match=True, hashes=hashes,
                            reference_wall_seconds=left["wall_seconds"],
                            candidate_wall_seconds=right["wall_seconds"],
                            observed_wall_ratio=left["wall_seconds"]/right["wall_seconds"]))
    result = dict(passed=True, reference=str(args.reference), candidate=str(args.candidate),
                  arms=checked, same_full_work_and_events=True,
                  wall_time_caveat="Runs overlap and the reference was briefly debugger-sampled; ratios are observational")
    write_json(args.output, result)
    print(result, flush=True)


if __name__ == "__main__":
    main()
