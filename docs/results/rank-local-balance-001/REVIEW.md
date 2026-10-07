# Rank-local collective 与单维 memory balance：完成验收

本阶段完成 output-ready / operation-retired 分离，并在 eex005 完成
8 个 global 控制臂、8 个 rank-local 臂和 12 个带宽臂。没有新增 workload。
119 项语义及原生网络接口测试通过；28 个新臂的双后端记录重新通过独立审计；
含历史参考在内的 840 项产物哈希一致。原生 BookSim 二进制未改。

**主要结果：rank-local 确实提前推进局部工作，但原有八个案例的总完成时间不变。
改变内存带宽后，placement 差距先缩小再扩大；高带宽区间是计算主导且对网络更敏感，
不是已证实的网络带宽瓶颈。**

## 1. 语义修正和生命周期

- 逻辑 AllReduce 只声明 SUM、参与者、输入/输出和数据量。`ExecutionPolicy`
  单独选择已有 direct-root algorithm 及 `rank_local` / `global_retirement`
  完成策略。此阶段没有加入第二种算法。
- 每个输出在自己的最终目标写入完成后发布；消费者的数据依赖跟随该事件。
  显式 `control_deps` 仍然等待被依赖操作退役。
- 所有 action 结束才退役。输入、staging 和 producer 自己的输出 reservation
  至少保留到退役；输出还必须等待所有消费者结束。这保证 root 的结果在消费者
  提前完成后仍可供尚未结束的 broadcast 读取，没有提前释放或重复释放。
- 入口仍要求所有输入到齐、整项操作原子分配空间；同周期 FCFS 与 action 提交顺序
  不变。没有引入 rank-local entry、流式 reduction 或普通输入的并发搬运。
- 应用完成仍要求所有操作退役，不能用第一个输出就绪代替完整执行。

新增测试覆盖早完成消费者、内部广播存活、显式控制依赖、提前发布/提前释放的
错误回读、非法策略和输出要求。113-cycle 普通操作参考的原始 service、phase、
admission、release 记录保持逐项一致，仅增加 output-ready/retired 记录。

## 2. 原 TP4/TP8 对照：局部推进变了，总时间未变

单位均为 cycles；每格的全局完成控制与 rank-local 结果相同。

| TP / mapping | Baseline | Rotated | Rotated − Baseline |
|---|---:|---:|---:|
| TP4 / row-major | 11,026 | 11,022 | −4 |
| TP4 / nearest-root | 10,816 | 10,834 | +18 |
| TP8 / row-major | 12,534 | 12,452 | −82 |
| TP8 / nearest-root | 12,538 | 12,572 | +34 |

新 global 控制与已验收历史版本的完整逻辑工作、映射、服务、phase、资源、操作时间、
终态和原生消息事件一致。rank-local 与新 global 的原生消息时间表也恰好相同；
普通后继操作已经提前，不能因此把两个执行过程称为完全等价。

以 TP8 row-major Baseline 的第一次 AllReduce 为例：

| rank | 输出写入完成 / 后继 admitted | 后继完成 | collective 退役 |
|---|---:|---:|---:|
| 0 | 4,751 | 6,095 | 5,906 |
| 1 | 5,079 | 5,527 | 5,906 |
| 7 | 5,906 | 6,354 | 5,906 |

7 个消费者在退役前开始服务，3 个已完成；输出就绪跨度为 1,155 cycles。
root 的消费者仍需与已提交的 broadcast reads 共享端口，所以 ready 不等于独占端口。
rank 7 最晚收到结果，其后继工作仍决定下一次 AllReduce 的全输入就绪时间；
第二次 AllReduce 后它又决定整个 block 的最终输出。TP4 的尾部是 rank 3。

因此，原有 mapping ordering 在这组案例中没有改变。全局完成是需要修正的模型限制，
但**当前“均值更好而应用更慢”的结果没有因为取消该限制而消失**。
不能将旧结果直接归因为人为 barrier，也不能由此说 barrier 在其他工作中无影响。

## 3. 单维 resource balance

固定八头 TP8、batch 1 / sequence 16 / hidden 64 / FFN 128、row-major、direct-root SUM、
rank-local、容量、计算服务率、网络时钟/参数、seed 1 和两个原作者 placements。
每个 memory region 的共享读写端口都采用相同带宽，只改变这一参数。
六个点都保留 114 operations、216 data objects、557,056 MAC、28 messages / 84 flits。
32 B/cycle 点逐事件复现对应 rank-local 臂。配置与资源比较确认没有第二项干预。

| 内存 B/cycle | Baseline cycles | Rotated cycles | B − R | Rotated 时间缩短 |
|---:|---:|---:|---:|---:|
| 32 | 12,534 | 12,452 | 82 | 0.6542% |
| 64 | 8,078 | 8,012 | 66 | 0.8170% |
| 128 | 5,940 | 5,920 | 20 | 0.3367% |
| 256 | 4,954 | 4,862 | 92 | 1.8571% |
| 512 | 4,597 | 4,401 | 196 | 4.2637% |
| 1024 | 4,461 | 4,225 | 236 | 5.2903% |

