# PR2 计划：运行登记、checkpoint、manifest 与原子提交

> 过程记录，只在工作分支 `codex/pr2-run-ledger` 上保留，不合入 `main`。

## 1. 目标

实现 `agent/PROJECT.md` §9.2 第 2 项：运行登记（run registry）、checkpoint、文件 manifest，以及“写文件 → 校验 → 登记 manifest → 推进 checkpoint”的原子提交；同时处理 PR1 留给 PR2 的写锁等待（ADR-002）和生效配置记录（V2-1）。

## 2. 负责人确认的决定（2026-11-13）

| 编号 | 决定 |
| --- | --- |
| D1 | 账本先用 Python 自带 `sqlite3`，位于 `DATA_ROOT/manifests/ledger.sqlite3`，接口保持窄，以后可换 PostgreSQL；不新增依赖。需新 ADR 并修改 PROJECT.md §3 表述。 |
| D2 | 写锁超时可配置：`writer_lock_timeout_seconds`，默认 `0`（保持立即失败），超时后报错且数据不变。 |
| D3 | 生效配置始终写进运行记录（`record.json` 和账本），不受日志级别影响；日志仍按 INFO 输出。 |

## 3. Agent 自主决定（依据与风险）

| 编号 | 决定 | 依据 | 风险 |
| --- | --- | --- | --- |
| A1 | SQLite 使用 `journal_mode=DELETE`、`synchronous=FULL`，macOS 上 `fullfsync=ON`；`PRAGMA user_version` 记录账本结构版本，遇到未知版本拒绝打开。 | 正确性优先（PROJECT §1）；默认回滚日志最容易排查。 | 写入较慢；实际断电行为未实测。 |
| A2 | manifest 登记时由账本自己重新计算磁盘上文件的 SHA-256 和大小，不信任调用方。 | 硬规则 3。 | 大文件登记时多读一次。 |
| A3 | checkpoint 只能在登记 manifest 的同一事务中推进，必须声明已执行的验证，并用 `expected_version` 防止两个运行同时推进。 | 硬规则 3、PROJECT §6。 | 调用方须提供验证说明；真实验证模块在 PR4。 |
| A4 | manifest 只登记 registry 中存在的数据集，schema 版本取自 registry，文件必须位于数据集所在层（bronze/silver/gold）。imports 与 quarantine 的登记留给 PR3、PR4。 | 单一事实来源；避免编造版本。 | PR3 需要扩展。 |
| A5 | 初始化时仍完整扫描全部层和 recovery，不缩小扫描范围。 | 正确性优先；缩小范围可能漏掉 partial。 | 数据量大时初始化变慢；见后续建议。 |
| A6 | `run_id` 形如 `20261113t120000z-<12位十六进制>`，符合 Bronze `receipt_id` 规则，可直接作为接收身份。 | 便于排序和追溯。 | — |
| A7 | 运行结束先在账本中写最终状态，再由 REGISTRY writer 发布 `manifests/runs/<run_id>/record.json`（及默认的 `report.md`）。记录内容完全来自账本，可重新生成。 | 账本是权威；中断时 audit 能发现“已结束但缺记录”。 | — |
| A9 | `writer_lock_timeout_seconds` 除 `runtime.json` 外还有模型默认值 `0`；缺字段时来源记为 `default:model`，测试保证两处默认值一致。 | `0` 即 PR1 行为，普遍安全；自定义配置目录和直接构造不必修改。 | 两处默认值需保持一致（已有测试）。 |
| A8 | 新增只读 `audit` 命令：核对 manifest 文件是否存在、校验和是否一致，报告未登记文件、遗留 partial、未结束运行和缺失的运行记录；只报告，不修改。 | FOUNDATION_RULES §8“文件已写入但 checkpoint 未推进时须检查”；PROJECT §11 可排查性。 | 每次全量计算校验和，数据大时较慢。 |

## 4. 代码块与验收示例

### B1 写锁超时
- `PipelineConfig.writer_lock_timeout_seconds`（0–3600 的整数，默认来自 `runtime.json`，环境变量 `PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS` 可覆盖）。
- `DataLayout.create(root, lock_timeout_seconds=...)`，writer 继承该值。
- 验收：超时 0 时锁被占用立即失败；超时 1 秒且锁一直被占用时约 1 秒后失败，数据不变；锁在等待期间释放时成功；非法值（负数、布尔、超过 3600、非数字字符串）被拒绝。

### B2 SQLite 账本
- `src/data_io/ledger.py`：建表、运行、manifest、checkpoint；`commit` 在一个事务中登记 manifest、推进 checkpoint、累计行数。
- 验收：校验和由账本计算；文件不存在、不在对应层、数据集未知、时间不是 UTC、范围颠倒时拒绝且账本不变；`expected_version` 不符时拒绝且 manifest 也不登记；运行已结束时拒绝；同一路径重复登记被拒绝；未知 `user_version` 拒绝打开；账本文件为软链接时拒绝。

### B3 运行生命周期与运行记录
- `src/data_io/runs.py`：`Run.start`、`commit_file`、`add_counts`、`finish`、上下文管理器；记录代码版本（commit 和是否有未提交修改，无法获取时写未知）、生效配置及哈希、参数、规则版本。
- 验收：成功运行生成 `record.json`、`report.md`（可关闭）；异常退出记为 `failed` 并保留错误；结束后不能再提交；`partial` 状态可用；参数不能 JSON 序列化时在任何副作用前拒绝。

### B4 audit 命令与文档
- `src/data_io/audit.py` 与 `python -m src audit`（只读 preflight）。
- 验收：干净数据返回 0；篡改已登记文件、删除文件、未登记文件、遗留 partial、未结束运行、缺失 record 都被报告并返回 1；不创建目录、不写任何文件；没有账本时报告清楚。
- 文档：ADR-003、PROJECT.md §3/§6、FOUNDATION_RULES、README、CHANGELOG、`src/config` 两份 README、`docs/README.md` 索引。

## 5. 不在本 PR

PostgreSQL、下载器与导入器（PR3）、跨行验证与 quarantine 流程（PR4）、调度器、真实 venue、断电实测。

## 6. 检查

`uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest tests/ -v`。
