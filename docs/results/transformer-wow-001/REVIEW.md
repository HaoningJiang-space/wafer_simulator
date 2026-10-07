# 完整 Transformer block：WoW 在线执行与 placement 对照

> 模型修正：本目录保留原始运行记录。随后确认通用多输出 lowering 在每次
> TP2 AllReduce 的 root 多写了 4,096 bytes；这里的绝对完成时间已由
> [collective action 执行结果](../collective-execution-001/REVIEW.md)取代。
> 修正并允许独立 action 重叠后为 12,550／12,918 cycles，差值仍为 368 cycles。
> 原始 JSON 文件及哈希没有改写。

在 eex005 完成。**同一个完整 block 在 Baseline 上需要 13,062 cycles，
Rotated 上需要 13,430 cycles。**在这组固定行优先映射和共同计算／内存参数下，
Rotated 增加 368 cycles（2.82%）。四条关键传输各增加 92 cycles，差异经两次
AllReduce 传到最终输出。没有修改 workload 或映射规则来追求特定排名。

执行版本为 `b572fb2`，只读归因版本为 `89d5bcb`。
[完整验收标记](COMPLETE.json)、[原始汇总](SUMMARY.json)和
[运行身份](STARTED.json)分别保留；归因没有启动新仿真。

## 1. 这次实际执行的是什么

沿用已验收的完整 float32 pre-LayerNorm Transformer forward block：batch 1、
sequence 16、hidden 64、4 heads、FFN 128、2 shards，包含 30 个操作、54 个数据对象、
557,056 MAC，以及注意力和 FFN 输出后的两次 SUM AllReduce。它是独立定义的完整
block，不是截取旧 capture，也不是完整 Llama 训练。

每个区域仍为 256 KiB，读写共享 32 bytes/cycle；矩阵计算为 64 MAC/cycle，
其他算术采用[原配置](../../../configs/transformer_block.json)中的显式服务率。
两边的工作身份和计算／内存参数哈希完全一致。这些是尚未标定到 WoW 的模型参数。

网络来自固定作者版本的两套真实导出图。时钟 1 GHz，16,000 bits/cycle =
2,000 bytes/cycle，BookSim 每通道每周期一个 flit。每条 4,096-byte 逻辑传输
封装成三个 2,000-byte flit，网络为 padding 付费，内存仍只处理 4,096 bytes。
两边各有四条消息、12 flits、16,384 bytes 逻辑数据和 24,000 bytes 网络注入数据。

每当源内存读取完成，目标执行器才向持续运行的 BookSim 提交消息。最后一个 flit
到达后返回完成事件；随后占用目标内存写端口，写完才能解除消费者依赖。
网络队列、credit、VC 和路由状态在调用之间保留。没有提前生成应用通信时间表。

## 2. 完成时间与关键链

| 指标 | Baseline | Rotated |
|---|---:|---:|
| 完整 block 完成时间，cycles | 13,062 | 13,430 |
| 1 GHz 下的时间，μs | 13.062 | 13.430 |
| attention AllReduce，cycles | 1,232 | 1,416 |
| FFN AllReduce，cycles | 1,232 | 1,416 |
| 每条消息就绪至完成，cycles | 72 | 164 |
| 平均 packet latency，cycles | 69 | 161 |
| 选定关键链计算服务，cycles | 6,406 | 6,406 |
| 选定关键链内存服务，cycles | 6,368 | 6,368 |
| 选定关键链网络服务，cycles | 288 | 656 |

关键链的三类服务总量分别精确相加得到 13,062 和 13,430 cycles。服务链包含
本地资源的释放前驱，资源等待没有重复加算；这是观测执行链，不是一般性的瓶颈
敏感度上限。两边关键链明细保存在
[Baseline](baseline/critical_chain.json)和[Rotated](ours_rotated/critical_chain.json)。

## 3. 从映射到路径，再到最终输出

