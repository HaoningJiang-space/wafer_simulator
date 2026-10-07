"""Export the accepted resource-balance evidence using standard plotting tools."""
import argparse
from pathlib import Path
import platform
import subprocess

from wafer_sim.io import read_json, write_json, digest


def main():
    if platform.node().split(".")[0] != "eex005": raise SystemExit("Run on eex005")
    parser = argparse.ArgumentParser()
    parser.add_argument("analysis", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"]):
        raise ValueError("Clean source required")
    receipt = read_json(args.analysis / "ANALYZED.json")
    if not receipt["passed"]: raise ValueError("Accepted analysis required")
    for name, value in receipt["artifacts_sha256"].items():
        if digest(args.analysis / name) != value: raise ValueError("Changed analysis: " + name)
    if not args.output.is_absolute(): raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rows = [r for r in read_json(args.analysis / "SUMMARY.json")["rows"] if r["group"] == "balance"]
    series = {p: sorted((r for r in rows if r["placement"] == p), key=lambda r: r["memory_bytes_per_cycle"])
              for p in ("baseline", "ours_rotated")}
    x = [r["memory_bytes_per_cycle"] for r in series["baseline"]]
    colors = ["#4878A8", "#E7AD47", "#69A78E"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), constrained_layout=True)
    for p, label, color in (("baseline", "Baseline", "#315A83"), ("ours_rotated", "Rotated", "#B15D36")):
        axes[0, 0].plot(x, [r["application_cycles"] for r in series[p]], marker="o", label=label, color=color)
    axes[0, 0].set_title("Complete block execution"); axes[0, 0].set_ylabel("Cycles"); axes[0, 0].legend()
    gap = [a["application_cycles"]-b["application_cycles"]
           for a, b in zip(series["baseline"], series["ours_rotated"])]
    axes[0, 1].plot(x, gap, marker="o", color="#705A91")
    axes[0, 1].set_title("Placement completion-time gap")
    axes[0, 1].set_ylabel("Baseline minus Rotated (cycles)")
    for ax, (p, label) in zip(axes[1], (("baseline", "Baseline"), ("ours_rotated", "Rotated"))):
        bottom = [0] * len(x)
        for category, color in zip(("compute", "memory", "network"), colors):
            height = [r["critical_" + category] for r in series[p]]
            ax.bar(range(len(x)), height, bottom=bottom, color=color, label=category)
            bottom = [a+b for a, b in zip(bottom, height)]
        ax.set_title(label + ": one observed critical chain")
        ax.set_ylabel("Service cycles"); ax.set_xticks(range(len(x)), x)
        ax.legend(fontsize=8)
    for ax in axes[0]:
        ax.set_xscale("log", base=2); ax.set_xticks(x, x); ax.grid(alpha=.2)
    for ax in axes.flat: ax.set_xlabel("Shared read/write memory bandwidth (B/cycle)")
    fig.suptitle("Fixed TP8 block, row-major, direct-root AllReduce, rank-local output readiness\n"
                 "Analytical target rates; author designs have unmatched physical cost", fontsize=11)
    for suffix in ("svg", "pdf", "png"):
        fig.savefig(args.output / ("resource_balance." + suffix), dpi=180)
    plt.close(fig)
    write_json(args.output / "FIGURES.json", dict(
        source_commit=subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        matplotlib=matplotlib.__version__, analysis_sha256=digest(args.analysis / "ANALYZED.json"),
        artifacts_sha256={p.name: digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__ == "__main__": main()
