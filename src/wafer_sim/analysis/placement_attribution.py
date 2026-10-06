"""Read-only attribution from accepted complete events; no simulator invocation."""
import csv
from importlib.metadata import distributions
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

from wafer_sim.analysis.campaign_acceptance import ARMS, accept
from wafer_sim.analysis.critical_chain import difference, message_timings, parent_graph, recover
from wafer_sim.io import digest, read_json, write_json


def _environment(output, filename):
    path = Path(output) / filename
    write_json(path, dict(host=platform.node(), platform=platform.platform(), python=sys.version,
        python_executable=str(Path(sys.executable).resolve()), python_executable_sha256=digest(sys.executable),
        packages=sorted((dict(name=d.metadata["Name"], version=d.version) for d in distributions()),
                        key=lambda d: d["name"].lower())))
    return digest(path)


def _csv(path, rows):
    iterator = iter(rows)
    first = next(iterator, None)
    if first is None:
        raise ValueError(f"Expected nonempty output: {path}")
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(first))
        writer.writeheader()
        writer.writerow(first)
        writer.writerows(iterator)


def _endpoint_map(arm):
    physical = {e["node"]: e for e in arm["network"]["endpoints"]}
    mapping = {}
    for entry in arm["contract"]["endpoint_mapping"]:
        key = (entry["host"], entry["nic"])
        if key in mapping or entry["node"] not in physical:
            raise ValueError("Invalid endpoint mapping")
        mapping[key] = physical[entry["node"]]
    if len({e["node"] for e in mapping.values()}) != len(mapping):
        raise ValueError("Non-injective endpoint mapping")
    return mapping


def _chain_rows(ops, events, chain, mapping, cpu_stride):
    for index, raw_id in enumerate(chain["ids"]):
        op_id = int(raw_id)
        op = ops[op_id]
        host, cpu, nic, kind = (int(op[f]) for f in ("rank", "cpu", "nic", "kind"))
        endpoint = mapping.get((host, nic)) if kind != 0 else None
        start, ready, finish = (int(events[f][op_id]) for f in ("start_cycle", "ready_cycle", "finish_cycle"))
        yield dict(sequence=index, op_id=op_id, kind=("calc", "send", "recv")[kind],
                   host=host, label=int(op["label"]), cpu=cpu, cpu_resource=host * cpu_stride + cpu,
                   nic=nic, endpoint=endpoint["node"] if endpoint else "",
                   router=endpoint["router"] if endpoint else "", layer=endpoint["layer"] if endpoint else "",
                   x_mm=endpoint["position"]["x"] if endpoint else "",
                   y_mm=endpoint["position"]["y"] if endpoint else "",
                   location_scope="network_endpoint" if endpoint else "logical_host_cpu_only",
                   controlling_predecessor=int(chain["ids"][index - 1]) if index else -1,
                   predecessor_relation=chain["predecessor_relations"][index],
                   cpu_predecessor=int(events["cpu_predecessor"][op_id]),
                   ready_cycle=ready, start_cycle=start, finish_cycle=finish,
                   cpu_wait_cycles=start - ready, service_cycles=finish - start,
                   injection_wait_cycles=int(events["first_inject_cycle"][op_id]) - start if kind == 1 else "",
                   first_inject_to_complete_cycles=finish - int(events["first_inject_cycle"][op_id]) if kind == 1 else "",
                   original_amount=int(op["amount"]), amount_unit="cycles_at_1GHz" if kind == 0 else "bytes")


