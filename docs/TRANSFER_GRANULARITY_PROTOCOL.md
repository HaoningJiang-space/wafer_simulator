# 实验卡：同路径的整消息聚合误差

登记后才运行；本轮只检验已有证据支持的一项机制，不复活通用六条件 sweep。
现有 direct/32/Baseline 有相同路径且 coarse queue=0 的消息，其网络服务仍偏大。
选择这项而非 GPC/SRAM 聚合的原因是：有 pinned 原生 reference；本地服务没有
独立标定。结果仅适用于 endpoint—WoW 网络服务，不能验证共用的 local 模型。

**问题。** 有限速率、相同接入/链路/router 延迟和路径下，逐跳整消息串行是否能
近似原生分片执行？误差有多少进入完整应用，模拟成本有什么差异？

**参考。** 不改 pinned author network/binaries，live BookSim + standalone
同注入时间戳回读验证。实际 flit 路径独立核对。它是该网络模型的参考，不是真实
wafer。Coarse 保留 FCFS 共享链路；不称无竞争模型。

**固定项。** Baseline、row-major、direct-root、TP8、eight heads、batch1、hidden64、
FFN128、seed1、1 GHz、2000 B/flit、原始 compute rates、256 KiB/region、32 B/cycle
共享 memory、rank-local 完成、整对象执行合同。只取 sequence16/64 两种完整定义
的输入：AllReduce 每条逻辑消息分别为4096/16384 B，字节来自 tensor shape。
两后端每个条件使用完全相同输入、初态、binding、资源预算。容量不足报告不可行，
不改小工作或扩大 SRAM。固定算法不比较优劣；不改 mapping、注入带宽、路由或内核。

**第一层：独立服务定位。** 从完整 binding 提取每一组唯一的
`(source,destination,bytes)`，使用新建且空闲的原生网络完成整条传输，credit
排空后关闭。全部源依赖仍由完整应用运行验证；孤立调用只是组件表征，不冒充
第二份应用 replay。记录所有 flit clocks/paths、注入间隔和接收尾部。
与固定 coarse 路径相同的调用才能算同路径抽象误差。若不相同，分别报告，不把
路由误差算成流水误差。可计算 coarse 服务在 native 观测路径上的诊断成本，但
明确它使用参考路径，不能当成可独立运行的新预测器。

**第二层：完整应用。** 比较两种后端完整完成时间、逐消息服务误差、实际路径、
关键链。新旧消息就绪时刻可以不同；不得把局部误差简单求和当应用因果贡献。
每次 native 完成后进行 standalone reference 检查，coarse 做独立服务/存储审计。

**事先判定。** 为本次工程筛查登记：完整应用 APE≤2%，每条同路径孤立服务
APE≤5%。这是人为选择的精度目标，不是论文领域标准；同时公开全部连续误差，
不只给通过/失败。一个维度通过不代表另一个维度通过。没有匹配路径时该项
不可判定。阈值只用于判断现有模型是否达到这次任务要求，不用于宣称通用准确率。

**仿真成本。** 每后端每条件三个 fresh-process cold repeats，另一个进程执行
三个 graph-reuse repeats。所有后端测量进程固定同一双 CPU affinity，顺序运行、交替
后端顺序，记录系统负载。Native 每次仍新建进程；reuse 只指输入/图/binding，
不是复用 native state。单独记录共同几何导出、构图、native 初始化、execute、
close+网络文件写入、执行记录序列化、独立审计及 standalone replay。
CPU 使用 Python self 和退出后 native 子进程的真实 usage；没有细分 native
阶段 CPU 的精度时不伪造。记录执行结束前 Python/native 的 lifetime peak RSS，
两者之和仅为非同时峰值上界；复用进程为累计高水位。
审计/replay 在全部计时 repeats 后执行，避免其内存污染执行峰值。日志保持现有
策略，报告事件和文件量；成本比包括 native IPC/日志差异，不宣称新算法加速。
冷启动 wall 包括解释器/import；不清空 OS page cache，故不是磁盘冷缓存结果。
共同几何导出在父进程中单独计量，不纳入两后端成本比，也未限制为测量进程的双核。

**验收。** 完整工作/字节/依赖/容量审计，native reference match，repeats 完整
模拟事件相同，两后端 input identity 相同，哈希包括 source/binary/environment。
必须区别研究运行完成与候选模型达到误差目标。既有结果不改写。

**结束产物。** 误差表、成本表、同路径服务及应用归因；根据证据决定是否需要
最小传输粒度修正。不在见到结果前添加新模型，不将此实验替代本地参数标定或
reticle 聚合准确性研究。