规则固定为按 `(layer,y,x)` 排序后选前两个 compute endpoints。它固定的是规则，
没有固定两个 placement 的物理位置或端点编号：

| 逻辑 worker | Baseline endpoint / 坐标 mm | Rotated endpoint / 坐标 mm |
|---|---|---|
| 0，collective root | 0 / (-52, -49.5) | 0 / (-52, -59) |
| 1 | 1 / (-26, -49.5) | 3 / (26, -53) |

所以这是一组 **placement × 固定映射规则** 的比较，不是对相同物理端点对的比较。
Rotated 的行优先排序在这一位置选中了相距更远的两个端点。这一事实是结果解释的
一部分，不能把差异全部概括为一个抽象 topology 的优劣。

两次 AllReduce 均观察到以下实际 router 路径；每个消息的三个 flit 都走相同路径：

| 方向 | Baseline | Rotated |
|---|---|---|
| gather：worker 1 → 0 | 1 → 23 → 22 → 0 | 3 → 30 → 29 → 1 → 22 → 20 → 0 |
| broadcast：worker 0 → 1 | 0 → 22 → 23 → 1 | 0 → 25 → 26 → 2 → 28 → 30 → 3 |
| inter-router links / 消息 | 3 | 6 |
| 路径链路延迟之和，cycles | 38 | 118 |
| 路径 router 流水之和，cycles | 4 × 4 = 16 | 7 × 4 = 28 |

实际 flit 记录与导出链路参数的连接见 [paths.csv](paths.csv)。这里用 inter-router
links 明确表示边数；BookSim 的 hops 包含源／目的 router，不能混用。

每条消息的差异为 `(118 - 38) + (28 - 16) = 92 cycles`。首 flit 的注入与接收
时间差分别为 67/159 cycles；三个 flit 连续注入，接收相隔两周期。两边首尾接收
跨度都为 4 cycles，最后一个 flit 所在周期结束后发布完成，因此消息服务分别为
72/164 cycles。接口的周期边界换算和两端通道开销在两边相同。

每个 AllReduce 另外需要 1,024 cycles 内存服务和 64 cycles 加法计算，因此：

```
Baseline: 1024 + 64 + 2 × 72  = 1232 cycles
Rotated:  1024 + 64 + 2 × 164 = 1416 cycles
```

完成事件继续推动真实的后续时间，而不是给最终结果额外加一个网络差值：

| 事件 | Baseline | Rotated | R − B |
|---|---:|---:|---:|
| attention AllReduce 就绪 | 4,625 | 4,625 | 0 |
| attention AllReduce 写完全部输出 | 5,857 | 6,041 | 184 |
| FFN AllReduce 就绪 | 11,382 | 11,566 | 184 |
| FFN AllReduce 写完全部输出 | 12,614 | 12,982 | 368 |
| 最终两个输出完成 | 13,062 | 13,430 | 368 |

[逐操作配对](operations.csv)显示：除两个 collective 各延长 184 cycles 外，其余
28 个操作的 admitted-to-finish 时长全部不变。第一次 collective 后的工作整体后移
184 cycles，最终 residual/output 后移 368 cycles。这解释了整份 block 的差异。

## 4. 排队、资源竞争和容量

| 观测量 | Baseline | Rotated |
|---|---:|---:|
| 同时未完成消息的最大数量 | 1 | 1 |
| 累计消息首 flit 注入前等待，cycles | 0 | 0 |
| 累计 compute 请求排队，cycles | 1,408 | 1,408 |
| 累计 memory 请求排队，cycles | 2,816 | 2,816 |
| 容量 admission 等待，cycles | 0 | 0 |
| worker 0 / 1 峰值内存，bytes | 87,040 / 82,944 | 87,040 / 82,944 |