def _paired_row(index, send_ids, recv_ids, ops, maps, metrics, membership, flit_bytes):
    send, recv = int(send_ids[index]), int(recv_ids[index])
    op, target = ops[send], ops[recv]
    source_key, target_key = (int(op["rank"]), int(op["nic"])), (int(target["rank"]), int(target["nic"]))
    row = dict(send_id=send, recv_id=recv, tag=int(op["tag"]), source_host=source_key[0],
               source_nic=source_key[1], destination_host=target_key[0], destination_nic=target_key[1],
               source_label=int(op["label"]), destination_label=int(target["label"]),
               payload_bytes=int(op["amount"]), flits=(int(op["amount"]) + flit_bytes - 1) // flit_bytes)
    for arm in ARMS:
        source, destination = maps[arm][source_key], maps[arm][target_key]
        row.update({f"{arm}_source_endpoint": source["node"], f"{arm}_destination_endpoint": destination["node"],
                    f"{arm}_source_router": source["router"], f"{arm}_destination_router": destination["router"],
                    f"{arm}_on_chain": bool(membership[arm][send])})
        row.update({f"{arm}_{field}": int(values[index]) for field, values in metrics[arm].items()})
    for field in ("cpu_wait", "injection_wait", "first_inject_to_complete", "service", "ready_to_complete", "finish_cycle"):
        row[f"baseline_minus_rotated_{field}"] = int(metrics[ARMS[0]][field][index]) - int(metrics[ARMS[1]][field][index])
    return row


def _local_row(op_id, ops, events, membership, stride):
    op = ops[op_id]
    row = dict(op_id=int(op_id), host=int(op["rank"]), label=int(op["label"]), cpu=int(op["cpu"]),
               cpu_resource=int(op["rank"]) * stride + int(op["cpu"]), duration_cycles=int(op["amount"]))
    for name in ARMS:
        row[f"{name}_on_chain"] = bool(membership[name][op_id])
        for field in ("ready_cycle", "start_cycle", "finish_cycle", "cpu_predecessor"):
            row[f"{name}_{field}"] = int(events[name][field][op_id])
        if row[f"{name}_finish_cycle"] - row[f"{name}_start_cycle"] != row["duration_cycles"]:
            raise ValueError("Local duration differs across the paired observed records")
    row["baseline_minus_rotated_start_cycle"] = row["baseline_start_cycle"] - row["ours_rotated_start_cycle"]
    return row


def render(summary, acceptance, output):
    """Render again after reference equivalence, without rereading large event files."""
    table = summary["table"]
    lines = ["# Baseline–Rotated 完整应用对照与归因", "",
             f"输入实验：`{Path(acceptance['campaign']).name}`。成对完整审计：通过。"
             f"参考实现等价性：**{acceptance['implementation_equivalence']['status']}**。", "",
             f"应用加速比 T(Baseline)/T(Rotated) = **{summary['application_speedup']:.9f}**；"
             f"完成时间缩短 **{summary['application_time_reduction_percent']:.6f}%**。", "",
             "| 指标 | Baseline | Rotated |", "| --- | ---: | ---: |"]
    for row in table:
        values = [f"{v:,.6f}" if isinstance(v, float) else f"{v:,}" for v in (row["baseline"], row["ours_rotated"])]
        lines.append(f"| {row['metric']} ({row['unit']}) | {values[0]} | {values[1]} |")
    lines += ["", f"平均 packet latency 变化：降低 {summary['packet_latency_reduction_percent']:.6f}%。"
              "该比例与应用时间缩短分别报告；不相除定义‘兑现率’。", "",
              "平均消息就绪至完成时间还包含 CPU-lane 等待。两者变化比例不同时，应先检查"
              "消息区间与实际关键链；不能由平均 packet latency 单独推导应用完成时间。", "",
              "## 两条实际关键链", "",
              "每个 placement 独立恢复一条确定性关键链：终点取最大完成时间中 ID 最小者，"
              "前驱取最大完成时间中 ID 最大者，与已有审计一致。存在同值路径时，这不是所有关键路径的枚举。", "",
              "每条链的本地服务时间 + 消息服务时间都严格等于应用完成时间。"
              "消息的 CPU 等待已经由前驱链解释，不能再加到这项总和中。", ""]
    for arm in ARMS:
        chain = summary["chains"][arm]
        lines.append(f"- {arm}: {chain['critical_chain_nodes']:,} 个节点；"
                     f"本地工作 {chain['critical_local_work_cycles']:,} cycles，"
                     f"消息服务 {chain['critical_message_cycles']:,} cycles；"
                     f"本地工作占链时长 {100 * chain['critical_local_work_cycles'] / chain['application_cycles']:.6f}%。")
    means = {row["metric"]: row for row in table}
    cpu_shares = {name: 100 * means["平均发送前 CPU 等待"][name] / means["平均消息就绪至完成"][name]
                  for name in ARMS}
    lines += ["", f"在全部消息的就绪至完成区间中，CPU-lane 等待占均值的比例为 "
              f"Baseline {cpu_shares['baseline']:.4f}%、Rotated {cpu_shares['ours_rotated']:.4f}%。"
              "这是消息级平均值，和关键链时长占比属于不同观察量。", ""]
    if (summary["packet_latency_reduction_percent"] > 0 and
            abs(summary["application_time_reduction_percent"]) < 1 and
            all(c["critical_local_work_cycles"] / c["application_cycles"] > .95
                for c in summary["chains"].values())):
        lines += ["当前观察是：平均 packet latency 下降，但整份工作完成时间变化不足 1%；"
                  "两条实际关键链均由固定本地阶段占据绝大部分时长。因此平均 packet 延迟下降"
                  "没有按相同比例缩短最终完成时间。下一步应先检查消息到达如何改变本地资源顺序"
                  "与关键链选择。链上的消息服务占比不能当作网络优化收益的上限，因为网络时序"
                  "也可能改变后续 CPU-lane 执行顺序。", ""]
    delta = summary["chain_difference"]
    lines += ["", "两条链可能经过不同操作。以下恒等式逐项核对完成时间差（Baseline − Rotated）：", "",
              "| 操作类别 | 共同节点服务差 | 仅 Baseline 链服务 | 仅 Rotated 链服务（扣除） |",
              "| --- | ---: | ---: | ---: |"]
    for kind in ("local", "message"):
        lines.append(f"| {kind} | {delta[f'common_{kind}_delta']:,} | {delta[f'baseline_only_{kind}']:,} | {delta[f'rotated_only_{kind}']:,} |")
    local_delta = delta['common_local_delta'] + delta['baseline_only_local'] - delta['rotated_only_local']
    message_delta = delta['common_message_delta'] + delta['baseline_only_message'] - delta['rotated_only_message']
    lines += ["", f"其中本地阶段的链上服务差为 {local_delta:,} cycles，"
              f"消息阶段的链上服务差为 {message_delta:,} cycles。"]
    lines += ["", f"逐项相加 = **{delta['accounted_delta_cycles']:,} cycles**，"
              f"等于观测完成时间差 {delta['application_delta_cycles']:,} cycles。"
              "这是实际服务时间的记账恒等式，不是逐消息独立加速的反事实效果。", "",
              "本地操作的原始 duration 在两个 placements 中完全相同。‘仅某条链上的本地工作’之差"
              "表示关键链选择了不同的固定操作，不能解释成本地计算单元变快。"
              "关键链并集中的本地操作配对见 `critical_local_pairs.csv`。", "",
              "### 各关键链中的本地阶段", "",
              "| 所属链 | 操作 ID | Host/CPU | 固定 duration | B/R 都在选定链上 | B 开始 | R 开始 | B CPU 前驱 | R CPU 前驱 |",
              "| --- | ---: | --- | ---: | --- | ---: | ---: | ---: | ---: |"]
    for name in ARMS:
        for row in summary["top_critical_local"][name]:
            both = row["baseline_on_chain"] and row["ours_rotated_on_chain"]
            lines.append(f"| {name} | {row['op_id']} | {row['host']}/{row['cpu']} | {row['duration_cycles']:,} | {both} | "
                         f"{row['baseline_start_cycle']:,} | {row['ours_rotated_start_cycle']:,} | "
                         f"{row['baseline_cpu_predecessor']} | {row['ours_rotated_cpu_predecessor']} |")
    order = summary["observed_order_changes"]
    lines += ["", f"两条选定链共有 {order['common_nodes']:,} 个操作；共同操作的相对顺序是否一致："
              f"{order['common_order_equal']}。关键链并集中的 {order['critical_local_nodes']:,} 个本地操作里，"
              f"有 {order['critical_local_cpu_predecessor_changes']:,} 个操作的 CPU 等待前驱记录发生变化。"
              f"全部本地操作中则有 {order['all_local_cpu_predecessor_changes']:,} 个前驱发生变化。"
              "原生 cpu_predecessor 仅在 start > ready 时记录，−1 表示没有额外 CPU 等待；"
              "它不是该 lane 的完整执行顺序。因此前驱变化计数描述阻塞关系变化，不能直接当作"
              "CPU 操作换序次数，也不能独立证明是哪一条消息造成了最终时间差。", ""]
    lines += ["",
              "## 关键消息与另一个 placement 的对应记录", "",
              "下面分别列出两条链上服务时间最大的消息；完整配对包含所有消息，保存在 `message_pairs.csv`。"
              "‘注入后’区间包括后续 flit 注入、传输及竞争，不能称为纯链路延迟。"]
    for arm in ARMS:
        lines += ["", f"### {arm} 的关键消息", "",
                  "| Send ID | 字节 | B/R 都在选定链上 | B CPU 等待 | R CPU 等待 | B 注入前 | R 注入前 | B 注入后 | R 注入后 |",
                  "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for row in summary["top_critical_messages"][arm]:
            both = row["baseline_on_chain"] and row["ours_rotated_on_chain"]
            values = [row[f"{name}_{field}"] for field in ("cpu_wait", "injection_wait", "first_inject_to_complete") for name in ARMS]
            lines.append(f"| {row['send_id']} | {row['payload_bytes']:,} | {both} | " + " | ".join(f"{v:,}" for v in values) + " |")
    lines += ["", "### 关键链并集中服务时间变化最大的配对消息", "",
              "按同一消息的服务时间差绝对值排序，正数表示 Baseline 更长。只列至少出现在一条"
              "选定链中的消息；这比只列最大绝对延迟更能定位需要解释的变化，但仍不是单消息反事实归因。", "",
              "| Send ID | B 链 / R 链 | CPU 等待差 | 注入前差 | 注入后差 | 服务差 B−R |",
              "| --- | --- | ---: | ---: | ---: | ---: |"]
    for row in summary["largest_critical_message_changes"]:
        values = [row[f"baseline_minus_rotated_{key}"] for key in
                  ("cpu_wait", "injection_wait", "first_inject_to_complete", "service")]
        lines.append(f"| {row['send_id']} | {row['baseline_on_chain']} / {row['ours_rotated_on_chain']} | " +
                     " | ".join(f"{v:,}" for v in values) + " |")
    lines += ["", "## 全部消息与关键链覆盖", "",
              "以下累计值只描述消息集合，多个消息可能重叠，不能相加作为应用完成时间。", "",
              "| 消息集合 | 数量 | 累计服务时间差 B−R |", "| --- | ---: | ---: |"]
    for name, group in summary["message_groups"].items():
        lines.append(f"| {name} | {group['messages']:,} | {group['service_delta_cycles']:,} |")
    lines += ["", "## 解释边界", "",
              "这是完整 ATLAHS capture 在固定本地执行模型下的条件化回放；calc 包括本地间隔、"
              "reduction/copy 与部分 intra-host transfer。它不是缺失的 WoW 论文 trace 复现，也不是标定过的原生 wafer 训练时间。", "",
              "当前结果只有一种 mapping 和 seed 1；router/link 成本不同。表中的总链路带宽是链路资源之和，"
              "不是可供任意两个区域使用的带宽，也不是应用有效带宽。", "",
              "calc 的位置只记录逻辑 host/CPU lane。该回放模型未把所有 calc lane 分配到物理 reticle，"
              "因此 CSV 不编造其物理坐标。通信端点位置见 `endpoint_mapping.csv`。", "",
              "消息服务暂未分解到 router、port、VC 或仲裁阻塞；注入等待既可能来自本地注入资源，"
              "也可能由下游反压造成。当前证据能够定位关键消息和时间区间，尚不能定位内部阻塞资源。", "",
              "两种 placements 的宿主运行时间仅作为实现成本记录，不用于计算架构加速比。并发与 debugger 采样"
              "使既有宿主时间比只能视为观测值。", "",
              f"下一轮登记状态：`{summary['next_experiment']['status']}`，"
              f"已登记组数：{summary['next_experiment']['registered_groups']}。", ""]
    if summary["next_experiment"]["registered_groups"]:
        lines += ["下一轮只登记一组 endpoint mapping 配对：将 row-major 改为既有的 permuted 策略，"
                  "映射置换种子固定为 1234，网络 seed 仍为 1。逻辑任务、duration、payload、依赖、"
                  "物理资源和原生实现保持不变。目的是检查当前‘网络均值改善而应用变化小’及关键链"
                  "变化是否依赖当前端点分配。详见 `next_experiment.json`；必须先通过本轮参考等价性验收。", ""]
    elif summary["next_experiment"]["status"] == "deferred_for_local_stage_provenance":
        lines += ["根据新的研究优先级，暂缓 mapping 实验。先追溯主要固定 calc 的来源，"
                  "再判断原节点内传输能否有依据地迁移到目标 WoW 资源竞争；不按占比阈值自动选择实验。", ""]
    lines += ["本分析不启动新仿真，也不扩展 thermal 或 GPU。", ""]
    (Path(output) / "attribution.md").write_text("\n".join(lines))


def analyze(campaign, output):
    """Analyze saved evidence; next-study registration waits for reference equivalence."""
    info = accept(campaign)
    graph = Path(info["config"]["graph_directory"])
    gate = read_json(graph / "graph_audit.json")
    work = info["work"]
    if (not gate["dependency_gate_passed"] or gate["truncated"] or gate["removed_dependencies"] or
            gate["source_sha256"] != work["source_sha256"]):
        raise ValueError("Original complete graph gate/identity differs")
    ops = np.load(graph / "operations.npy", mmap_mode="r")
    deps = np.load(graph / "dependencies.npy", mmap_mode="r")
    pairs = np.load(graph / "message_pairs.npy", mmap_mode="r")
    if (len(ops), len(deps), len(pairs)) != (work["instructions"], work["original_dependencies"], work["arrival_dependencies"]):
        raise ValueError("Complete graph work counts differ")
    sends = np.flatnonzero(ops["kind"] == 1)
    order = np.argsort(pairs[:, 0])
    if not np.array_equal(pairs[order, 0], sends) or len(sends) != work["messages"]:
        raise ValueError("Not every message has a unique matched receive")
    recvs = pairs[order, 1]
    if np.any(ops["kind"][recvs] != 2) or not np.array_equal(ops["amount"][sends], ops["amount"][recvs]):
        raise ValueError("Paired message identity differs")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    parents = parent_graph(len(ops), deps, pairs)
    events, chains, maps, metrics = {}, {}, {}, {}
    for name in ARMS:
        arm = info["arms"][name]
        events[name] = np.load(arm["path"] / "checked_events.npy", mmap_mode="r")
        if len(events[name]) != len(ops):
            raise ValueError("Checked event count differs from full work")
        chains[name] = recover(ops, events[name], parents, arm["audit"])
        maps[name] = _endpoint_map(arm)
        metrics[name] = message_timings(events[name], sends)
        for metric, audit_key in (("cpu_wait", "mean_cpu_wait_before_send"),
                                  ("injection_wait", "mean_message_injection_wait"),
                                  ("first_inject_to_complete", "mean_first_inject_to_complete"),
                                  ("ready_to_complete", "mean_message_ready_to_complete")):
            if not np.isclose(metrics[name][metric].mean(), arm["audit"][audit_key], rtol=0, atol=1e-8):
                raise ValueError(f"Message summary differs from existing audit: {name}/{metric}")
        directory = output / name
        directory.mkdir()
        _csv(directory / "critical_chain.csv", _chain_rows(ops, events[name], chains[name], maps[name], work["cpu_stride"]))
        print(f"Recovered {name} critical chain: {len(chains[name]['ids'])} nodes", flush=True)
    delta, left, right = difference(ops, events[ARMS[0]], events[ARMS[1]], chains[ARMS[0]], chains[ARMS[1]])
    membership = dict(zip(ARMS, (left, right)))
    local_ids = np.flatnonzero((left | right) & (ops["kind"] == 0))
    if len(local_ids):
        _csv(output / "critical_local_pairs.csv", (_local_row(int(i), ops, events, membership, work["cpu_stride"])
                                                   for i in local_ids))
    top_local = {}
    for name in ARMS:
        selected = np.flatnonzero(membership[name] & (ops["kind"] == 0))
        ranked = selected[np.argsort(ops["amount"][selected], kind="stable")[-10:][::-1]]
        top_local[name] = [_local_row(int(i), ops, events, membership, work["cpu_stride"]) for i in ranked]
    row = lambda index: _paired_row(index, sends, recvs, ops, maps, metrics, membership, work["flit_bytes"])
    _csv(output / "message_pairs.csv", (row(i) for i in range(len(sends))))
    _csv(output / "endpoint_mapping.csv", (
        dict(placement=name, host=host, nic=nic, endpoint=e["node"], router=e["router"], layer=e["layer"],
             x_mm=e["position"]["x"], y_mm=e["position"]["y"])
        for name in ARMS for (host, nic), e in sorted(maps[name].items())))
    top = {}
    for name in ARMS:
        selected = np.flatnonzero(membership[name][sends])
        ranked = selected[np.argsort(-metrics[name]["service"][selected], kind="stable")[:10]]
        top[name] = [row(int(i)) for i in ranked]
    selected = np.flatnonzero(left[sends] | right[sends])
    service_delta = metrics[ARMS[0]]["service"] - metrics[ARMS[1]]["service"]
    ranked_changes = selected[np.argsort(-np.abs(service_delta[selected]), kind="stable")[:10]]
    common_left = chains[ARMS[0]]["ids"][right[chains[ARMS[0]]["ids"]]]
    common_right = chains[ARMS[1]]["ids"][left[chains[ARMS[1]]["ids"]]]
    changed_cpu = events[ARMS[0]]["cpu_predecessor"] != events[ARMS[1]]["cpu_predecessor"]
    order_changes = dict(common_nodes=len(common_left), common_order_equal=bool(np.array_equal(common_left, common_right)),
                         critical_local_nodes=len(local_ids),
                         critical_local_cpu_predecessor_changes=int(changed_cpu[local_ids].sum()),
                         all_local_cpu_predecessor_changes=int(changed_cpu[ops["kind"] == 0].sum()))
    groups = {}
    for name, mask in (("both_selected_chains", left[sends] & right[sends]),
                       ("baseline_chain_only", left[sends] & ~right[sends]),
                       ("rotated_chain_only", right[sends] & ~left[sends]),
                       ("neither_selected_chain", ~left[sends] & ~right[sends])):
        groups[name] = dict(messages=int(mask.sum()), service_delta_cycles=int(
            (metrics[ARMS[0]]["service"][mask] - metrics[ARMS[1]]["service"][mask]).sum()))
    table = []
    for label, unit, source, key in (
        ("完整应用完成时间", "cycles", "audit", "application_cycles"),
        ("完整应用完成时间", "seconds at 1 GHz", "audit", "application_seconds_at_1GHz"),
        ("平均消息就绪至完成", "cycles", "audit", "mean_message_ready_to_complete"),
        ("平均发送前 CPU 等待", "cycles", "audit", "mean_cpu_wait_before_send"),
        ("平均首 flit 注入前等待", "cycles", "audit", "mean_message_injection_wait"),
        ("平均首 flit 注入至消息完成", "cycles", "audit", "mean_first_inject_to_complete"),
        ("关键链本地工作", "cycles", "audit", "critical_local_work_cycles"),
        ("关键链消息服务", "cycles", "audit", "critical_message_cycles"),
        ("计算端点", "count", "resources", "compute_reticles"),
        ("Routers", "count", "resources", "routers"),
        ("无向链路", "count", "resources", "undirected_links"),
        ("总有向链路带宽", "bits/cycle", "resources", "aggregate_directed_link_bits_per_cycle")):
        table.append(dict(metric=label, unit=unit, **{name: info["arms"][name][source][key] for name in ARMS}))
    for key in ("Packet latency average", "Network latency average", "Hops average"):
        table.append(dict(metric=key, unit="hops" if key == "Hops average" else "cycles",
                          **{name: info["arms"][name]["execution"]["network_metrics"][key] for name in ARMS}))
    _csv(output / "application_comparison.csv", table)
    a, b = (chains[name]["application_cycles"] for name in ARMS)
    pa, pb = (info["arms"][name]["execution"]["network_metrics"]["Packet latency average"] for name in ARMS)
    summary = dict(campaign=str(info["campaign"]), work=work, table=table, application_speedup=a / b,
                   application_time_reduction_percent=100 * (a - b) / a,
                   packet_latency_reduction_percent=100 * (pa - pb) / pa,
                   chain_difference=delta, chains={name: {k: v for k, v in chains[name].items()
                       if k not in ("ids", "predecessor_relations")} for name in ARMS},
                   top_critical_messages=top, top_critical_local=top_local, message_groups=groups,
                   largest_critical_message_changes=[row(int(i)) for i in ranked_changes],
                   observed_order_changes=order_changes,
                   host_wall_seconds={name: info["arms"][name]["execution"]["wall_seconds"] for name in ARMS})
    summary["next_experiment"] = dict(status="pending_reference_equivalence", registered_groups=0)
    print("Recording complete-input and artifact hashes", flush=True)
    inputs = {str(graph / file): digest(graph / file) for file in
              ("graph_audit.json", "operations.npy", "dependencies.npy", "message_pairs.npy")}
    for file in ("COMPLETE.json", "config.json", "provenance.json", "registration.json", "results.json", "summary.csv", "comparison.md"):
        inputs[str(info["campaign"] / file)] = digest(info["campaign"] / file)
    for name in ARMS:
        path = info["arms"][name]["path"]
        for file in ("contract.json", "audit.json", "trace_report.json", "execution.json", "resources.json", "network.json",
                     "trace.json", "events.jsonl", "checked_events.npy") + (("dependency_profile.json", "dependency_profile_audit.json")
                         if info["config"].get("dependency_profile") else ()):
            inputs[str(path / file)] = digest(path / file)
        if inputs[str(path / "trace.json")] != info["arms"][name]["contract"]["trace_sha256"]:
            raise ValueError("Full mapped input identity changed")
    original_environment = info["campaign"].parent.parent / "logs/python-environment.txt"
    if original_environment.exists():
        inputs[str(original_environment)] = digest(original_environment)
    acceptance = dict(architecture_pair_accepted=True, implementation_equivalence=dict(status="pending"),
                       campaign=str(info["campaign"]), simulator_provenance=info["provenance"],
                       analysis_source_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
                       input_sha256=inputs, work=work,
                       analysis_environment_sha256=_environment(output, "analysis_environment.json"))
    write_json(output / "summary.json", summary)
    write_json(output / "acceptance.json", acceptance)
    render(summary, acceptance, output)
    artifacts = [p for p in output.rglob("*") if p.is_file()]
    write_json(output / "ANALYZED.json", dict(architecture_pair_accepted=True,
        implementation_equivalence="pending", artifact_sha256={str(p.relative_to(output)): digest(p) for p in artifacts}))
    print(f"Complete-pair attribution written: {output}", flush=True)
    return summary


def finalize(output, equivalence, register_next=None):
    output, equivalence = Path(output).resolve(), Path(equivalence).resolve()
    acceptance = read_json(output / "acceptance.json")
    verification = read_json(equivalence)
    if verification.get("passed") is not True or not verification.get("same_full_work_and_events"):
        raise ValueError("Complete implementation equivalence has not passed")
    if Path(verification["candidate"]).resolve() != Path(acceptance["campaign"]):
        raise ValueError("Equivalence belongs to a different campaign")
    if len(verification["arms"]) != 2 or {a["placement"] for a in verification["arms"]} != set(ARMS):
        raise ValueError("Equivalence omits a placement")
    for arm in verification["arms"]:
        if (arm.get("exact_full_event_match") is not True or len(arm["hashes"]) != 2 or
                {h["file"] for h in arm["hashes"]} != {"trace.json", "events.jsonl"}):
            raise ValueError("Equivalence must bind both complete input and event hashes")
        for file in arm["hashes"]:
            key = str(Path(acceptance["campaign"]) / arm["placement"] / file["file"])
            if acceptance["input_sha256"].get(key) != file["sha256"]:
                raise ValueError("Equivalence differs from attributed input/events")
    acceptance["implementation_equivalence"] = dict(status="passed", path=str(equivalence), sha256=digest(equivalence),
                                                      reference=verification["reference"])
    summary = read_json(output / "summary.json")
    summary["next_experiment"] = (register_next(accept(acceptance["campaign"]), summary, output) if register_next else
                                  dict(status="needs_result_review", registered_groups=0))
    acceptance["finalization_source_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    acceptance["finalization_environment_sha256"] = _environment(output, "finalization_environment.json")
    write_json(output / "summary.json", summary)
    write_json(output / "acceptance.json", acceptance)
    render(summary, acceptance, output)
    manifest = read_json(output / "ANALYZED.json")
    manifest["implementation_equivalence"] = "passed"
    for file in ("acceptance.json", "summary.json", "attribution.md", "next_experiment.json",
                 "next_experiment_config.json", "next_experiment_decision.json", "implementation_equivalence.json",
                 "finalization_environment.json"):
        if (output / file).exists():
            manifest["artifact_sha256"][file] = digest(output / file)
    write_json(output / "ANALYZED.json", manifest)
    write_json(output / "FINAL_ACCEPTED.json", dict(architecture_pair_accepted=True, implementation_equivalence=True,
        acceptance_sha256=digest(output / "acceptance.json"), report_sha256=digest(output / "attribution.md"),
        equivalence_sha256=digest(equivalence)))
