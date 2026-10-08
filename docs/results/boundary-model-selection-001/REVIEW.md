# 存储—网络边界：按预测目标选择模型

2026-10-08，eex005。本次只回读已接受的完整执行，没有启动新仿真。
**当前证据支持把存储服务政策、消息提交和接收容量分别建模；不支持声称有限
RX 反馈已经改善这两份应用的总时间预测。**模型选择必须先明确要预测哪个量。

本轮新增解释是：反馈改变了 gather 消息及部分 root 读取时序，但差异在归约的
输入汇合处消失。两套内存政策、两份工作中，全部 114 个操作记录及全部输出
就绪记录分别相同。不能从相同 makespan 推出边界内部也准确。

## 参数来源与目标范围

限定 Baseline、row-major、TP8、direct-root、完整 s16/s64 analytical Transformer
forward，沿用原 BookSim 配置、二进制、seed 和资源预算。WoW 作者实现固定在
`9470042fb2d8b5368556e46cc75ac818dbf31522`。

| 参数或行为 | 来源 | 能支持的结论 |
|---|---|---|
| overlap 连接、几何路径、unit-to-router latency | pinned 几何导出及 [WoW adapter](../../../src/wafer_sim/adapters/wow_target.py) | 同一作者网络实现；trace 模式每 compute reticle 一个 endpoint，含固定访问时延 |
| 16 Tb/s/link、1 GHz、2000 B/flit、一 flit/cycle | 作者 [config.py](../../../third_party/nw-design-for-wsi/config.py) 及单位换算 | 可追溯的模型参数；作者也将时钟等列为 assumption，不等于实测硬件 |
| router 4 cycles、传播 2 mm/cycle、1 VC、32-flit VC buffer | 同一作者配置 | 原生网络内部行为；VC buffer 不等于我们的 8-slot 接收 FIFO |
| 64 MAC/cycle、其他算子服务率、256 KiB/region、共享读写 32 B/cycle | [analytical target](../../../configs/transformer_block.json) | 本项目声明的本地资源，未标定为原生 WoW 的 GPC/SRAM |
| 2 TX/8 RX slots、每槽 2000 B、从原 SRAM 扣除 20,000 B | [边界合同](../../../configs/memory_network_boundary.json) | 同预算的 streaming-DMA 假设，不是作者硬件提供的槽数 |
| request_atomic / 256 B FCFS burst、完整对象写完才可见 | [内存服务合同](../../MEMORY_SERVICE_ISOLATION.md) | 两种目标服务政策；256 B 不由 2000 B flit 推导，也不是推荐硬件值 |

`transformer_block.json` 原手写网络的 16/32 B/cycle 不能当成此次 WoW 链路参数；
adapter 使用实际导出的网络。`compute_memory_calibrated=False` 与
`physical_cost_matched=False` 仍有效。这里验证的是**同一声明机器下的模拟抽象**；
跨内存政策改变的是目标服务合同，不能混称为模型误差。现有来源也不能证明必须
显式模拟 8 个 GPC 的 local NoC。

## 分开验收应用、消息和容量

同一内存合同内以 bounded 为边界参考。预登记门槛仍是：应用同时满足 ≤2% 与
≤100 cycles；每条消息同时满足 ≤5% 与 ≤20 cycles；容量另行检查。
bounded 对自身的零误差不算独立硬件验证。

| 工作 / 内存政策 | serial 应用误差，绝对 cycles / 百分比 | pipeline 应用误差 | pipeline 最大消息服务误差 | pipeline RX 峰值 / 预算 |
|---|---:|---:|---:|---:|
| s16 / request_atomic | 1,049 / 7.723% | 0 | 384 cycles | 18 / 8 |
| s64 / request_atomic | 3,978 / 7.111% | 0 | 1,536 cycles | 60 / 8 |
| s16 / burst_256 | 253 / 1.883% | 0 | 265 cycles | 16 / 8 |
| s64 / burst_256 | 1,355 / 2.440% | 0 | 616 cycles | 63 / 8 |

serial 四格均未通过应用门槛，s16/burst 不能只看百分比。pipeline 四格的应用
预测通过，但消息和容量均不通过。serial 没有建模 FIFO 占用，容量结论是未知，
不能把缺少状态视作通过。峰值按 endpoint 槽计，非 wafer 总量。
[12 格逐目标结果](analysis/prediction_objectives.csv)

| 模型 | 当前可保留的用途 | 当前不能承担的判断 |
|---|---|---|
| serial | 兼容基线；目标若明确整消息串行，可使用相应合同 | 代替本轮 streaming-DMA 参考并声称通过已登记应用精度 |
| pipeline，立即返还接收 credit | 本轮四格中仅预测 makespan 的近似 | 有限 RX 可行性、准确消息提交；推广到其他依赖和参数 |
| bounded，写完才释放接收槽/credit | 本声明合同的消息、容量及执行参考 | 原生 wafer ground truth；所有场景都需要此粒度的证明 |

