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
- silver 和 gold 的文件还必须放在以数据集名命名的第二级目录下（负责人决定，2026-11-19）：`silver.trades` 只能登记 `silver/trades/…`，`gold.market_1m` 只能登记 `gold/market_1m/<venue>/<market_id>/…`，`gold.training_datasets` 只能登记 `gold/training_datasets/<训练集名>/…`。直接放在 `silver/`、`gold/` 根下或放在别的数据集目录下的文件被拒绝，账本不变；`Run.commit_file` 在写文件之前就做这项检查，所以放错位置的文件不会写到磁盘上。目录名须与数据集名完全一致（区分大小写）。第二级以下的结构（venue、市场、数据版本、日期等）不检查，留给各 gold 产品的 PR。bronze 只有 `bronze.raw` 一个数据集，不会和别的数据集混在一起，仍只检查层（如 `bronze/kalshi/…`）。
- checkpoint 只能在登记 manifest 的同一事务中推进，调用方须说明已执行的验证，并给出期望的当前版本（新 checkpoint 为 0）；版本不符时整个事务回滚，manifest 也不登记。每次推进另存历史。
- 账本事务等待 SQLite 锁的时间为 `max(writer_lock_timeout_seconds, 5)` 秒：SQLite 的读写都会短暂持锁，即使写锁设置为立即失败，也不能让一次并发读取导致提交失败（agent 决定）。
- 只读连接使用普通连接加 `query_only`，不用 `mode=ro`：`mode=ro` 读者会让并发写者报误导性的 disk I/O 错误。普通连接打开时 SQLite 会回滚遗留日志，因此存在 `ledger.sqlite3-journal`、账本处于 WAL 模式或存在 `-wal` 文件时，只读命令拒绝打开（切回 DELETE 后遗留的 `-shm` 不读不写，允许）；只读连接用 `mode=rw` 打开，不会创建缺失的账本文件（agent 决定）。
- 登记路径必须与磁盘上的文件名逐级完全一致，避免大小写不敏感文件系统上同一文件以不同大小写登记两次；watermark 不能后退或被去掉。

**理由与后果**：SQLite 提供单机事务，测试和 CI 无需外部服务，符合“简单优先”和“无必要不加依赖”。代价是只适合单机；多机写入、远程查询和更大规模时需迁移到 PostgreSQL，届时写新 ADR。实际断电下的持久性尚未实测。

## 写锁等待

**决定**（负责人，2026-11-13）：新增共享配置 `writer_lock_timeout_seconds`（0–3600，默认 0）。0 保持 ADR-002 的立即失败；大于 0 时最多等待该秒数，超时报 `WriteBoundaryError`，数据不变。初始化仍完整扫描全部层和 `recovery/`，不缩小范围（agent 决定，正确性优先）。

