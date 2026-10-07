"""Standard reproducible plots of accepted algorithm/topology projection."""
import argparse
from collections import defaultdict
from pathlib import Path
import platform
import subprocess

from wafer_sim.io import read_json, write_json, digest


def main():
    if platform.node().split(".")[0] != "eex005": raise SystemExit("Run on eex005")
    parser=argparse.ArgumentParser()
    parser.add_argument("analysis",type=Path);parser.add_argument("output",type=Path)
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    if subprocess.check_output(["git","-C",str(repo),"status","--porcelain"]): raise ValueError("Clean source required")
    receipt=read_json(args.analysis/"ANALYZED.json")
    if not receipt["passed"]:raise ValueError("Accepted analysis required")
    for name,value in receipt["artifacts_sha256"].items():
        if digest(args.analysis/name)!=value:raise ValueError("Changed analysis: "+name)
    if not args.output.is_absolute():raise ValueError("Fresh absolute output required")
    args.output.mkdir(exist_ok=False)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.colors import Normalize
    summary=read_json(args.analysis/"SUMMARY.json")
    rows={(r["algorithm"],r["placement"],r["memory_bytes_per_cycle"]):r for r in summary["rows"]}
    bws=[32,256,1024];names={"baseline":"Baseline","ours_rotated":"Rotated"}
    colors={"baseline":"#32608D","ours_rotated":"#B6633D"}
    fig,axes=plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
    for p in names:
        for a,style in (("direct","-"),("tree","--")):
            axes[0,0].plot(bws,[rows[a,p,b]["application_cycles"] for b in bws],style,marker="o",
                          color=colors[p],label=f"{names[p]} / {a}")
    axes[0,0].set_title("Complete block time");axes[0,0].set_ylabel("Cycles");axes[0,0].legend(fontsize=8)
    for a,col in (("direct","#408877"),("tree","#916196")):
        axes[0,1].plot(bws,[rows[a,"baseline",b]["application_cycles"]-rows[a,"ours_rotated",b]["application_cycles"] for b in bws],
                       marker="o",label=a,color=col)
    axes[0,1].axhline(0,color="gray",linewidth=.8)
    axes[0,1].set_title("Placement gap: positive favors Rotated")
    axes[0,1].set_ylabel("Baseline minus Rotated (cycles)");axes[0,1].legend()
    for ax in axes[0]:ax.set_xscale("log",base=2);ax.set_xticks(bws,bws);ax.set_xlabel("Memory B/cycle");ax.grid(alpha=.2)
    selected=[(a,p,1024) for a in ("direct","tree") for p in names]
    bottom=[0]*4
    for category,col in (("compute","#4878A8"),("memory","#E7AD47"),("network","#69A78E")):
        height=[rows[k]["critical_"+category] for k in selected]
        axes[1,0].bar(range(4),height,bottom=bottom,color=col,label=category)
        bottom=[a+b for a,b in zip(bottom,height)]
    axes[1,0].set_xticks(range(4),[a+"\n"+names[p] for a,p,_ in selected],fontsize=8)
    axes[1,0].set_ylabel("Cycles");axes[1,0].set_title("Observed critical chain at 1024 B/cycle");axes[1,0].legend(fontsize=8)
    for a,p,_ in selected:
        detail=read_json(args.analysis/f"{a}-memory-1024-{p}.json")
        loads=sorted(r["payload_bytes"]/1024 for r in detail["spatial"]["directed_links"])
        axes[1,1].step(loads,[(i+1)/len(loads) for i in range(len(loads))],where="post",
                       color=colors[p],linestyle="-" if a=="direct" else "--",label=f"{names[p]} / {a}")
    axes[1,1].set_xlabel("Payload KiB per directed link (including zero-load links)")
    axes[1,1].set_ylabel("Cumulative fraction");axes[1,1].set_title("Physical link-load distribution, 1024 B/cycle")
    axes[1,1].legend(fontsize=8);axes[1,1].grid(alpha=.2)
    fig.suptitle("Same TP8 block and rank-local completion; direct-root vs fixed heap tree\nAnalytical services, unmatched author physical costs",fontsize=11)
    def save(fig,stem):
        for ext in ("pdf","svg","png"):fig.savefig(args.output/f"{stem}.{ext}",dpi=180)
        plt.close(fig)
    save(fig,"algorithm_comparison")

    # Geometry evidence from the original exports; positions are router centers.
    fig,axes=plt.subplots(2,2,figsize=(10,9),constrained_layout=True)
    maximum=0;panels=[]
    direct_path=Path(summary["runs"][0]["path"]);tree_path=Path(summary["runs"][1]["path"])
    for i,a in enumerate(("direct","tree")):
        for j,p in enumerate(names):
            exp=read_json((direct_path if a=="direct" else tree_path)/f"memory-1024/{p}/network.json")
            rec=read_json((direct_path if a=="direct" else tree_path)/f"memory-1024/{p}/execution.json")
            spatial=read_json(args.analysis/f"{a}-memory-1024-{p}.json")["spatial"]
            xy={r:(c["position"]["x"],c["position"]["y"]) for r,c in enumerate(exp["inputs"]["placement"]["chiplets"])}
            loads=defaultdict(int)
            for edge in spatial["directed_links"]:loads[tuple(sorted((edge["source"],edge["destination"])))] += edge["payload_bytes"]
            maximum=max(maximum,max(loads.values()));panels.append((axes[i,j],a,p,exp,rec,spatial,xy,loads))
    norm=Normalize(0,maximum/1024)
    for ax,a,p,exp,rec,spatial,xy,loads in panels:
        paths=[[xy[u],xy[v]] for u,v in loads]
        ax.add_collection(LineCollection(paths,colors="#D9D9D9",linewidths=.6,zorder=1))
        active=[edge for edge in loads if loads[edge]]
        lc=LineCollection([[xy[u],xy[v]] for u,v in active],cmap="plasma",norm=norm,
                          linewidths=[1+3*loads[e]/maximum for e in active],zorder=2)
        lc.set_array([loads[e]/1024 for e in active]);ax.add_collection(lc)
        attach=dict((e["node"],e["router"]) for e in exp["endpoints"])
        ep={r["endpoint"]:r for r in spatial["endpoint_rows"]}
        for rank,e in enumerate(rec["worker_endpoints"]):
            x,y=xy[attach[e]];amount=ep[e]["total_payload_bytes"]
            ax.scatter([x],[y],s=40+160*amount/114688,facecolor="white",edgecolor="black",zorder=3)
            ax.annotate(str(rank),(x,y),ha="center",va="center",fontsize=7,zorder=4)
        ax.axvline(0,color="#3978A2",linestyle=":",label="x=0 graph cut")
        ax.autoscale();ax.set_aspect("equal");ax.set_xlim(-95,95);ax.set_ylim(-95,95)
        ax.set_title(a+" / "+names[p]);ax.set_xlabel("x (mm)");ax.set_ylabel("y (mm)")
    fig.colorbar(lc,ax=axes.ravel().tolist(),label="Payload KiB, both directions combined per link")
    fig.suptitle("Observed spatial traffic at 1024 B/cycle (all layers projected)\nNumbers: logical ranks; node area: endpoint in+out bytes; graph cut x=0",fontsize=11)
    save(fig,"spatial_projection")
    write_json(args.output/"FIGURES.json",dict(
        source_commit=subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(),
        matplotlib=matplotlib.__version__,analysis_sha256=digest(args.analysis/"ANALYZED.json"),
        artifacts_sha256={p.name:digest(p) for p in sorted(args.output.iterdir()) if p.is_file()}))


if __name__=="__main__":main()
