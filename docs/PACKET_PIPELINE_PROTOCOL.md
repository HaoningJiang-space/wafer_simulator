# 最小修正实验：跨跳 packet 流水

在结果产生前登记。沿用`transfer-granularity-001`的两份完整工作、Baseline、
row-major、direct-root、TP8、32 B/cycle memory及256 KiB容量。目标、输入和
seed不改；原 coarse、BookSim 均保留。候选采用原 coarse 的确定性最少跳路径。

## 来自代码的服务合同

固定作者 trace 路径在`trafficmanager.cpp::_Inject`中把每个flit生成为独立
head+tail packet。`booksim_wrapper.py`设置routing delay=0、VC allocation=1、
switch allocation=1、crossbar final=2；当前配置non-speculative、one VC、
wait_for_tail_credit=0。`IQRouter::_InternalStep`先evaluate再update，VC allocation
完成后下一周期进入switch allocation；尾flit发送释放output VC，下一packet再
申请。这给出无额外阻塞时同一output两周期的packet启动间隔，不是从上轮误差拟合。

注入channel一packet/cycle。带router的link输出和ejection输出按两cycle启动；
它们的飞行时延分别取已有router+link latency和最终router+access latency。
沿用原生边界约定，源注入和最终接收各计一个边界cycle，内部link不重复加边界。
这保持物理channel的名义一flit/cycle，而用单VC allocation约束其可实现的
packet启动；不把2000 B/cycle物理链路改成1000 B/cycle设计。

仅支持这套已核对配置；其他VC数、packet size、speculation或router pipeline
拒绝使用。源码路径都在pinned `third_party/nw-design-for-wsi/rapidchiplet/`内。

## 只替换必要的一层

复用`ResourceCalendar`：每packet提交一组注入、路径输出、接收服务，某一跳
完成后才申请下一跳，允许同一消息的不同packet处于不同跳。不预留未来路径。
每消息等全部packet到达后发布完成；storage和rank-local output合同不变。

本候选仍为FCFS共享输出、无限排队、固定路由，未模拟input-VC竞争、有限buffer/
credit或adaptive routing。它不是BookSim事件的等价压缩，也不先声称保留拥塞精度。
这些省略是否重要由完整应用与逐消息结果决定，不能凭孤立传输通过就宣布成功。

## 实验和验收

三后端×两份完整工作，各3次冷进程和3次图复用；顺序轮换，固定同一双CPU。
沿用上一轮分阶段wall/CPU/RSS、全部事件、哈希及独立审计。BookSim继续做
standalone时间戳检查，coarse/native应精确恢复已接受的完整事件哈希。
28条来自binding的孤立消息也运行候选；保留原生路径和全部packet服务记录。

精度目标沿用应用APE≤2%、匹配路径的孤立服务APE≤5%，不因新结果改阈值。
同时报告完整应用逐消息误差、关键链、队列和路径差异，不能只验收两个小APE。
计成本时保持原日志策略，并报告候选新增packet事件数量和记录量。

如果孤立精度改善而完整工作出现剩余偏差，定位具体消息及先前省略的机制；
不在同一轮继续加buffer/VC/新路由。若未达到目标，保留失败证据和参考后端。
不把校正跨跳服务等同于8-GPC/SRAM聚合验证，也不自动替换默认粗模型。
