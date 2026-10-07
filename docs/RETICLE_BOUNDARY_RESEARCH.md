# 研究对象：reticle 聚合资源抽象的适用范围

状态：原文和 pinned source 核对完成，原有 collective / placement 案例冻结。
本文第 1–6 节保留当时的研究边界；后续已完成网络流水和
[存储—网络边界对照](results/memory-boundary-001/REVIEW.md)。后者以明确的 streaming
DMA 设计假设为参考；没有实现显式 local NoC，也没有原生硬件标定或网络饱和结论。
已归档：[12 点只读模型误差](results/model-fidelity-saved-001/REVIEW.md)、
[端点与外部连接复核](results/reticle-boundary-audit-001/REVIEW.md)。

当前问题收紧为：**在明确的目标机器与工作范围内，aggregate compute / memory /
endpoint 模型能否以可接受的成本，预测应用完成时间与架构收益？如果不能，
误差来自参数、资源共享、执行政策，还是被省略的空间结构？**

精度—成本是验证这个问题的方法；它不再是一组脱离具体机制的后端规模 sweep。
不先认定所有 reticles 都必须逐 GPC、逐 flit 模拟，也不预设高 radix 收益消失。
本文件中已确认的“未建模”只是范围描述，不是必须实现的功能列表。有限边界 FIFO
与双向反馈需要按目标合同检验，不能因原代码没有它们就预定它们是主要误差来源。

## 1. 原文支持什么，不能过度推断什么

