# PR2 逐块代码阅读进度

> 过程记录，只在分支 `codex/pr2-run-ledger` 上保留，不合入 `main`。行号指 `e69f167` 的版本。

负责人于 2026-11-13 要求按 Reporter 规则逐个代码块 review（替代 B1、B4 升级后的第 4 轮复核决定）。

## 1. 阅读状态

| 块 | 文件 | 状态 | 日期 | 结论 |
| --- | --- | --- | --- | --- |
| B1 写锁等待 | `src/config/validation.py`、`src/config/models/pipeline.py`、`src/config/defaults/runtime.json`、`src/data_io/layout.py`（`_lock`、`DataLayout`、`ScopedWriter`） | 已讲解，待负责人反馈 | 2026-11-13 | 见 §4.1 |
| B2 SQLite 账本 | `src/data_io/ledger.py` | 未开始 | — | — |
| B3 运行生命周期 | `src/data_io/runs.py` | 未开始 | — | — |
| B4 audit 与文档 | `src/data_io/audit.py`、`src/cli.py`、文档 | 未开始 | — | — |

## 2. Analyst 实施清单

（阅读中产生的修改要求记录在此，标明尚未实施。）

## 3. 需要负责人确认的事项

| 事项 | 所在块 | 详情 |
| --- | --- | --- |
| 写锁默认 0（立即失败），但账本 SQLite 锁至少等 5 秒，是否接受这种差异 | B1/B2 | §4.1 问题 1 |

## 4. 待办详情

### 4.1 B1

阅读时实际运行：`uv run pytest tests -q -k "lock or invalid_fields or json_default or zero_padded"` → 40 passed, 386 deselected；`PipelineConfig.load` 示例：未设置 → `0`（`default:runtime.json`），`" 0030 "` → `30`（`environment:…`），`3601` → `ConfigError`。

发现的问题（待负责人反馈）：

1. 写锁 `0` 表示立即失败，但账本事务的 SQLite 锁至少等 5 秒（PLAN A10、ADR-003）。两处“等待”语义不同。
2. 目前没有真实写任务把配置值传给 `DataLayout.create`；只有文档示例和 `Run.start` 的一致性检查。
3. 等待是每 50 ms 轮询一次，不保证先到先得；多个任务争用时可能有人一直抢不到。

## 5. 未来设计要求（不在本 PR 实施）

- B2-R2-2：逐级列目录的开销，在真实回填 PR 中测量。
- B3-R1-6：按账本重新生成缺失的运行记录。
- B3-R1-7：PR3 接入真实来源时对异常文本脱敏。
