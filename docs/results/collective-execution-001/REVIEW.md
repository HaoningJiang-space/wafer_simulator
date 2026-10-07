# Collective action 计时修正与首组并发 WoW 对照

已在 eex005 完成 AllReduce lowering 修正、action DAG 执行、TP2 重验，以及
预先登记的 TP4／TP8 × 两种 placement × 两种映射，共八个完整 block 案例。
正式执行版本为 `916a982`；只读归因版本为 `a5c1b09`。没有新增网络内核，原
BookSim 二进制及 patch 未变，也没有回到旧 capture 恢复或启动完整 Llama。

## 1. 确认并修复的问题

旧 Transformer 把 AllReduce 声明成普通多输出操作，通用 binder 先在 root
写出两个结果副本，再把其中一个传出。因此每个 TP2 AllReduce 多写 4,096 bytes，
并多保留一个 root 输出 staging allocation。

现在 logical operation 显式携带 collective 身份、参与者、数据量和 SUM 工作量。
`adapters/collective_operation.py` 直接复用 `adapters/collectives.py` 的 action 模型：

```
各参与者读取 → 独立 gather → root 接收写入及操作数读取
              → SUM → root 写一个结果
              → 各 broadcast 读取与传输 → 目的端写入
```

`OperationPlan` 保存 action 依赖。所有就绪 action 使用同一 ResourceCalendar
或在线 BookSim；普通操作继续按顺序执行。没有给每条 action 单独制造内存带宽。

全体参与者输入就绪且 output/staging 容量原子保留后，collective 才进入执行。
全部 action（包括所有目的端写入）完成后，才发布输出、释放输入与临时存储，
允许后续 Transformer 操作开始。这个全局完成策略保持不变；没有同时引入
rank-local 提前进入、streaming reduction 或新的 collective 算法。

root 的广播读取按参与者顺序共享端口，每个目的端重新读取一次结果。这是保留的
direct 算法选择，不是 multicast 或缓存复用。独立 action 可以并发，不等于它们
在争用同一内存端口时也会同时获得服务。

## 2. TP2：把纠错与并发的影响分开

保持原来的四个 heads、两个 shards、完整工作、row-major 映射和服务参数：

| 模式 | Baseline，cycles | Rotated，cycles | R − B |
|---|---:|---:|---:|
| 原通用 lowering（历史结果） | 13,062 | 13,430 | 368 |
| 修正 materialization，action 串行控制 | 12,806 | 13,174 | 368 |
| 修正 materialization，按依赖并发 | **12,550** | **12,918** | **368** |

两种新模式使用同一份 action、分配及逻辑工作，只在串行控制中补上拓扑顺序依赖。
这两个新模式不是不同的 BookSim 实现。

每个 AllReduce 的 root memory write 从 12,288 降为 8,192 bytes：后者包括
4,096-byte gather staging 和一次 4,096-byte 结果写入。所有区域的写入总量从
16,384 降为 12,288 bytes。两次 collective 共去掉 8,192 bytes，即
`8192 / 32 = 256 cycles` 的实际服务量。

并发模式再将 root 自己的 128-cycle 操作数读取与远端源读取重叠。每次省下
128 cycles，两次再减少 256 cycles。没有删除这项读取，其字节数和资源服务记录
仍在。两边单条消息的网络服务依然为 72／164 cycles，所以 placement 差值不变。

| 每次 AllReduce 耗时 | Baseline | Rotated |
|---|---:|---:|
| 历史通用 lowering | 1,232 | 1,416 |
| 修正后的串行 action | 1,104 | 1,288 |
| action DAG | 976 | 1,160 |

修正后两条应用关键链均为 6,406 cycles 计算和 5,856 cycles 内存；网络分别为
288／656 cycles，精确相加得到 12,550／12,918。
原报告保留，并添加了模型修正说明；原 JSON、输入和哈希没有改写。

验收数据：[action 模式](tp2-actions/SUMMARY.json)、
[串行控制](tp2-serial/SUMMARY.json)。这替代了旧绝对时间，不表示已标定原生 wafer。

## 3. 并发实验的固定条件