保留三个可选模型和现有默认配置，不新增自动选择器，也不依据两份工作删除旧
实现。消息提交需要读出/在途/写入进度，容量需要 TX/RX 占用与释放；当前
whole-object 依赖只在完整写入后发布。这是所测试模型的取舍，尚不是全局最小
状态的证明。

## 反馈差异在哪里消失？

本轮从现有 phase DAG 读取归约的真实前驱，再检查逐项 memory-read 完成、
compute ready/start/finish 及其后继，未按固定 phase 编号猜测关键点。
每个工作有 28 条搬运；pipeline→bounded 改变的完整提交数依次为 8、14、14、14。

| 工作 / 内存政策 | attention 最后输入读取完成，P / B | FFN 最后输入读取完成，P / B | 每次归约中改变完成时间的输入读取数 |
|---|---:|---:|---:|
| s16 / request_atomic | 4,109 / 4,109 | 11,077 / 11,077 | 3 / 8 |
| s64 / request_atomic | 20,216 / 20,216 | 46,504 / 46,504 | 3 / 8 |
| s16 / burst_256 | 4,349 / 4,349 | 10,932 / 10,932 | 6 / 8 |
| s64 / burst_256 | 21,224 / 21,224 | 46,101 / 46,101 | 7 / 8 |

P 为 pipeline，B 为 bounded。八个归约的最后输入读取、compute ready/start/finish
都一致；归约及其后继 phase 记录也全部一致。例如 s16/burst 的某个 gather
于 3,326/3,061 cycles 提交，其 root reduce-read 于 4,253/4,061 完成；但归约
仍等到 4,349 才能开始。个别消息也可能在 bounded 下更晚完成，不能把反馈写成
统一附加延迟。

这里保留的是归约的真实数据依赖，不是重新给所有 rank 加全局完成屏障。
root-memory 服务顺序改变了中间时序，但此次依赖汇合的最大完成时刻不变，
差异没有传到后续输出。这是事件级观测解释，不是对任意 workload 的误差上界。

[四组完整记录比较](analysis/feedback_pairs.csv)、
[八个归约汇合点](analysis/reduction_joins.csv)、
[64 条输入读取对照](analysis/operand_reads.csv)

## 成本与模型精度分别记账

[原 36 次同版本实验](../memory-service-isolation-001/REVIEW.md)提供三个模型的
同合同成本。后来[准入检查优化](../memory-execution-cost-001/REVIEW.md)在
burst_256 + bounded 下把 s16/s64 的执行中位数降为 0.576/1.521 s，完整事件和
原生命令一致；这个实现优化已收口。

不能拿优化后的 bounded 与优化前 serial/pipeline 拼成新排行榜，也不能把跨
内存政策的成本变化称为同目标近似算法加速。本次没有新计时。若将来需要最新
版本三个模型的成本比较，应使用同版本、同日志策略的配对测量。

## 当前决定及剩余研究问题

可成立的发现是：**相同字节量、带宽和应用总时间，不足以确定消息时序与容量
可行性；memory 服务政策与边界反馈必须按预测目标分别评估。**它不是“详细
模型对所有 wafer 应用必不可少”的证明。本轮也没有新增 Rotated 结果，不能
据此宣称 placement 排名已被修正。

本阶段停止增加运行时优化、collective、mapping 或 GPC 细节。下一项尚未建立
的证据是：**边界误差何时会越过依赖汇合点，改变关键数据可用时间及应用预测？**
先由明确目标合同与合法工作需求给出条件，再选择一个受控对照；不能为了出现
差异删除归约依赖、无限提高供数率或增加免费缓冲。

若目标只是当前四格的 makespan，pipeline 已足够，无需为此继续加模型。
若目标是消息或有限容量判断，bounded 参考已有用途，继续保留。
若目标是原生 WoW 性能，还缺独立的 SRAM/DMA 服务与缓冲依据；增加模拟细节
不能代替参数证据。三种任务不再串成必须全部完成的一条前置链。

## 验证与复现

本次在 eex005 重新校验 **547 项源产物哈希、36 次既有执行的独立完成/存储/服务
审计**，复算的 12 格结果和政策交互与归档完全一致。新增分析覆盖四个反馈配对、
八个归约汇合点及 64 条输入读取。**新仿真 0、新 native replay 0，未重跑语义
测试。**模拟器、上游代码、配置和既有结果未改变。[本次回执](analysis/VALIDATION.json)

分析源码 `4f95af9`；模块在 `src/wafer_sim/analysis/boundary_selection.py`。
命令行只组织回读，不调用执行器。原始事件留在服务器。在 eex005 source checkout
执行，输出必须为新绝对目录：

```bash
PYTHONPATH=src /home/wangziheng/wafer_simulator/.venv/bin/python \
  scripts/summarize_boundary_models_remote.py \
  /home/wangziheng/wafer_simulator/runs/memory-service-isolation-001 \
  /home/wangziheng/wafer_simulator/runs/boundary-model-selection-NEW
```

本次输出为 `runs/boundary-model-selection-001`；仓库只收录紧凑分析和校验记录。