核对 [WoW v2](https://arxiv.org/html/2603.05266v2)：

- §3.1 定义 GPU-like compute reticle，含 8 GPC 和 local SRAM。
- §3.2 为独立研究 wafer 网络，将 compute reticle 内部网络合并为连接 GPC 和
  vertical connectors 的单 router；LoI 的 interconnect reticle 内部 routers/links
  仍显式建模。这里确实有一个明确的空间聚合边界。
- Table 1 的 200 mm rectangular LoI 中，compute-reticle 外部 radix 为 Baseline 4、
  Rotated 7；这个数不是连同 GPC 接入端口计算的完整 BookSim router radix。
- §5.1 的 router、buffer、credit 和带宽并非无限。不能把作者模型写成无端口竞争的
  ideal router；也不能从“内部网络聚合”直接推断作者分开运行两套仿真后相加延迟。

进一步，本地供数不足不意味着额外邻居必定无用。更多连接仍可能减少路径、缓解
其他流的争用或服务过境流量。供数约束与实际流量投影须共同计量。

## 2. Author source 中必须保留的区别

Pinned upstream `9470042fb2d8b5368556e46cc75ac818dbf31522`，来源位于
`third_party/nw-design-for-wsi`，本次未修改：

| 证据位置 | 实际行为 | 对研究的含义 |
|---|---|---|
| `config.py` | 8 GPC、1 GHz、2 TB/s/link、4-cycle router、1 VC、32 flits/VC | 都是作者网络配置/假设；SRAM 服务不能从 link width 反推 |
| `export_to_rapidchiplet.py:106–129` | Synthetic 每 compute reticle 有 8 units；`trace-*` 只有 1 unit；unit 到中心的平均几何距离给固定接入时延 | “单 router”与“单注入端口”不是同一件事；必须区分两种输入模式 |
| `rapidchiplet/booksim_wrapper.py:245–259` | 每个 unit 单独接 node；外部邻接连接另占 router ports | 原模型已拥有多输入端口及内部 router 竞争 |
| `rapidchiplet/booksim2/src/trafficmanager.cpp` | 注入受 buffer/credit 限制；收到 flit 后返回 credit 并 retire | 网络内有双向反压；接收与目标 SRAM 写服务未连接 |

## 3. 原整消息模型的范围（保留为比较基线）

当前 `adapters/wow.py` 用 `trace-llama7B` 导出，即使随后运行的是 analytical
Transformer，也仍是 **每 compute reticle 一个网络 endpoint**。
`wow_target.py` 在这个 endpoint 上绑定一个 compute 资源和一个共享读写 memory。

| 层次 | 已有 | 未有 |
|---|---|---|
| Local compute / memory | 显式工作量、单资源服务率、逐区域容量及生命周期 | 8 GPC 分布、SRAM banks 与内部互连拓扑/端口共享 |
| 源供数 | 完整 memory read 后才提交 transfer；已有 memory 带宽限制 | 按有限边界 FIFO 供数；下游 credit 能停住尚未完成的 SRAM 读取 |
| 网络 | 一 endpoint 一 flit/cycle；WoW router/link/VC/credit | 当前 adapter 中的 GPC-level source identity 和局部 NoC |
| 目的接收 | 网络全 flit 到齐后执行 memory write，完成写入才发布数据 | 目的 SRAM 写服务消耗接收 FIFO，并据空间释放控制返还 credit |

`collectives.deliver()` 与普通 operation 的 `move()` 都是先读、再网络、再写。
`OnlineBookSim` 只接受完整消息和返回全消息接收完成；原生 `_Step()` 不询问
Python 侧 SRAM 状态。现有全对象 staging/reservation 不是免费存储，必须保留；
但预留足够容量不等于模拟了接收 FIFO 与写端口逐周期的相互限制。

因此当前模型不能称作“没有 memory”，也不能称作“已闭合 SRAM—network credit
反馈”。缺的是边界服务的耦合粒度与状态。这是一个需要检验的模型边界，尚非证明
作者架构排名错误的结果。

当前每 endpoint 2000 B/cycle 的注入上限，在 1 GHz 下为 2 TB/s。这个上限约束
该 endpoint 的本地产生流量，不是整个 reticle 上包括 transit 的总流量。不得直接
以外部 degree × link width 作为每个 GPC 可获得的带宽。

## 4. 先区分参数不确定、抽象误差和架构变化

| 问题 | 所需参考 | 不能混称为 |
|---|---|---|
| Compute / SRAM 服务参数是否正确 | 对同一操作/访问模式的目标表征、独立组件参考；缺失时为明确假设与范围 | 改一个 bandwidth 后时间变化，不是已经测得模型误差 |
| 单共享资源是否遗漏必要行为 | 同一机器、工作、初态和预算下，包含该行为的独立参考 | 给细模型增加端口/带宽后变快，不是聚合模型不准确 |
| 架构是否提供了不同能力 | 两台各自定义清楚的机器及其物理预算 | 1 endpoint 改 8 endpoints 不是自动等价的精度细化 |

现有 coarse 与 BookSim 共用 aggregate compute/memory，因此它们互相接近，只能
支持共同合同下的网络后端比较，不能验证共同使用的本地抽象。
显式 NoC 也不会因“更细”自动成为正确参考：内部拓扑、仲裁、存储服务和执行政策
必须有来源或明确假设。没有这样的参考时，结果只能叫假设敏感性，不能叫准确率。

### 有参考依据后，才构造相同机器的模型对照

| 角色 | 定义 | 能证明什么 |
|---|---|---|
| A0：作者网络抽象 | 原始 central-router、原始 unit 数与接入参数 | 与论文边界对应的网络基线；不是无限供数，也不是未经改动的真实芯片模型 |
| A1：聚合局部资源 | 同一局部资源预算，聚合供数/接收服务、显式延迟；有限队列是否需要由对照决定 | 简单边界模型是否已经足够；不是只把两个总 duration 相加 |
| R：独立参考 | 对所检验机制有支撑的组件模型、服务记录或详细仿真；只展开必要资源 | 对该参考覆盖范围的精度证据；不要求先建设完整 8-GPC NoC |

A1 必须从 R 的同一个物理资源合同推导，而非任意设置一个慢 memory 来压低
Rotated 收益。不能给 R 更多 GPC、更多供数通道或不同内存总带宽后，将差值解释成
“聚合误差”。A0 与 R 若硬件预算不同，只能解释模型范围和资源假设的敏感性。

**空间聚合和时间耦合是两个不同变量。** 对比单 router 与多 router 不能单独证明
“分开模拟会错”。检验耦合时，固定局部图和服务，仅对照离线/单向响应与在线有限
队列反馈；检验聚合时，固定耦合及端口预算，再比较 A1 与 R。先做一轴，不同时改
路由、tiling、compute rate、memory policy 和 collective algorithm。

## 5. 下一项交付：一个有参考的误差定位对照

不把输入缺数据重新变成 capture recovery 项目，也不同时实现下表所有候选。
先选择有参考证据、能保持同机同工作且影响目标判断的一项：

| 候选假设 | 有效的检验条件 | 误差成立后才考虑的改动 |
|---|---|---|
| 固定 compute service rate 不足 | 同操作、工作量/形状与目标资源的独立服务结果 | 更合适的操作服务模型；不必增加 GPC 节点 |
| 共享 SRAM 服务过度聚合 | 已知 read/write/bank 共享规则，比较同预算的合法请求 | 校正共享端口或 bank 服务，而非先建完整 local NoC |
| Endpoint 总供数/接收能力假设不符 | 明确端口数、总带宽、接入延迟和访问来源 | 校正聚合服务合同；与 1→8 端口扩容区分 |
| 阶段串行或边界反馈遗漏有影响 | 目标允许的 overlap、有限接收能力/credit 规则有依据 | 必要的流水阶段或有限队列反馈 |
| 内部空间争用不能被聚合保留 | 相同 GPC 工作与资源预算，已知位置/路径形成不同冲突 | 只展开决定冲突的 local NoC 资源 |

为选中的一项形成一张实验卡：目标问题和允许误差、参考来源/适用范围、完整逻辑
工作身份、参数与初态、唯一改变的抽象、观测量与成本计量，以及判定标准。先登记
这些，再运行；不按已经看到的收益设置阈值。没有参考的字段保持未知或设计假设，
不靠调参制造失效。若简单模型已经足够，结论中明确保留它。

评价至少同时包含应用时间误差和设计收益差距误差；临近相消时报告绝对 cycles，
不只看 gap 百分比。成本分别计图构建、初始化、执行、日志、独立审计，避免把少
记录日志当成仿真方法收益。小型机制检查不替代完整声明 workload 的应用结果。

只有选中空间/边界机制时才需要 `(reticle, gpc/bank/port)` 身份、FIFO/credit 事件
和相关 BookSim 扩展。仍必须防止八倍复制原工作、双计旧接入 latency 或免费扩容。
现阶段不以完成 unified hierarchical simulator 为预设交付物。

## 6. 验证和停止条件

必须同时报告：完整任务时间误差、相关工作/资源服务与关键链，以及执行 wall/CPU/
内存成本。只有检验边界机制时才要求注入/接收率、FIFO 占用和 stall 等相关观测。
供数限制与真正 network saturation 用观测区分。方法比较固定机器和工作，之后
才用 Baseline/Rotated 验证该误差是否影响设计收益预测。

前一轮 coarse/BookSim 的 12 个点已只读复算：应用 MAPE 1.470193%，最大 3.276723%，
六组 placement 排名一致；tree/1024 的 gap 分别为 −308/−548 cycles。它们说明
现有小案例尚不能证明 fine network 必需，不是对 reticle 内部聚合的验证。

如果 A1 保留目标精度，就把它作为主要模型；若仅需接收 FIFO，不重建整个 GPC
微架构。若需要空间 NoC，则给出 A1 的具体失败、R 中起作用的状态和最小修补的
精度—成本结果。“更复杂”“排序反转”或“两个层次连起来”本身均不是验收标准。

## 本轮状态

- 已完成[同路径整消息服务对照](results/transfer-granularity-001/REVIEW.md)：两种
  完整声明工作、24次完整执行、28条孤立传输，全部在eex005检查；旧结果不改写。
- 应用误差0.367%/0.204%，孤立服务最大误差15%/42.857%。本轮服务参考覆盖的是
  endpoint—WoW网络，发现的是整消息逐跳服务与分片流水差异，不是本地聚合失效。
- 本地GPC/SRAM没有独立参考，不能借用网络对照验证。当前应用目标下保留粗模型；
  更精确的消息预测需要检验流水服务，而非立即添加local NoC或FIFO。
- `MODEL_FIDELITY_PROTOCOL.md` 的通用六条件 sweep仍延后；新实验的固定卡为
  `TRANSFER_GRANULARITY_PROTOCOL.md`，没有新增算法、mapping、thermal或capture恢复。
- [最小流水修正](results/packet-pipeline-001/REVIEW.md)已完成同工作三后端对照。
  候选在当前两例的应用APE为0%/0.0154%，孤立服务全部对齐，应用内最大消息
  误差3.5714%；剩余差异定位到共享输出的消息服务顺序。未改变默认后端，
  不以此验证本地聚合，也不继续为了逐事件对齐增加模型。
- [存储—网络边界对照](results/memory-boundary-001/REVIEW.md)已固定 BookSim 完成。
  同预算 streaming DMA 假设下，whole-message 对 s16/s64 应用时间低估
  7.723%/7.111%；原因涉及 memory 请求粒度及 rank-local 服务交错，不能只称作
  overlap 差异。简单分片恢复两例 makespan，但 RX 峰值 18/60 槽超过规定 8 槽，
  且消息提交误差超过预登记目标。可选有限端点反馈保留必要占用状态；这些结果
  不证明所有 workload 的应用时间需要 finite FIFO，也不启动完整 8-GPC NoC。
