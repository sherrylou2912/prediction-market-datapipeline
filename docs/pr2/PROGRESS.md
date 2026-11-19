# PR2 进度

> 最后更新：2026-11-18 · 分支 `codex/pr2-run-ledger` @ `6e6dfe0`（未提交：agent 工作流文档、`.claude/`、`docs/README.md`、`docs/pr2/PLAN.md`、本文件）

## 交接

PR2 的 B1–B4 代码已经写完并走过旧流程的审查：B2、B3 已收敛；B1、B4 达到旧的 3 轮上限后做了修复（`9d0e8f3`、`e69f167`），但还没有 Reviewer 复核。负责人已逐块读完 B1、B2，提出 5 条修改要求（见下表），并决定它们都在本 PR 处理。本次对话重写了 agent 工作流：阶段与两层循环、独立子代理、Orchestrator 指南、快捷命令；本文件改为只保留最新快照。下一步按新流程处理 P1 的修改要求。

## 状态

阶段 **P1（B1–B4）**：修改反馈中（第 1 次）。

| 块 | 状态 | 说明 |
| --- | --- | --- |
| B1 写锁等待 | 待内循环 | `9d0e8f3` 的修复未经审查；修改要求 P1-F1、P1-F2、P1-F3 |
| B2 SQLite 账本 | 待内循环 | 修改要求 P1-F1、P1-F4、P1-F5 |
| B3 运行生命周期 | 已收敛 | 无待处理事项 |
| B4 audit 与文档 | 待内循环 | `e69f167` 的修复（B4-R3-1）未经审查 |

## 待处理的修改要求

| ID | 块 | 内容 | 状态 |
| --- | --- | --- | --- |
| P1-F1 | B1、B2（文档） | 把两把锁的等待差异写清楚：`CHANGELOG.md:10` 说账本事务“最多等配置的秒数”，实际是至少等 5 秒（`max(writer_lock_timeout_seconds, 5)`），要改正；`README.md:56`、`src/config/README.md:29` 补一句：写锁超时只管 `.writer.lock`，账本另外至少等 5 秒，超过 5 秒仍拿不到锁时文件已写入但未登记，由 `audit` 报告。ADR-003 已正确。 | open |
| P1-F2 | B1 | 目前没有真实写任务把配置里的 `writer_lock_timeout_seconds` 传给 `DataLayout.create`，只有文档示例和 `Run.start` 的一致性检查。本 PR 处理，做法由 Reviewer 在审查中问负责人。 | open |
| P1-F3 | B1 | 写锁等待是每 50 毫秒试一次，不保证先到先得；多个任务同时等时，可能有一个一直抢不到。本 PR 处理，做法由 Reviewer 在审查中问负责人。 | open |
| P1-F4 | B2 | `commit_values` 只检查路径第一级是层名，`silver.trades` 的文件放在 `silver/quotes/c.parquet` 也能登记（已实测）。本 PR 加“数据集与子目录对应”检查；项目里还没有统一路径规则（gold 的例子是 `gold/<venue>/…`），规则怎么定由 Reviewer 在审查中问负责人。 | open |
| P1-F5 | B2 | `ledger.py:571-580` 先查 watermark 后查版本。两个任务抢同一个 checkpoint、后到者不带 watermark 时，报的是“watermark 不能后退”，真正原因是版本冲突（已实测）。把版本检查放到前面，加测试断言错误信息。（agent 建议） | open |

## 待负责人回答的问题

无。P1-F2、P1-F3、P1-F4 的具体做法会由 Reviewer 在审查中按通俗格式提出。

## 下一步

`开始修改`：对 B1、B2、B4 分别运行内循环（新的 Analyst 处理上表修改要求 → 新的 Reviewer 审查，同时复核 `9d0e8f3`、`e69f167`），全部收敛后由 Reporter 做 P1 的改动汇报。
