# 已有应用结果的网络抽象误差：只读复核

2026-10-07 在 eex005 重新构建绑定、独立审计已有两种后端的事件和关键链；
核对 420 个源产物哈希，**没有启动新的仿真**。来源和分析版本见
[ANALYZED.json](ANALYZED.json)。三个新增误差汇总单元测试在 eex005 通过；
没有把历史 130 项测试当作本轮重新运行。

| 指标 | 复算结果 |
|---|---:|
| 已有完整案例 | 12 |
| Coarse 相对 BookSim 的应用时间 MAPE | 1.470193% |
| 最大应用时间绝对百分比误差 | 3.276723% |
| 六组 placement 排名一致 | 6/6 |
| Tree/1024 的参考 B−R | −308 cycles |
| 同组 coarse B−R | −548 cycles |
| 差距误差 | −240 cycles；相对参考差距绝对值为 77.922% |

完整数据：[应用误差](applications.csv)、[收益差距误差](placement_gaps.csv)、
[SUMMARY](SUMMARY.json)。小的应用相对误差不保证接近相消的设计收益估计准确。
当前没有公平分离的后端成本测量，不能填写模拟加速比。

消息配对按同一逻辑 phase；分析同时保留 ready、finish、service duration、coarse
queue/serialization/latency、native 每 flit 实际路径和两种模型的关键链。
单个案例的消息服务 MAPE 为 5.90%–18.71%，大于其应用误差；非关键和重叠消息
不能直接相加成应用误差。12 个案例中，11 个有至少一个 flit 的路径与粗模型不同。
即使传输逻辑相同，也不能将所有差异归结为“不模拟竞争”。粗模型仍有链路 FCFS
排队，其总 network queue 在本例中为 0–6 cycles。

详细 `DETAILS.json` 保留在服务器
`/home/wangziheng/wafer_simulator/runs/model-fidelity-saved-001`，其哈希在清单中。
该文件包括两种完整关键链与逐消息路径，未下载入 Git。原始运行与图表未改写。

这只评价现有共同目标执行合同下的两种网络后端，不验证真实 wafer，亦未验证
compute reticle 内部的聚合是否准确。下一项具体研究对象已转到
[reticle 供数/接收边界](../../RETICLE_BOUNDARY_RESEARCH.md)；原通用六条件成本
sweep 延后，尚未运行。

复算命令（eex005，使用新的绝对输出目录）：

```bash
PYTHONPATH=src /home/wangziheng/wafer_simulator/.venv/bin/python \
  scripts/analyze_model_fidelity_remote.py \
  /home/wangziheng/wafer_simulator/runs/collective-memory-balance-001 \
  /home/wangziheng/wafer_simulator/runs/collective-tree-spatial-001 \
  /home/wangziheng/wafer_simulator/runs/model-fidelity-saved-NEW
```
