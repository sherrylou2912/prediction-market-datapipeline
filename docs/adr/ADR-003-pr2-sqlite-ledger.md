# ADR-003：PR2 运行账本、checkpoint 与 manifest

- 状态：已接受（负责人决定，2026-11-13）
- 日期：2026-11-13
- 补充：[ADR-001](ADR-001-v1-architecture.md) 第 3、4 条，[ADR-002](ADR-002-pr1-foundation.md)“数据持久性”

## 账本先用 SQLite

**背景**：ADR-001 和 `agent/PROJECT.md` §3 原定由 PostgreSQL 做运行、checkpoint 和 manifest 的账本。当前机器没有 PostgreSQL 服务，项目也没有数据库驱动依赖；新增依赖须经负责人批准。

**决定**（负责人，2026-11-13）：v1 先用 Python 标准库 `sqlite3` 实现账本，文件位于 `DATA_ROOT/manifests/ledger.sqlite3`，不新增依赖。接口（`src/data_io/ledger.py` 的 `Ledger`）保持窄，以后可替换为 PostgreSQL 实现。

- 账本使用 `journal_mode=DELETE`、`synchronous=FULL`，macOS 上 `fullfsync=ON`；`PRAGMA user_version` 记录账本结构版本（当前 1），遇到未知版本拒绝打开。
- 账本文件不能是软链接，必须与 `DATA_ROOT` 在同一设备；REGISTRY writer 不能写 `manifests/ledger.sqlite3*`。
- manifest 登记时由账本重新计算磁盘文件的 SHA-256 和大小，schema 版本取自契约 registry；只登记 bronze、silver、gold 中与数据集同层的文件（imports 与 quarantine 的登记留给 PR3、PR4）。
- checkpoint 只能在登记 manifest 的同一事务中推进，调用方须说明已执行的验证，并给出期望的当前版本（新 checkpoint 为 0）；版本不符时整个事务回滚，manifest 也不登记。每次推进另存历史。
- 账本事务等待 SQLite 锁的时间为 `max(writer_lock_timeout_seconds, 5)` 秒：SQLite 的读写都会短暂持锁，即使写锁设置为立即失败，也不能让一次并发读取导致提交失败（agent 决定）。
- 只读连接使用普通连接加 `query_only`，不用 `mode=ro`：`mode=ro` 读者会让并发写者报误导性的 disk I/O 错误。普通连接打开时 SQLite 会回滚遗留日志，因此存在 `ledger.sqlite3-journal`、账本处于 WAL 模式或存在 `-wal` 文件时，只读命令拒绝打开（切回 DELETE 后遗留的 `-shm` 不读不写，允许）；只读连接用 `mode=rw` 打开，不会创建缺失的账本文件（agent 决定）。
- 登记路径必须与磁盘上的文件名逐级完全一致，避免大小写不敏感文件系统上同一文件以不同大小写登记两次；watermark 不能后退或被去掉。

**理由与后果**：SQLite 提供单机事务，测试和 CI 无需外部服务，符合“简单优先”和“无必要不加依赖”。代价是只适合单机；多机写入、远程查询和更大规模时需迁移到 PostgreSQL，届时写新 ADR。实际断电下的持久性尚未实测。

## 写锁等待

**决定**（负责人，2026-11-13）：新增共享配置 `writer_lock_timeout_seconds`（0–3600，默认 0）。0 保持 ADR-002 的立即失败；大于 0 时最多等待该秒数，超时报 `WriteBoundaryError`，数据不变。初始化仍完整扫描全部层和 `recovery/`，不缩小范围（agent 决定，正确性优先）。

## 运行记录与生效配置

**决定**（负责人，2026-11-13）：每次运行在账本中登记，结束时发布 `manifests/runs/<run_id>/record.json`，默认同时发布 `report.md`（可关闭）。生效配置、来源和哈希始终写进账本和 `record.json`，不受日志级别影响。运行先在账本中写最终状态，再从账本生成并发布记录（agent 决定）。

**后果**：文件发布与账本登记不在同一事务。两步之间中断时，文件会留下但未登记；`python -m src audit` 只读报告这类情况以及校验和不一致、遗留 partial、未结束运行和缺失的运行记录，处理仍需人工或后续恢复流程。