原 block 只有 4 heads，完整 head 分片不能直接支持 TP8。为此，
[登记配置](../../../configs/transformer_collective_study.json)明确使用一个独立的
**8-head block**；batch 1、sequence 16、hidden 64、FFN 128 和服务率保持原设定。
TP4 与 TP8 各比较两套 WoW、两种固定规则：

- `row_major`：按 `(layer,y,x)` 选取端点。
- `nearest_root`：root 仍是第一个 row-major 端点，其余按到 root 的平面距离平方
  排序，平局按坐标和端点 ID。没有使用仿真结果搜索映射。

每个 TP 内四个案例的完整逻辑工作哈希一致。TP4／TP8 分别为 58／114 个操作，
108／216 个数据对象，两次 AllReduce。总矩阵工作均为 557,056 MAC；跨 TP 时
复制的 normalization 和 reduction 等工作量不同，不能宣称总工作完全相等。

计算与内存仍为共同分析参数：64 MAC/cycle、显式 scalar rates、每区域
256 KiB、32 B/cycle 共享读写端口。网络保留作者 1 GHz、16,000 bits/cycle、
4-cycle router、1 VC、32-flit buffer、adaptive routing 和 seed 1。资源成本
没有匹配：Baseline 为 124 routers／232 links，Rotated 为 100／226，均有 20
个 compute endpoints。只有 TP 所需端点活跃。

## 4. 完整执行结果

| TP | 映射 | Baseline，cycles | Rotated，cycles | R − B |
|---|---|---:|---:|---:|
| 4 | row-major | 11,026 | 11,022 | −4 |
| 4 | nearest-root | 10,816 | 10,834 | +18 |
| 8 | row-major | 12,534 | 12,452 | −82 |
| 8 | nearest-root | 12,538 | 12,572 | +34 |

在当前确定性模型和 seed 下，映射确实改变了 placement 排序。但差异只有
4–82 cycles，不能据此宣布某一种 topology 普遍更好，也不是性能显著性的统计检验。

每次 AllReduce 的时间分别为：

| TP / 映射 | Baseline | Rotated |
|---|---:|---:|
| 4 / row-major | 1,990 | 1,988 |
| 4 / nearest-root | 1,885 | 1,894 |
| 8 / row-major | 3,727 | 3,686 |
| 8 / nearest-root | 3,729 | 3,746 |

一个案例中的两次 collective 时间相同，它们的差异合计为该案例的最终应用差异。
完整结果与身份见 [study/SUMMARY.json](study/SUMMARY.json)，紧凑比较见
[comparison.csv](attribution/comparison.csv)。

## 5. 网络并发是真实发生的，但当前拥塞影响有限

TP4／TP8 分别有 3／7 条 gather 同时未完成；每边完整执行分别包含
12／28 条消息、36／84 flits。所有原生完成时刻与独立 BookSim 一致。多条请求
确实进入同一个网络并共享链路、router 和接收资源，未预先把它们串行化。

首 flit 注入等待在八个案例中仍均为零。沿**实际路径**扣除链路通道和已配置
router pipeline 后，各消息首注入 flit 的额外 router 驻留总量为：

| TP / 映射 | Baseline，cycles | Rotated，cycles |
|---|---:|---:|
| 4 / row-major | 0 | 2 |
| 4 / nearest-root | 6 | 0 |
| 8 / row-major | 6 | 14 |
| 8 / nearest-root | 18 | 16 |

这些是观测驻留量，可能包括仲裁及 credit 等效果；不是一个“去掉竞争”的反事实，
也不是完整网络延迟的可加因果分解。共享链路流量汇总还包含先后使用同一路径的
消息，不能把共享本身等同于拥塞。本例载荷只有 3 flits／消息，测到了部分额外
驻留，但尚不能宣称网络拥塞主导应用。

更显著的资源现象在本地端口：请求累计内存排队在 TP4 约 6,900–7,300 cycles，
TP8 约 27,700–28,300 cycles。这些跨请求等待有重叠，不能直接加到 makespan。
TP8 的选定关键链有 9,040 cycles 内存服务、3,080 cycles 计算，网络只有
332–452 cycles。这个分解描述观测链，不代替带宽干预。

