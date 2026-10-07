# 本轮服务器清理

已按用户授权在 eex005 删除 **2,329 个文件，454,127,566 逻辑字节**，原文件
占用 459,890,688 分配字节。失败/被替代结果的留档和完整删除收据约 22 MB，另留
dry-run 清单；净减少约 **0.43 GB**。这是枚举文件的记账量，非共享文件系统的
瞬时空闲量变化。逐文件原路径、大小、时间和 SHA-256 见 [PRUNED.json](PRUNED.json)。

| 清理范围 | 删除内容 | 保留内容 |
|---|---|---|
| `runs/memory-boundary-001` | 因首次网络前 clock 初始化失败的部分运行 | 原 FAILED、配置、日志及文件哈希 |
| `runs/memory-boundary-002` | 第一次完整运行；第四诊断没有实际共享链路，未获本阶段机制验收 | 原 COMPLETE 及配置/审计/日志，保留其“执行完成但机制覆盖不合格”的区别 |
| `runs/memory-boundary-003` | 第二个候选共享路径被 gate 拒绝的部分运行 | 原 FAILED、配置、日志及文件哈希 |
| `runs/memory-boundary-analysis-001`、`-002` | 对 002 的被替代回读/replay | 原 summary、验收及分析哈希清单、CSV/日志 |
| `runs/memory-boundary-tests-001` 至 `-004` | 被同版本测试 005 替代的测试输入/原生输出 | SEMANTICS、tests.log 及文件哈希 |
| `build/booksim-fixed`、`-node-reuse`、`-runtime-opt`、`-topology-ref` | 仅未跟踪的生成 `.o` 文件 | 原源码、Git worktree、补丁和二进制 |

没有删除原始输入、完整 Llama 验收结果、已验收网络流水结果、当前 boundary 004 /
analysis 003 / tests 005，以及当前/参考/CSR BookSim build。
`prepare_model_boundary_remote.py` 仍引用 CSR build，所以它也保留。
旧构建若重新编译会再生成 `.o`；历史二进制仍可直接核验运行。

执行脚本为 `scripts/prune_boundary_intermediates_remote.py`，只接受枚举目录：
先确认接受的结果存在，检查活动进程的 cwd/exe/fd，归档必要收据，复核每个候选
大小/mtime/hash 后才删除。2338 项保留源码、二进制及结果哈希在删除后再次一致。
不可读取 `/proc` 的 `sshd`/`(sd-pam)` 会话辅助进程单独记录为检查盲区，用户 shell
及子任务照常检查；其他进程权限错误会使清理停止。没有结束任何用户进程。

紧凑留档位于：

`/home/wangziheng/wafer_simulator/runs/memory-boundary-cleanup-001/receipts/`

其中路径保持相对 runtime 根目录的原始结构。删掉的原始大事件不能再直接从旧
目录回读；若需要复查被排除的候选，应按留档配置和 Git 版本重跑。它们不是当前
结论的证据输入。当前所有已验收 raw events 保留在原目录，复现入口未改变。

本轮未删除 Python/C++ 模型源码：整消息、packet pipeline 和 native backend 都仍
承担已登记的对照或回归用途，不能只因较慢或结果被更新就判断为无用代码。
