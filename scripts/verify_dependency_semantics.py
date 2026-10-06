"""Compare saved CPU-reference/candidate unit traces and audit frontier counters."""
import argparse
import copy
from pathlib import Path
import platform

from wafer_sim.analysis.dependency_profile import validate
from wafer_sim.io import digest, read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Run native-evidence checks on eex005")
    names = {p.parent.name for p in args.reference.glob("*/trace_report.json")}
    if names != {p.parent.name for p in args.candidate.glob("*/trace_report.json")} or not names:
        raise ValueError("Native regression reports differ or are absent")
    checked = []
    for name in sorted(names):
        left, right = args.reference / name, args.candidate / name
        for artifact in ("trace.json", "trace_report.json"):
            if digest(left / artifact) != digest(right / artifact):
                raise ValueError(f"Semantic mismatch: {name}/{artifact}")
        if read_json(left / "execution.json")["network_metrics"] != read_json(right / "execution.json")["network_metrics"]:
            raise ValueError(f"Network metric mismatch: {name}")
        trace = read_json(right / "trace.json")
        profile = read_json(right / "dependency_profile.json")
        counts = (len(trace), sum(len(op["rev_deps"]) for op in trace),
                  sum(op["num_deps"] == 0 for op in trace))
        if profile["complete"]:
            validate(profile, *counts)
            # Independent negative checks of acceptance, not extra simulations.
            for field in ("complete", "instructions_completed", "csr_storage_bytes"):
                corrupted = copy.deepcopy(profile)
                corrupted[field] = False if field == "complete" else corrupted[field] + 1
                try:
                    validate(corrupted, *counts)
                except ValueError:
                    pass
                else:
                    raise AssertionError(f"Corrupted {field} accepted")
        else:
            try:
                validate(profile, *counts)
            except ValueError:
                pass
            else:
                raise AssertionError("Incomplete dependency profile accepted")
        checked.append(dict(case=name, exact_input_and_report_match=True,
                            complete=profile["complete"], profile_checked=True))
    write_json(args.output, dict(passed=True, cases=checked,
                                scope="Semantic regressions only, not workload performance"))
    print(f"{len(checked)} exact native input/report matches; profile accounting passed")


if __name__ == "__main__":
    main()