## 6. 为什么平均消息变快，应用却没有变快

TP8 给出一个可具体解释的案例：

| Placement | row-major 消息均值 | nearest-root 消息均值 | 应用时间变化 |
|---|---:|---:|---:|
| Baseline | 133.357 cycles | 109.929 cycles | +4 cycles |
| Rotated | 123.500 cycles | 110.786 cycles | +120 cycles |

平均实际 inter-router links 也下降：Baseline 从 6 降到 4.714，Rotated 从
4.143 降到 3.571。但 root 的广播读取依次争用同一个 32 B/cycle 端口，4,096-byte
结果的每次读取占 128 cycles。较早消息的改善不一定缩短最后一项必需的完成事件。

以第一次 AllReduce 为例，四种 TP8 情况下：

1. collective 在 2,179 cycles 就绪，首个 gather 都在 2,383 完成。
2. root 的接收写入与操作数读取占用同一端口；SUM 都在 4,175 开始、4,623 结束。
3. 最后一条给逻辑 rank 7 的 broadcast 都在 5,647 就绪。
4. 该消息在 Baseline 的 row-major／nearest-root 中分别用 131／133 cycles；
   Rotated 中分别用 90／150 cycles。

因此每次 AllReduce 分别增加 2／60 cycles；两次合计恰好是应用的 +4／+120。
改善发生在其他消息上的平均收益被隐藏在已有的端口服务与依赖等待中，而最后
broadcast 的路径代价仍直接决定结束。各案例的关键 action 和真实路径都在
[attribution 目录](attribution/)的 JSON 中。

这里能支持的架构解释是：**映射改变了数据路径，也改变了哪项通信处在共享端口
服务之后的关键位置；平均 hop 或平均消息时间不足以预测完成时间。**这一现象
还依赖当前 root-gather 和按参与者顺序读取广播的策略，不应推广为所有 collective
算法或最优 mapping 的结论。

整消息简化模型保留了这八个案例的排序，较 BookSim 多估 28–72 cycles。
它们有不同路由和序列化规则，这仍不是隔离 contention 的消融结果。

## 7. 验收与交付

- 正式实验前 [112 项语义／接口测试](validation/SEMANTICS.json)通过，包括完整
  TP8 分片的数值等价、手算 collective、并发 gather、容量不足、提前完成和原生
  credit/共享链路案例；原 113-cycle 普通操作回归记录未变。
- 新增归因与错误工作量检查随 [9 项定向回归](report-validation/VALIDATION.json)
  通过。其中 7 项与前述套件重复，不把它们算成 121 项不同测试。
- TP2 action、TP2 serial 和八个 study arm 共十二个正式执行均通过完整操作、
  数据、服务率、依赖、容量、最终驻留及全部 flits 的独立回读。
- 每个执行结束后，观察到的消息就绪表才用于独立 BookSim 接口核对；ready、
  generation、首尾注入与首尾接收全部匹配。它不驱动应用执行。
- 三份 [COMPLETE](tp2-actions/COMPLETE.json)、[COMPLETE](tp2-serial/COMPLETE.json)、
  [COMPLETE](study/COMPLETE.json)保留全部运行产物哈希；只读归因再次逐文件核对。
  源码、输入、二进制、编译器和环境身份在各目录的 STARTED／CONFIG 中。

原始输入、完整图、服务事件和 BookSim 日志均留在 eex005：

```
/home/wangziheng/wafer_simulator/runs/transformer-wow-actions-002
/home/wangziheng/wafer_simulator/runs/transformer-wow-actions-serial-001
/home/wangziheng/wafer_simulator/runs/transformer-collective-study-001
/home/wangziheng/wafer_simulator/runs/transformer-collective-attribution-002
```

代码、登记协议与紧凑证据都在同一个 wafer_simulator 仓库。
下一项有依据的诊断是隔离 root memory 服务或 broadcast 策略的影响；本轮不继续
增加 mapping、拓扑、thermal 或输入恢复范围。
