"""Pair only identical work, mapping policy, and random seed."""
from collections import defaultdict
from pathlib import Path
import statistics

from wafer_sim.io import write_json


def compare(rows, output):
    pairs = defaultdict(dict)
    for row in rows:
        pairs[(row["workload"], row["mapping"], row["seed"])][row["placement"]] = row
    comparisons = []
    for (workload, mapping, seed), arms in pairs.items():
        baseline = arms["baseline"]
        for placement, alternative in arms.items():
            if placement == "baseline":
                continue
            for key in ("workload_sha256", "ranks", "instructions", "messages", "payload_bytes", "flits", "compute_cycles"):
                if baseline[key] != alternative[key]:
                    raise ValueError(f"Unmatched pair: {key}")
            comparisons.append(dict(workload=workload, mapping=mapping, seed=seed, placement=placement,
                                    application_speedup=baseline["application_cycles"]/alternative["application_cycles"],
                                    message_latency_ratio=baseline["mean_message_cycles"]/alternative["mean_message_cycles"],
                                    saved_application_cycles=baseline["application_cycles"]-alternative["application_cycles"],
                                    saved_exposed_network_cycles=baseline["exposed_network_cycles"]-alternative["exposed_network_cycles"]))
    write_json(Path(output) / "comparisons.json", comparisons)
    lines = ["# Fixed-state WoW placement comparison", "",
             "Generated synchronous data-parallel training DAGs; not the original Llama trace.",
             "All reported arms completed all instructions and all payload flits. Compute clocks and network settings are fixed.",
             "Equal compute resources and work; total interconnect cost is reported separately, not matched.", "",
             "| Workload | Mapping | Placement | Mean application speedup | Mean message latency ratio |", 
             "|---|---|---|---:|---:|"]
    grouped = defaultdict(list)
    for item in comparisons:
        grouped[(item["workload"], item["mapping"], item["placement"])].append(item)
    for (workload, mapping, placement), values in grouped.items():
        lines.append(f"| {workload} | {mapping} | {placement} | "
                     f"{statistics.mean(x['application_speedup'] for x in values):.5f} | "
                     f"{statistics.mean(x['message_latency_ratio'] for x in values):.5f} |")
    lines += ["", "Speedup is baseline/alternative. Per-seed values, absolute cycles, work counters,",
              "and observed critical-chain decomposition are in summary.csv and individual audit.json files.",
              "The zero-network bound preserves compute durations and dependencies; the difference",
              "from measured application time is exposed communication cost, not sum of all message latencies."]
    (Path(output) / "REPORT.md").write_text("\n".join(lines) + "\n")