**补充决定**（负责人，2026-11-19）：
- 写任务只通过 `src/data_io/layout.py` 的 `open_write_layout(config)` 创建布局：先 `validate_for_write()`，再用配置里的 `writer_lock_timeout_seconds` 调用 `DataLayout.create`。测试 `test_only_open_write_layout_creates_layouts_in_src` 读取 `src/` 的源码，除类型标注、`isinstance`/`issubclass` 检查、普通导入和 `layout.py` 中两处允许的位置外，任何对 `DataLayout` 或 `ScopedWriter` 的引用都判为违规：包括 `layout.DataLayout.create(...)` 这类经模块名的调用、直接构造 `DataLayout(...)`/`ScopedWriter(...)`（会跳过写前检查、遗留 partial 的恢复和配置的等待秒数）、`make = DataLayout.create` 这类别名；改名导入（`import DataLayout as X`）也判为违规。扫描只看源码文字，抓不到完全不写类名的写法，例如 `type(layout)(...)`、`layout.__class__.create(...)`、`dataclasses.replace(layout, ...)`、运行时拼字符串查找类，以及 `src/` 以外的代码（测试、脚本）。`Run.start` 仍检查配置与布局的等待秒数一致。
- 等锁不再每 50 毫秒轮询一次，而是在后台线程里用阻塞的 `flock` 等待（锁文件句柄由该线程自己打开、自己关闭，调用方从不替它关闭），调用方线程负责计时。锁一释放，等待者就被唤醒，因此连续写很多文件的任务通常不会再让等待者一直等到超时（macOS 实测每次约 10 毫秒内拿到锁）。这不是严格的先来先得队列，只是很强的倾向，不是保证。超时放弃后，后台线程和它打开的锁文件句柄会一直阻塞到锁空出来（守护线程，进程退出时随之结束），之后拿到锁会立即释放。同一进程再次等待同一把锁时，直接接手这个仍在等的线程，不再新开线程和句柄：单线程反复重试最多只多占一个线程和一个句柄；同一进程里有几个线程同时在等，最多各留一个（agent 决定，B1-R5-2）。进程在此期间 fork 时（例如 `multiprocessing` 的 `fork` 方式），子进程会立刻关闭继承来的等待句柄，不会替父进程一直占着锁（`os.register_at_fork`，B1-R5-3）；占锁写文件期间 fork 的子进程会共享这把锁，但只到父进程写完为止：释放时先显式解锁（`LOCK_UN`）再关闭句柄，所以即使子进程还在运行，锁也会空出来；只有拿锁的那个进程才解锁，子进程退出同一段代码时只关闭自己那份句柄，不会替父进程解锁（agent 决定，B1-R6-2）。父进程在写的过程中被杀掉时，子进程那份句柄仍会占着锁直到子进程退出。写任务仍不应在持锁时 fork。同一进程里多个线程同时等锁时，后台线程拿到锁后直接把句柄交给当时接手它的那次等待；一次等待把线程交回空闲表之后就不再读它的任何状态，所以锁不会被交给已经放弃的等待（B1-R6-1）。**中断的已知限制**：Ctrl-C 或信号处理函数抛出的异常可以落在任意两条 Python 指令之间。如果落在等锁或放锁的收尾过程中，而程序捕获它后继续运行，可能留下一个打开的锁文件句柄（不占锁）；少数情况下这把锁会被本进程一直占到进程退出，同一进程之后的等锁会在超时后失败；在 Python 3.9 上，内部互斥锁也可能因此一直被占，此时同一进程里其他线程的等锁或 fork 可能卡住。已缩小的部分（B1-R6-2）：放锁先解锁再关闭，单次打断仍会放锁；拿到的锁在交出时已经在调用方的句柄列表里；内部互斥锁可重入，被打断的线程自己的收尾不会和自己死锁；互斥锁里只做不会阻塞的操作（`Event.set` 移到锁外）；`Thread.start()` 可能在线程已经运行之后才抛异常（例如信号处理函数在它等新线程报到时抛出），这时调用方不会去关闭后台线程的句柄，只是不再复用这个线程，线程拿到锁后自己关闭句柄、放掉锁（B1-R7-1）。没有采用“等内部互斥锁最多等到超时”（`acquire(timeout=...)`）：实测（Python 3.9，随机时刻 Ctrl-C）它反而更容易把互斥锁留在被占状态，因为阻塞期间到达的 Ctrl-C 正好在 `acquire` 返回之后、`try` 开始之前生效；`with` 语句进入时没有这个空隙。完全消除需要在关键段屏蔽信号，本 PR 不做。Ctrl-C 后应让程序退出，操作系统会释放锁。超时为 0 时仍立即失败，不启动线程；超时错误仍为 `WriteBoundaryError`，数据不变。
- **只在 macOS 上验证过**：自动测试 `test_waiting_writer_gets_lock_while_another_process_writes_back_to_back` 和人工测量都在 macOS 上运行；Linux 上的唤醒行为尚未实测，部署到 Linux 前应在 Linux 上运行该测试。
- **冻结**（负责人，2026-11-19，B1-R7-2）：等锁实现到此冻结，之后只修真正的错误、不再增加新机制，剩下的极端情况（如上面的中断限制）只写进文档。

## 运行记录与生效配置

**决定**（负责人，2026-11-13）：每次运行在账本中登记，结束时发布 `manifests/runs/<run_id>/record.json`，默认同时发布 `report.md`（可关闭）。生效配置、来源和哈希始终写进账本和 `record.json`，不受日志级别影响。运行先在账本中写最终状态，再从账本生成并发布记录（agent 决定）。

**后果**：文件发布与账本登记不在同一事务。两步之间中断时，文件会留下但未登记；`python -m src audit` 只读报告这类情况以及校验和不一致、遗留 partial、未结束运行和缺失的运行记录，处理仍需人工或后续恢复流程。
