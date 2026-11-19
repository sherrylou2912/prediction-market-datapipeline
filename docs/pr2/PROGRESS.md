# PR2 进度

> 最后更新：2026-11-19 18:08 · 分支 `codex/pr2-run-ledger` @ 本次“保存进度”提交（之前为 `4cd778e`）（未提交：B1、B2 的代码和文档改动，见“状态”）

## 交接

按新工作流处理 P1 的修改要求。B4 第 4 轮已收敛并提交；B2 第 4 轮已收敛（P1-F4、P1-F5 完成），但还没提交，因为它和 B1 改了相同的文件（README、CHANGELOG、ADR-003），要等 B1 收敛后先提交 B1、再提交 B2。B1 实现了 P1-F1、P1-F2（唯一写入入口 `open_write_layout`）、P1-F3（等锁改为“等通知”），经过第 4–8 轮审查；负责人决定冻结等锁实现（只修真正的错误），并在 8 轮上限后再给第 9 轮，**只补测试**。负责人要求暂停时，B1 第 9 步的 Analyst 被中途停止：它已经写好了新测试和 `layout.py` 的两处注释修改（B1-R8-1、B1-R8-2、B1-R8-3），但**还没跑检查，也没交回修订包**。

## 状态

阶段 **P1（B1–B4）**：修改反馈中（第 1 次）。

| 块 | 状态 | 说明 |
| --- | --- | --- |
| B1 写锁等待 | 第 9 步 Analyst 被中断（只补测试） | 第 8 轮剩 B1-R8-1（should-fix：帮手打开锁文件失败的路径没有测试）和两条 suggestion。工作区里的 `tests/test_writer_recovery.py` 和 `src/data_io/layout.py`（仅注释）含未检查的第 9 步改动。 |
| B2 SQLite 账本 | 已收敛（第 4 轮），未提交 | 等 B1 收敛后提交。 |
| B3 运行生命周期 | 已收敛 | 无待处理事项。 |
| B4 audit 与文档 | 已收敛，已提交（`4cd778e`） | 第 4 轮确认 B4-R3-1。 |

工作区未提交的代码和文档：`src/data_io/layout.py`、`src/data_io/runs.py`、`src/data_io/ledger.py`、`tests/test_writer_recovery.py`、`tests/test_ledger.py`、`tests/test_runs.py`、`README.md`、`CHANGELOG.md`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`、`src/config/README.md`、`src/config/README_FOR_DEVELOPER.md`、`agent/PROJECT.md`、`docs/FOUNDATION_RULES.md`。**不要丢弃这些改动。**

## 待处理的修改要求

| ID | 块 | 内容 | 状态 |
| --- | --- | --- | --- |
| B1-R8-1 | B1 | 为“帮手线程打开锁文件失败”加测试：另一个进程持锁时，线程里的打开抛 `EMFILE` 或 `WriteBoundaryError`，调用方很快报错、不写文件、不留帮手状态；删掉 `if fd is not None:` 或把 `except Exception` 改成 `except OSError` 时测试必须失败。只补测试，不改功能代码。 | 已写测试，未检查 |
| B1-R8-2 | B1 | 为“线程启动后、句柄登记前发生 fork”加确定性测试（suggestion）。 | 已写测试，未检查 |
| B1-R8-3 | B1 | 改准 `layout.py` 两处注释（suggestion）。 | 已改，未检查 |
| 条件 2 | B1 | 负责人对 P1-F3 的条件：合并前至少在 Linux 上跑一次连续写测试；目前没有 Linux 环境，文档已写明只在 macOS 验证过。 | 未满足（已按文档写明处理） |

P1-F1 至 P1-F5 都已完成：B2 部分已收敛；B1 部分等 B1 收敛。

## 待负责人回答的问题

无。

## 下一步

1. `继续`：开一个新的 B1 Analyst（第 9 步），在现有改动上完成并检查 B1-R8-1、R8-2、R8-3（只补测试，不改功能代码）。工作区里已有未检查的测试，Analyst 要先读懂再跑：lint、format、全量测试，锁测试连跑 30 次并在负载下跑，再用 Reviewer 的改坏代码脚本（`mut8.py` 的 M1、M2、M8）确认测试能抓到问题。
2. B1 第 9 轮审查 → 收敛后先提交 B1、再提交 B2（README、CHANGELOG、ADR-003 要按段落分开暂存）。
3. Reporter 做 P1 的改动汇报（只讲改动）→ 负责人验收 P1 → Validator。
