# Compute-reticle 边界：源代码与既有资源复核

2026-10-07，eex005，只读；没有新仿真。核对原 tree run 的全部 141 个产物哈希，
读取 memory-32 两个 placements 的真实 export/target/timing。证据与代码哈希见
[BOUNDARY_AUDIT.json](BOUNDARY_AUDIT.json)。源/论文语义解释见
[研究合同](../../RETICLE_BOUNDARY_RESEARCH.md)。

| 已导出的 compute reticles | Baseline | Rotated |
|---|---:|---:|
| Reticle 数 | 20 | 20 |
| 每个 reticle 的 endpoint 数 | 1 | 1 |
| 实际外部连接度分布 | 3:4 个；4:16 个 | 3:2 个；4:4 个；5:6 个；6:2 个；7:6 个 |
| 每 endpoint 注入能力 | 2000 B/cycle | 2000 B/cycle |

所以论文标注的 4/7 不等于每个边缘 reticle 都有 4/7 条实际连接；一个 central
router 也不等于一个无限带宽 endpoint。当前 export 使用作者的 trace 模式，
unit_count=1；作者 synthetic 模式的 unit_count=8 是另一个配置，不能混用。

当前缺失的机制候选是：目的 SRAM 写入不控制 native ejection credit；源 memory
read 在提交整个消息前完成，没有与有限边界 FIFO 逐段耦合。网络本身有有限端口、
buffer/credit；数据容量与最终写入发布也已有检查。本次没有证明这些抽象使任何
placement 排名错误，没有建立真实内部 NoC 参数，也未宣称已经实现 hierarchical
模型。

首个模型对照应使局部资源预算、GPC 工作、路径和外部网络一致，再检验简单聚合
是否需要增加边界状态。不能用不同硬件预算制造所谓“模型误差”。

复算（eex005，新的绝对输出目录）：

```bash
PYTHONPATH=src /home/wangziheng/wafer_simulator/.venv/bin/python \
  scripts/inspect_reticle_boundary_remote.py \
  /home/wangziheng/wafer_simulator/runs/collective-tree-spatial-001 \
  /home/wangziheng/wafer_simulator/runs/reticle-boundary-audit-NEW
```
