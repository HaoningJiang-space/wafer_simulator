"""Check the entire real input before any placement experiment."""
import argparse
import platform
from wafer_sim.workloads.goal import ingest

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("preliminary_audit")
    parser.add_argument("output")
    args = parser.parse_args()
    if platform.node().split(".")[0] != "eex005":
        raise SystemExit("Full dataset processing must run on eex005")
    result = ingest(args.input, args.preliminary_audit, args.output)
    raise SystemExit(0 if result["dependency_gate_passed"] else 2)