本例没有不同消息同时争用网络，不能据此声称 Rotated 缓解或加重拥塞。单个消息
内部仍有 flit 流水和仲裁开销，不能把“首 flit 注入等待为零”写成所有 router 排队
为零。compute 和 memory 的请求等待确实存在，但两边累计值相同；这些等待是重叠
观测量，不能再加到关键链总时间上。[归因数据](attribution.json)保留具体统计。

## 5. 简化模型与资源成本

保留的整消息 store-and-forward 模型也在同一资源图上执行同一 block：

| 后端 | Baseline，cycles | Rotated，cycles | R − B |
|---|---:|---:|---:|
| 在线 BookSim | 13,062 | 13,430 | 368 |
| 整消息简化模型 | 13,098 | 13,502 | 404 |

该简化模型在本例保留了排序，但分别多估 36/72 cycles。它与 BookSim 在路由、
序列化和队列粒度上都有区别，不能用这组差值单独归因于 contention，也不是旧
M0/M1 工作负载的 Mstatic 实验。

| 资源 | Baseline | Rotated |
|---|---:|---:|
| compute endpoints / 活跃端点 | 20 / 2 | 20 / 2 |
| routers | 124 | 100 |
| 无向 links | 232 | 226 |
| 全图有向链路带宽总和，bits/cycle | 7,424,000 | 7,232,000 |
| 每链路带宽，bits/cycle | 16,000 | 16,000 |
| VC 数 / 每 VC buffer flits | 1 / 32 | 1 / 32 |

物理成本没有匹配；全图带宽求和也不等于端点对或 cut 的可用带宽。

## 6. 验收与复现

- 正式运行前，102 项语义／接口测试通过；新增报告入口后，同一组测试再次通过。
  [初始 receipt](validation-initial/SEMANTICS.json)与
  [报告版本 receipt](validation-reporting/SEMANTICS.json)分别记录源码、环境和日志哈希。
- 单流、共享链路竞争、有限 credit、空闲跨越、全 flit 完成、目标写入以及消费者
  依赖均有验证；原 113-cycle 例子的完整事件记录保持一致。
- 每边全部 30 个操作、102 个 phase、118 个本地资源服务及 12 flits 完成，
  独立回读检查工作量、服务率、路径、依赖、容量和最终驻留。
- 每边在线执行结束后，才将**已观察到**的消息就绪时间交给原独立 BookSim 检查。
  就绪、生成、首尾注入、首尾接收时刻逐项一致。这是接口验证，不是应用的驱动方式。
- 原独立内核仍为已收口的 CSR 版本，二进制 SHA-256 为 `fbd6fca…`；桥接二进制为
  `d37fc55…`。[STARTED.json](STARTED.json)记录完整哈希、编译器和环境，
  [build-binaries.sha256](build-binaries.sha256)记录链接对象。没有另写网络内核或更改
  既有 native patch。
- 接收记录保存在 [Baseline](baseline/online_network.json)与
  [Rotated](ours_rotated/online_network.json)。[COMPLETE.json](COMPLETE.json)记录远端
  47 个运行产物的哈希；只读归因重新核对了全部产物。

完整图、执行事件和日志保留在：

```
/home/wangziheng/wafer_simulator/runs/transformer-wow-001
/home/wangziheng/wafer_simulator/runs/transformer-wow-attribution-001
/home/wangziheng/wafer_simulator/runs/wow-transformer-semantics-001
/home/wangziheng/wafer_simulator/runs/wow-transformer-semantics-002
```

仓库保存紧凑报告、原始汇总、关键链、路径和逐操作配对，以及身份／哈希。
复现命令和层级职责见[实验协议](../../TRANSFORMER_WOW_PROTOCOL.md)。

这一步已完成“同一完整 block 在两套 WoW 资源上由目标服务决定时间”的交付。
它不承担原生 wafer 计算性能标定、完整 Llama 性能、等成本 topology 排名或拥塞
优劣的结论。下一项若研究竞争，应单独登记更多参与者的并发 collective，保留本例
作为已验收的路径成本基线。