这些百分比为 `(Baseline − Rotated) / Baseline`，不是 simulator 墙钟加速。
64→128 的绝对和相对 gap 都缩小，因此“内存越快，topology 优势必然越大”不成立。

### 关键链怎样变化

下表为一条观测关键链上的 compute / memory / network 服务周期，三项相加为总时间。
它是完整计时记账，不是三个独立的因果贡献，也不是整个 wafer 的平均利用率。

| 内存 B/cycle | Baseline C / M / N | Rotated C / M / N |
|---:|---:|---:|
| 32 | 3,080 / 9,040 / 414 | 3,080 / 9,040 / 332 |
| 64 | 3,336 / 4,328 / 414 | 3,336 / 4,200 / 476 |
| 128 | 3,336 / 1,972 / 632 | 3,336 / 2,100 / 484 |
| 256 | 3,336 / 986 / 632 | 3,336 / 1,018 / 508 |
| 512 | 3,336 / 301 / 960 | 3,336 / 397 / 668 |
| 1024 | 3,336 / 153 / 972 | 3,336 / 193 / 696 |

**32–64 B/cycle：内存限制最明显。**32 时 Baseline 关键链 72.12% 为内存服务；
端口翻倍使完成时间减少 4,456 cycles。广播读按参与者顺序占用 root 端口，
32 时两种 placement 都由最后的 rank 7 输出决定尾部。

**128–256 B/cycle：计算成为关键链最大项，尾部转由路径和端口共同决定。**
从 128 起 Baseline 的输出尾部为 rank 4，Rotated 为 rank 6，不再必然是最后提交的 rank。
128 点的差距为 `−128 memory + 148 network = 20 cycles`：两条链经过不同的等待/
服务关系，使网络服务差异被内存服务差异部分抵消。总数学工作没有变化。

**512–1024 B/cycle：网络对应用差异更重要，但应用仍由计算占最大部分。**
Baseline 关键链中 network 从 32 时的 3.30% 增到 1024 时的 21.79%，memory 降到 3.43%；
compute 占 74.78%。在观测采样点上，gap 从 256 的 92 增到 512 的 196，再到 1024 的 236。
这定位了本次参数范围内差距扩大的区间，不意味着找到了普适连续阈值。

1024 点的两次 AllReduce 在关键链上各包含：

- Baseline：rank 4 gather 240 cycles；rank 4 broadcast 246 cycles。
- Rotated：rank 1 gather 173 cycles；rank 6 broadcast 175 cycles。

此时关键链网络差为 `972 − 696 = 276`，内存差为 `153 − 193 = −40`，
compute 相同，总差为 236 cycles。128/256 时仍是较早 gather 与 root 端口共同控制
归约启动；512 起更远的 gather 也进入关键链。**资源平衡改变了哪些消息关键，
而不是仅对原来的通信时间整体乘一个系数。**

所有点首 flit 注入等待仍为 0，最多 7 条同时未完成消息；首注入 flit 的 router
驻留超额总计到 1024 才从 Baseline/Rotated 的 6/14 上升至 90/98 cycles。
它包含仲裁/credit 等影响，不是独立的拥塞因果贡献。当前主要证据是路径代价和
关键链暴露增加，不能据此宣称网络饱和或网络带宽主导。粗粒度网络结果仅作为
已有对照保留，也不是“关闭 contention”的实验。

## 4. 可复现性与边界

- 执行和 119 测试的源码为 `c526aec`；图表前的独立回读源码为 `91e726d`。
  原生二进制、配置、Python 环境和全部输入/输出身份见各 `STARTED.json` / `COMPLETE.json`。
- [机器可读归因](analysis/SUMMARY.json)、[对照表](analysis/comparison.csv)、
  [独立验收](analysis/ANALYZED.json)、[测试记录](validation/SEMANTICS.json) 是本目录的主要证据。
- 原始 execution、原生路径/消息、完整链与 1.8 MB 的 `DETAILS.json` 均留在服务器：
  `/home/wangziheng/wafer_simulator/runs/{collective-global-control-001,collective-rank-local-001,collective-memory-balance-001,rank-local-balance-attribution-002}`。
  本地仅同步紧凑报告与清单，不下载 trace。未覆盖或修改历史实验。
- 初次测试 `rank-local-semantics-001` 的唯一失败来自旧参考整份 JSON 比较新增字段；
  增加兼容投影后，原始事件仍逐项比较并通过。初次后处理 `rank-local-balance-attribution-001`
  因 JSON 排序与 target tuple 服务顺序不同而拒绝；恢复原记录的服务顺序后通过。
  两份失败目录均未被标为验收结果，未因此重跑正式仿真。
- 结果限定于完整的分析型 forward block、固定小 tensor、单 seed、给定入口和算法策略。
  compute/SRAM 参数未标定；两个设计资源成本未匹配。它不是 Llama 训练时间、网络饱和证据或
  最佳 topology 的普适结论。

下一步可以选择一种结构不同的 collective algorithm，在同一 workload 和这些资源
控制下比较。无需先恢复缺失 Chakra 字段、扩 workload、扫 mapping 或加入 thermal。
