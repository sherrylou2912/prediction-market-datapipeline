# PR2 Review Log

> 过程记录，只在工作分支 `codex/pr2-run-ledger` 上保留，不合入 `main`。

## Block B1 · Round 1 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `24501f2`（含 `6107c38`，基于 `main` `71499dc`）；files: `src/config/validation.py`、`src/config/models/pipeline.py`、`src/config/defaults/runtime.json`、`src/data_io/layout.py`、`tests/test_cli_logging.py`、`tests/test_writer_recovery.py`、`src/config/README.md`、`src/config/README_FOR_DEVELOPER.md`、`README.md`、`docs/pr2/PLAN.md`。`git diff main..24501f2 --stat` 与 revision packet 所列 10 个文件一致。
- 审查方式：在 `/private/tmp/b1-review-wt` 以 `git worktree add --detach 24501f2` 检出该提交运行检查，结束后已移除；未审查主工作区中不属于 B1 提交的未提交改动。
- Checks run by Reviewer（均在上述 worktree 内）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 24 files already formatted
  - `uv run pytest tests/ -q` → 359 passed in 3.84s
  - 临时探测脚本（scratchpad，未入库）验证：直接构造 `True`/`False`/`3601`/`-1`/`1.0`/`"5"` 均被拒绝；环境变量 `3601`/`+5`/`1_0`/全角 `５` 被拒绝，`" 5 "` 接受为 5，`"0003600"` 被拒绝；`runtime.json` 中 `true`/`3601`/`"5"` 被拒绝，缺少该字段时取 0 且来源记为 `default:runtime.json`；`DataLayout.create(lock_timeout_seconds=True/1.5/3601/None)` 被拒绝；锁一直被占用时 `ScopedWriter.write_new` 约 1.0 秒后报 `WriteBoundaryError (waited 1s)`，`silver/` 下无任何文件（含 partial），锁在等待中释放后写入成功。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| — | — | 首轮，无此前发现。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R1-1 | must-fix | `tests/test_writer_recovery.py:466-489`；`tests/test_pipeline_foundation.py:33-50`（未扩展） | PLAN §4 B1 验收要求的若干项没有测试覆盖：(a) “布尔被拒绝”——新增测试只覆盖环境变量字符串 `-1/3601/abc/1.5`，直接构造、`runtime.json` 和 `DataLayout.create` 的布尔值均无测试（代码实际会拒绝，见探测结果，但无回归保护）；(b) “超时后数据不变”——新测试只断言报错和耗时，没有像 `test_held_lock_fails_immediately_and_preserves_partial` 那样检查遗留 partial 未被处理、目录未变化；(c) writer 的等待路径（`ScopedWriter.write_new` 在锁被占用时等待/超时/成功）完全未测试，只测了 `DataLayout.create`；(d) 合法环境变量覆盖（如 `5`）的取值与来源 `environment:PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS`、`runtime.json` 中非 0 值生效均无测试。 | 在 `test_direct_config_and_reconstruction_reject_invalid_fields` 参数表加入 `writer_lock_timeout_seconds` 的 `True`、`-1`、`3601`、`1.0`、`"5"`；增加 `runtime.json` 非法值（`true`、`3601`）用例；`DataLayout.create` 增加 `True` 用例；超时用例中放置 partial 并断言超时后其仍在原处、`recovery/` 无新增；增加 `write_new` 在持锁时超时（目标文件和 partial 均不存在）及等待中释放后成功的用例；增加合法覆盖值与来源断言。 |
| B1-R1-2 | should-fix | `src/config/models/pipeline.py:170-172`（`load()` 的 `sources`） | 当 `runtime.json`（例如自定义 `PIPELINE_CONFIG_DIR` 中的旧文件）缺少 `writer_lock_timeout_seconds` 时，实际取的是模型默认值 0，但来源仍记为 `default:runtime.json`。按 D3 生效配置会写入运行记录，来源不实会误导审计（硬规则 10 要求记录默认值或覆盖值的真实来源）。 | 区分来源：JSON 中存在该字段时记 `default:runtime.json`，缺失时记如 `default:model`（可用 `"writer_lock_timeout_seconds" in runtime.model_fields_set` 判断），并加测试；同步 `src/config/README.md` 的来源说明。 |
| B1-R1-3 | suggestion | `src/config/models/pipeline.py:91,114`；`docs/pr2/PLAN.md` §3 | 模型级默认值 `0` 偏离 PLAN“默认来自 `runtime.json`”。评估：可接受——0 即 PR1 行为、普遍安全，且现有多处测试和自定义配置目录只含 `log_level`，改为必填会造成无关破坏；但这形成 JSON 与模型两处默认值，且该偏离未记入 PLAN 的 Agent 自主决定表（AGENTS.md 要求单独记录 agent 决定及理由）。 | 在 PLAN §3 增加一条 A 决定（理由、风险：两处默认可能漂移）；可加一个测试断言 `defaults/runtime.json` 的值与模型默认值一致，防止漂移。与 B1-R1-2 一并处理。 |
| B1-R1-4 | suggestion | `src/data_io/layout.py:356-357` 与 `src/config/validation.py:28-34` | 0–3600 的范围和“非 bool 的 int”规则在两个模块各写一遍，`3600` 为重复字面量；`ScopedWriter`、`DataLayout` 为公开 dataclass，直接构造时 `lock_timeout_seconds` 不经校验（负数会立即失败，`True` 会被当作 1 秒）。失败均为显式报错或较短等待，不会静默损坏数据，故不阻塞。 | 在 `src/data_io/layout.py` 定义唯一常量（`data_io` 目前不依赖 `src.config`，可让 `validation.py` 引用该常量或反之，保持单一事实来源）；可在 `ScopedWriter.__post_init__` 复用同一校验。 |
| B1-R1-5 | suggestion | `src/config/models/pipeline.py:152` | 环境变量用 `len(raw_timeout) > 4` 预先拒绝，导致合法值 `"0003600"`、`"00005"` 被拒绝，而 `DATA_MIN_FREE_GIB` 接受前导零；README 只写“ASCII 十进制数字，取值 0–3600”，未说明此限制。 | 去掉长度判断，直接 `int()` 后交给 `LockTimeoutSeconds` 校验范围（ASCII 数字字符串长度可先设较宽上限防超大输入），或在 README 中写明。 |
| B1-R1-6 | suggestion | `tests/test_writer_recovery.py:476-477` | 1 秒超时测试只断言耗时 `>= 0.9`，没有上限，无法发现“等待远超设定值”的回归（验收为“约 1 秒后失败”）；`threading.Timer` 线程未 join。 | 增加宽松上限（如 `< 3`），Timer 线程在 `with` 结束后 `join()`。 |
| B1-R1-7 | out-of-scope | `CHANGELOG.md:11`、`docs/adr/ADR-002-pr1-foundation.md:11` | CHANGELOG 0.1.0 条目和 ADR-002 仍写“锁被占用时立即失败、带超时等待留待 PR2”。作为历史记录本身没错，但 PR2 需要说明默认行为不变、可配置等待已实现。PLAN 已把 CHANGELOG/ADR 更新放在 B4。 | 在 B4 的 CHANGELOG 新版本条目和 ADR-003（或 ADR-002 后续说明）中记录 D2 的实现。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B1-R1-1 | fixed | `tests/test_pipeline_foundation.py` 直接构造参数表新增 `-1/3601/True/1.5/"1"`；`tests/test_writer_recovery.py` 新增：`test_invalid_lock_timeout_rejected_for_layout_and_writer`（`DataLayout.create` 与直接构造的 `ScopedWriter` 拒绝 `-1/3601/True/1.5/"1"`，目标未创建）、`test_create_waits_for_lock_then_fails_without_change`（超时后遗留 partial 未动、recovery 无新增；等待中释放后成功）、`test_write_waits_for_lock_then_fails_or_succeeds`（`write_new` 超时后 `silver/` 为空，释放后成功）、`test_lock_timeout_sources`（合法覆盖 `" 0030 "` 取值 30 与来源；`runtime.json` 值 7 生效；`runtime.json` 非法值 `-1/3601/true/1.5/"1"` 被拒绝）、环境变量非法值加入全角数字。 |
| B1-R1-2 | fixed | `src/config/models/pipeline.py` `load()` 用 `runtime.model_fields_set` 区分，缺字段时来源为 `default:model`；`test_lock_timeout_sources` 断言；`src/config/README.md` 已写明。 |
| B1-R1-3 | fixed（采纳 suggestion） | PLAN §3 新增 A9；`test_json_default_matches_model_default` 断言两处默认一致。 |
| B1-R1-4 | fixed（采纳 suggestion） | 唯一常量 `MAX_LOCK_TIMEOUT_SECONDS` 在 `src/config/validation.py`；`layout._lock` 引用它并在加锁前校验，覆盖 `DataLayout` 和直接构造的 `ScopedWriter`；`DataLayout.create` 中的重复校验已删除。 |
| B1-R1-5 | fixed（采纳 suggestion） | 删除长度判断，前导零值由类型校验处理；`" 0030 "` 用例覆盖。 |
| B1-R1-6 | fixed（采纳 suggestion） | 两个超时用例断言 `0.9 <= 耗时 < 3`，Timer 线程 `join()`。 |
| B1-R1-7 | 转 B4 | 在 B4 的 CHANGELOG 和 ADR-003 中记录。 |

Analyst 检查：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 通过；`uv run pytest tests/ -q` → 393 passed（含尚未提交的 B2 `tests/test_ledger.py` 20 个用例；B1 提交不含 B2 文件）。

- Round result: `changes requested`

## Block B1 · Round 2 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `52bd831`（相对第 1 轮：`git diff 24501f2..52bd831`）；files: `docs/pr2/PLAN.md`、`docs/pr2/REVIEW_LOG.md`、`src/config/README.md`、`src/config/models/pipeline.py`、`src/config/validation.py`、`src/data_io/layout.py`、`tests/test_pipeline_foundation.py`、`tests/test_writer_recovery.py`。主工作区未提交的 `src/data_io/ledger.py`、`src/data_io/runs.py`、`tests/test_ledger.py`、`tests/test_runs.py` 属于 B2/B3，不在本轮审查范围；`layout.py` 中 `manifests/ledger.sqlite3*` 保留名检查属于 B2，仅确认未影响 B1。
- 审查方式：在 `/private/tmp/b1-review-wt2` 以 `git worktree add --detach 52bd831` 检出运行，结束后已移除。
- Checks run by Reviewer（均在上述 worktree 内，Python 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 24 files already formatted
  - `uv run pytest tests/ -q` → 373 passed in 5.14s（Analyst 报告的 393 含主工作区未提交的 B2/B3 测试，与本提交单独的 373 不矛盾）
  - `uv run pytest tests/ -q -k "lock or invalid_fields or json_default"` → 36 passed, 337 deselected
  - 探测（Python 3.13.2，独立临时 venv，结束后删除）：`PipelineConfig.load(environ={..., "PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS": "9"*5000})` 与 `"0"*5000+"5"` 均抛出原生 `ValueError: Exceeds the limit (4300 digits) for integer string conversion`，而同样输入给 `DATA_MIN_FREE_GIB` 时得到 `ConfigError: DATA_MIN_FREE_GIB is too large to parse.`

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R1-1 | resolved | `tests/test_pipeline_foundation.py:50-54` 直接构造拒绝 `-1/3601/True/1.5/"1"`；`tests/test_writer_recovery.py` 新增 `test_invalid_lock_timeout_rejected_for_layout_and_writer`、`test_create_waits_for_lock_then_fails_without_change`（partial 保留、`recovery/` 无新增）、`test_write_waits_for_lock_then_fails_or_succeeds`（超时后 `silver/` 为空）、`test_lock_timeout_sources`（覆盖值、来源、`runtime.json` 合法与非法值），均通过。 |
| B1-R1-2 | resolved | `src/config/models/pipeline.py:170-174` 依 `runtime.model_fields_set` 区分 `default:runtime.json`/`default:model`；`test_lock_timeout_sources` 断言；`src/config/README.md` 已同步。 |
| B1-R1-3 | resolved | PLAN §3 新增 A9；`test_json_default_matches_model_default` 断言两处默认值一致。（A9 行排在 A8 之前，仅排版问题，不另立发现。） |
| B1-R1-4 | resolved | `MAX_LOCK_TIMEOUT_SECONDS` 唯一定义于 `src/config/validation.py`，`src/data_io/layout.py:91-93` 在 `_lock` 内引用并校验，覆盖直接构造的 `DataLayout`/`ScopedWriter`；`src.config` 不导入 `src.data_io`，无循环导入。 |
| B1-R1-5 | resolved，但引入新问题 | 长度判断已删除，`" 0030 "` 被接受为 30；但删除后超长数字串在 Python ≥3.11 上触发未转换的 `ValueError`，见 B1-R2-1。 |
| B1-R1-6 | resolved | 两个超时用例断言 `0.9 <= 耗时 < 3`，Timer 线程 `join()`，句柄在 `finally` 中关闭。 |
| B1-R1-7 | deferred（out-of-scope，转 B4） | Analyst 已确认在 B4 的 CHANGELOG 与 ADR-003 中记录；不阻塞 B1。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R2-1 | should-fix | `src/config/models/pipeline.py:151-160`（`int(raw_timeout)`） | 修复 B1-R1-5 时删除了长度判断，`int(raw_timeout)` 不再有保护。项目支持 Python ≥3.9，在 Python ≥3.11 上，超过 4300 位的纯数字环境变量会抛出原生 `ValueError`，而不是带变量名的 `ConfigError`；与 `DATA_MIN_FREE_GIB` 已有的 `try/except ValueError` 处理不一致，违反“非法设置立即以清晰错误拒绝”（硬规则 10）。当前 3.9 测试环境无法发现，已在 3.13.2 上复现。 | 仿照 `DATA_MIN_FREE_GIB` 用 `try/except ValueError` 转为 `ConfigError("PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS must be an integer from 0 to 3600.")`；或先去掉前导零再按长度（>4 位）直接拒绝，这样既接受 `"0003600"`，又不依赖解释器版本。补一个超长输入（如 `"9"*5000`）的测试，断言得到 `ConfigError`。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B1-R2-1 | fixed | `src/config/models/pipeline.py`：去掉前导零后有效数字超过 4 位即报 `ConfigError`，不再调用 `int()`；`test_invalid_lock_timeout_environment_rejected` 增加 `"9" * 5000` 用例。前导零值（`" 0030 "`）仍接受。 |

- Round result: `changes requested`

## Block B1 · Round 3 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `11e344b`（B1 相关改动：`git diff 52bd831..11e344b -- src/config tests/test_writer_recovery.py docs/pr2/PLAN.md`）；files: `src/config/models/pipeline.py`、`tests/test_writer_recovery.py`、`docs/pr2/PLAN.md`、`docs/pr2/REVIEW_LOG.md`。同一区间内的 `45527fd`（B2）、`ee1ddf6`（B3），以及主工作区未提交的 `src/cli.py`、`src/data_io/audit.py`、`tests/test_audit.py`（B4）都不在本轮审查范围。
- 审查方式：在 `/private/tmp/b1-review-wt3` 以 `git worktree add --detach 11e344b` 检出运行，结束后已移除。
- Checks run by Reviewer（均在上述 worktree 内，Python 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 28 files already formatted
  - `uv run pytest tests/ -q` → 403 passed in 5.54s（含已提交的 B2/B3 测试）
  - `uv run pytest tests/ -q -k "lock or invalid_fields or json_default"` → 38 passed, 365 deselected
  - 探测（Python 3.13.2，独立临时 venv，结束后已删除），`PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS` 取以下值：`"9"*5000` → `ConfigError`（已修复）；`"0"*5000+"5"` → 原生 `ValueError: Exceeds the limit (4300 digits) for integer string conversion`；`"0"*5000` → 同样的原生 `ValueError`；`"0003600"` → 3600；`"3601"` → `ConfigError`。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R2-1 | not resolved | `src/config/models/pipeline.py:152-160`：现在只用 `len(raw_timeout.lstrip("0")) > 4` 判断，但随后的 `int(raw_timeout)` 仍对**原始**字符串（含全部前导零）调用。Python ≥3.11 的位数限制按整串计算，所以超长前导零输入仍抛原生 `ValueError`（3.13.2 已复现，见上）。新增测试 `"9" * 5000` 只覆盖“有效数字过多”的情况；在 3.9 下即使不修也能通过，因此无法防止回归。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| — | — | — | 本轮无新发现。B1 的其余内容（锁等待与超时、配置校验、来源记录、文档、PLAN A9 顺序）复核后无问题。 | — |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B1-R2-1 | fixed（待负责人决定是否开第 4 轮复核） | `src/config/models/pipeline.py` 改为 `int(raw_timeout.lstrip("0") or "0")`，不再对含前导零的长字符串调用 `int()`；新增 `test_long_zero_padded_lock_timeout_is_parsed_without_long_int_conversion`（`"0"*5000+"5"` → 5，`"0"*5000` → 0），用 monkeypatch 模拟 3.11+ 的 `int()` 长度限制。已验证：撤销修复后该测试 2 failed，恢复后通过。 |

- Round result: `escalated`
- 升级说明：B1 已进行 3 轮审查，`B1-R2-1`（should-fix）仍未解决，按 `agent/AGENTS.md` 轮次上限交 Reporter 报告负责人。双方对问题本身没有分歧：Analyst 已认可该问题并做了修复，只是修复不完整。剩余工作很小：把 `int(raw_timeout)` 改为对去零后的字符串转换，即 `int(raw_timeout.lstrip("0") or "0")`；另外加 `"0" * 5000 + "5"` 和 `"0" * 5000` 两个测试用例，按现有“允许前导零”的规则，二者应分别接受为 `5` 和 `0`；若决定拒绝超长输入，则必须报 `ConfigError`，不能抛原生 `ValueError`。注意在 3.9 下这两个用例即使不修也能通过，无法证明修复有效；要防止回归，可在测试中把 `int` 换成会拒绝超长字符串的替身（monkeypatch），或加一个仅在 Python ≥3.11 上运行的用例。其余 must-fix/should-fix 均已解决；R1-3 至 R1-6 为已采纳的 suggestion，R1-7 转 B4。建议负责人批准再修一轮（第 4 轮）以完成收敛。

## Block B2 · Round 1 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `45527fd`（审查 `git diff 52bd831..ee1ddf6` 中的 B2 部分，及 `52bd831` 中 `src/data_io/layout.py` 对 `manifests/ledger.sqlite3*` 的保留名检查）；files: `src/data_io/ledger.py`、`tests/test_ledger.py`、`src/data_io/layout.py`（保留名检查）。审查时分支已前进到 `b8d1c69`（B1 修复与 B4），但 `git diff --stat ee1ddf6..HEAD` 显示上述 B2/B3 文件未变；B4 内容不在本轮范围。
- 审查方式：在 `/private/tmp/pr2-review-b2b3` 以 `git worktree add --detach ee1ddf6` 检出运行，结束后已移除；Python 3.9 检查使用临时 venv `/private/tmp/pr2-review-venv39`，已删除。
- Checks run by Reviewer（worktree 内）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 28 files already formatted
  - `uv run pytest tests/ -q` → 402 passed in 5.65s
  - `uv run pytest tests/test_ledger.py tests/test_runs.py -q` → 29 passed
  - `UV_PROJECT_ENVIRONMENT=/private/tmp/pr2-review-venv39 uv run --python 3.9 pytest tests/ -q`（CPython 3.9.6，SQLite 3.43.2）→ 402 passed
  - 探测脚本（`PYTHONPATH=. uv run python <scratchpad>/probe*.py`，结果见各条发现）：大小写不同路径重复登记、只读连接与写事务并发、`ROLLBACK` 行为。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| — | — | 首轮，无此前发现。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B2-R1-1 | must-fix | `src/data_io/ledger.py:429-457`（路径检查与重复判断） | 重复登记只按字符串 `path` 判断。在 macOS 默认的大小写不敏感 APFS 上，`silver/trades/a.parquet` 与 `silver/trades/A.parquet` 是同一个文件，但两者都能登记成功：探测结果 `manifests()` 为 `['silver/trades/A.parquet', 'silver/trades/a.parquet']`，`rows_written` 变为 2，同一 checkpoint 也推进两次。`target.resolve()` 在 macOS 上不会规范大小写，所以检查拦不住。通过 `Run.commit_file` 也能触发：`write_new` 遇到大小写不同但内容相同的已存在文件时走“相同内容重试”分支并返回成功，随后账本登记第二条。这违反验收要求“同一路径重复登记被拒绝”，下游按 manifest 读取时会把同一份数据读两遍，即 FOUNDATION_RULES §8 所说的“不受控重复”。 | 以文件身份而不是字符串判重：例如在 `manifest_files` 中保存 `(st_dev, st_ino)` 并设 UNIQUE 约束；或在登记前确认各级目录中确实存在完全同名（区分大小写）的条目（`os.listdir(parent)` 包含 `name`），否则拒绝。补一个大小写变体测试（在大小写敏感的文件系统上跳过或改用 inode 断言）。 |
| B2-R1-2 | should-fix | `src/data_io/ledger.py:204-219`（`open_read_only`）、`:188-189`（busy timeout） | 并发行为没有测试，也没有记录。(a) `mode=ro` 的只读连接只要处在读事务中，写连接的 `BEGIN IMMEDIATE` 就会立刻失败，报误导性的 `disk I/O error`，不管 timeout 设为 0 还是 5 都一样（探测：`Cannot start ledger transaction: disk I/O error`；不带 `mode=ro` 的普通读连接则在 `COMMIT` 时得到 `database is locked`）。B4 的 audit 正是用这个只读入口；与正在运行的任务同时执行时，会让该任务“文件已发布、登记失败”。(b) SQLite busy timeout 直接复用 `lock_timeout_seconds`，默认值 0 意味着任意两个连接的短暂重叠都会立即失败。这个选择不在 PLAN 的 D/A 决定表中。 | 把“账本 busy timeout 取值”记为 Agent 决定（写明依据与风险）。为只读连接与写事务并发补测试，断言写方得到清楚的 `LedgerError`（例如“账本正被读取/锁定”），不要出现 `disk I/O error`。可考虑只读打开不用 `mode=ro`，改为普通连接加 `query_only` 和 busy timeout；或让 audit 持有 writer 锁；或为账本事务设一个与 writer 锁无关的短暂最小等待。至少在 ADR-003 中说明这一限制。 |
| B2-R1-3 | should-fix | `src/data_io/ledger.py:281-287`（`_transaction` 的异常分支） | 出错分支无条件执行 `connection.execute("ROLLBACK")`。SQLite 在 `SQLITE_FULL`、`SQLITE_IOERR` 等错误后可能已自动回滚；这时 `ROLLBACK` 本身会抛 `cannot rollback - no transaction is active`，这个异常不是 `LedgerError`，还会掩盖真正的根因（磁盘满或 I/O 错误）。而这恰好是崩溃或磁盘问题时最需要的信息。`COMMIT` 分支已用 `in_transaction` 做了保护，两处处理不一致。 | 出错分支同样只在 `connection.in_transaction` 时回滚，并把回滚自身的失败附在原异常上（例如 `from exc`，或在消息里同时列出两者），保证对外只抛 `LedgerError` 且保留原因。可用 mock 连接补一个“语句失败后事务已不存在”的测试。 |
| B2-R1-4 | suggestion | `src/data_io/ledger.py:246-256` | 没有核对 `PRAGMA journal_mode = DELETE` 的返回值。如果账本曾被外部工具改为 WAL，并且仍有其他连接打开，切换会静默失败（SQLite 会返回 `wal`），A1 声明的模式就不成立。 | 读取返回值，不是 `delete` 时拒绝打开并说明原因。 |
| B2-R1-5 | suggestion | `src/data_io/ledger.py:437`、`:473`；`:517-519` | `registered_at`/`updated_at` 在 `BEGIN IMMEDIATE` 之前取值，等锁后可能早于真正提交的时间；`checkpoint_history` 先按 `updated_at` 排序，墙钟回拨时会与 version 顺序不一致。另外，`watermark` 允许后退，checkpoint key 也不与 dataset 关联。 | 在事务内取时间；history 排序改为 `checkpoint_key, version`。考虑拒绝 watermark 后退（cursor 是不透明值，可以不比较）。 |
| B2-R1-6 | suggestion | `src/data_io/layout.py:401` | 保留名检查区分大小写。在大小写不敏感的文件系统上，REGISTRY writer 仍能创建 `manifests/LEDGER.SQLITE3-JOURNAL`，SQLite 会把它当作同名的 hot journal。影响有限（REGISTRY 是内部角色，且内容无效的 journal 会被忽略），但与 B2-R1-1 是同一类问题。 | 用 `relative.name.casefold().startswith("ledger.sqlite3")` 判断。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B2-R1-1 | fixed | `Ledger.commit` 逐级用 `os.listdir` 核对路径各段与磁盘目录项完全一致，否则拒绝；`test_case_variant_path_cannot_register_the_same_file_twice`（大小写敏感文件系统上 skip）。 |
| B2-R1-2 | fixed | 已复现：`mode=ro` 读者持锁时写者报 `disk I/O error`。只读连接改为普通连接 + `query_only`；SQLite busy timeout 取 `max(writer_lock_timeout_seconds, 5)`（`MIN_BUSY_TIMEOUT_SECONDS`），记为 PLAN A10 与 ADR-003；`test_concurrent_reader_does_not_fail_a_commit`（读者在另一线程持有读事务 0.5 秒，写者等待后成功）。普通连接会回滚遗留日志，因此另加回滚日志时拒绝只读打开（见 B4-R1-1）。`test_held_ledger_lock_fails_without_change` 将最小等待设为 0 以保持测试速度。 |
| B2-R1-3 | fixed | `_transaction` 只在 `in_transaction` 时 ROLLBACK，ROLLBACK 失败时报包含原因的 `LedgerError`；`test_rollback_after_sqlite_auto_rollback_keeps_original_error`。 |
| B2-R1-4 | fixed（采纳） | 读取 `PRAGMA journal_mode = DELETE` 的结果，不是 `delete` 时拒绝；`test_non_delete_journal_mode_is_rejected`。 |
| B2-R1-5 | fixed（采纳） | `registered_at`/`updated_at` 在事务内取得；历史按 `checkpoint_key, version` 排序；watermark 后退或去掉时拒绝且不登记；`test_watermark_cannot_move_backwards_or_disappear`。 |
| B2-R1-6 | fixed（采纳） | 保留名检查用 `casefold()`。 |

上述新测试在撤销 `ledger.py` 修复后 6 个失败、恢复后通过（Analyst 实际运行）。

- Round result: `changes requested`

## Block B3 · Round 1 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `ee1ddf6`（`git diff 45527fd..ee1ddf6`）；files: `src/data_io/runs.py`、`tests/test_runs.py`。截至审查时 HEAD `b8d1c69` 中这两个文件未改动。
- Checks run by Reviewer：与 B2 第 1 轮相同（同一个 `ee1ddf6` worktree）：ruff check 通过；format check 通过；全量 `pytest` 402 passed（Python 3.9.6 下同样 402 passed）；`tests/test_runs.py` 包含在 29 个定向测试中。另运行探测脚本，结果见各条发现。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| — | — | 首轮，无此前发现。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B3-R1-1 | must-fix | `src/data_io/runs.py:177-196`（`finish` 的 `finally: close()`）、`:213-217`（`__exit__` 的 `except LedgerError: return`） | `finish` 无论哪一步失败都会关闭账本连接，`__exit__` 又把任何 `LedgerError` 都当成“finish 已执行”，直接静默返回。结果：(1) `finish("failed")` 不带 error 时，`finish_run` 校验失败，连接被关闭，运行永远停在 `running`。探测：上下文退出后状态仍为 `running`，且没有任何“无法记录失败”的日志。(2) 默认 timeout 为 0 时，如果另一个连接正占用账本，`__exit__` 中的 `get_run` 会因 busy 失败，同样静默返回。探测：异常退出时账本被锁，运行保持 `running`。这违反硬规则 2（失败不能静默），也违反 B3 验收“异常退出记为 failed 并保留错误”。 | 在 `Run` 上显式记录状态（例如 `_finished`、`_closed`），不要靠“连接已关闭”的异常来推断。参数校验（status、error 类型和非空）放在任何账本操作之前，校验失败不关闭连接。只在最终状态已写入后才关闭连接。`__exit__` 无法记录失败时必须 `logger.exception`；在没有原始异常时，还要抛出错误。补测试：`finish("failed")` 不带 error、账本被锁时的异常退出，两者都应最终记为 failed，或至少响亮报错并留下日志。 |
| B3-R1-2 | must-fix | `src/data_io/runs.py:109-129`；`tests/test_runs.py:88-99` | PLAN B3 的验收要求“参数不能 JSON 序列化时在任何副作用前拒绝”，但 `Ledger.open(layout)` 在 `create_run` 校验参数、task、时间等之前就执行了：账本文件和表结构已被创建（探测：非法参数被拒绝后，`manifests/ledger.sqlite3` 已存在；空 `task` 也要在打开账本之后才被拒绝）。现有测试恰好依赖这个副作用：只有非法 `Run.start` 已经建好账本，`Ledger.open_read_only(tmp_path)` 才不会返回 None。 | 在 `Ledger.open` 之前完成全部输入校验：参数用 `json_text` 预检，task/version/venue/dataset 预检非空，range 预检 UTC 与先后顺序。可把 `create_run` 的校验抽成纯函数复用。测试改为断言非法输入后 `manifests/ledger.sqlite3` 不存在。 |
| B3-R1-3 | should-fix | `src/data_io/runs.py:139-164`；`tests/test_runs.py:76-85`、`:102-110` | `commit_file` 先发布文件、后校验，制造了本可避免的未登记文件：(1) 运行结束后再调用 `commit_file`，文件仍被发布（探测：报错 `Cannot start ledger transaction: Cannot operate on a closed database`，但 `silver/trades/a` 已存在）；(2) dataset 未知、路径不在对应层、facts 或 checkpoint 字段非法，这些都能在写盘前判断。测试也是因为错误的原因通过：`test_no_commit_after_finish_and_no_double_finish` 中两个 `pytest.raises(LedgerError)` 实际捕获的是“连接已关闭”，而不是“运行已结束”。另外，`write_new` 走“相同内容重试”分支后若账本报“已登记”，日志会写“published file was not registered”，与事实不符。 | 在 `write_new` 之前检查运行是否仍在进行（用 B3-R1-1 的显式状态），并调用一个与 `Ledger.commit` 共用的纯校验函数校验 facts、checkpoint 和 dataset 与路径层级的对应关系；发布后只剩重新计算哈希和事务两步。测试改为匹配具体消息（如 `already succeeded`、运行已结束），并断言不产生文件。登记失败时的日志区分“已登记”与“未登记”。 |
| B3-R1-4 | should-fix | `src/data_io/runs.py:95-137` | `Run.start` 不检查 `config` 与 `layout` 是否对应同一个数据目录。探测：用 DATA_ROOT=A 的 config 和 root=B 的 layout 启动，`record.json` 记录的 `data_root` 是 A，而数据和账本实际都在 B，审计记录与事实不符。`writer_lock_timeout_seconds` 与 `layout.lock_timeout_seconds` 同样可能不一致。 | 在任何副作用之前校验 `config.data_root.resolve() == layout.root`，以及 `config.writer_lock_timeout_seconds == layout.lock_timeout_seconds`，不一致时拒绝；补测试。 |
| B3-R1-5 | suggestion | `src/data_io/runs.py:177-182` | `finish` 不校验 `error` 的类型（探测：`error=123` 被原样存为整数）；`succeeded` 状态也可以带 error。 | `error` 要求为 `str` 或 None；只允许 `partial`/`failed` 带 error，或在 report 中明确显示。 |
| B3-R1-6 | out-of-scope | `src/data_io/runs.py:183-190`；PLAN A7 | A7 写明“记录内容完全来自账本，可重新生成”，但没有为“已结束、record 缺失或只写了一半（`record.json` 已发布、`report.md` 失败）”的运行提供重新发布的入口；`set_record_path` 也不会被补上。 | 交给 B4 或后续 PR：提供 `publish_record(ledger, layout, run_id)`，对已结束且缺记录的运行补发，并由 audit 给出提示。 |
| B3-R1-7 | out-of-scope | `src/data_io/runs.py:220` | 错误文本 `f"{type(exc).__name__}: {exc}"` 原样写入账本、`record.json` 和 `report.md`（Analyst 已列为已知限制）。PR3 接入真实来源后，HTTP 库的异常消息可能包含带凭据的 URL，触及硬规则 5。 | PR3 引入 adapter 时统一脱敏异常文本（例如去掉 URL query、已知 secret 环境变量的值），并加测试。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B3-R1-1 | fixed | `Run` 用显式 `_state`；`finish` 先校验参数，再写最终状态，成功后才关闭连接；写状态失败时运行保持打开可重试。`__exit__` 无法记录失败时写 `run.finish_failed` 日志，没有原异常时抛 `LedgerError`；`test_invalid_finish_arguments_keep_run_open`、`test_unrecordable_exit_is_logged_and_raised`。 |
| B3-R1-2 | fixed | 抽出 `ledger.run_values()`，`Run.start` 在 `Ledger.open` 前校验全部字段；`test_invalid_start_has_no_side_effect` 断言 `ledger.sqlite3` 和 `manifests/runs` 均不存在。 |
| B3-R1-3 | fixed | 抽出 `ledger.commit_values()`；`commit_file` 在发布前检查运行状态、参数和账本中的运行状态；日志改为 “file was published but registration failed”。`test_no_commit_after_finish_and_no_double_finish`（断言具体消息且未创建文件）、`test_invalid_commit_is_rejected_before_publishing`；发布后仍可能失败的情况（checkpoint 版本过期）由 `test_registration_failure_after_publication_leaves_file_unregistered` 覆盖。 |
| B3-R1-4 | fixed | `Run.start` 拒绝 config 的 `DATA_ROOT`（解析后）与 layout 根目录不同，或锁等待秒数不同；在任何副作用前检查，测试同上。 |
| B3-R1-5 | fixed（采纳） | `error` 必须为字符串，只允许用于 `partial`/`failed`。 |
| B3-R1-6 | 转 Reporter | 记录重新发布暂不实现；`audit` 会报告 `run_record_missing`。建议后续 PR 增加按账本重建记录的命令。 |
| B3-R1-7 | 转 Reporter | PR3 接入真实来源时对异常文本脱敏。 |

- Round result: `changes requested`

## Block B4 · Round 1 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `b8d1c69`；files: `src/data_io/audit.py`、`src/cli.py`、`tests/test_audit.py`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`（新）、`agent/PROJECT.md`、`docs/FOUNDATION_RULES.md`、`docs/adr/ADR-001-v1-architecture.md`、`docs/README.md`、`README.md`、`CHANGELOG.md`、`src/config/README.md`、`src/config/README_FOR_DEVELOPER.md`、`src/config/developing.md`。`git show b8d1c69 --stat` 为 13 个文件，与 revision packet 一致。
- 审查方式：在 `/private/tmp/pr2-b4-review` 以 `git worktree add --detach b8d1c69` 检出运行检查，结束后已移除。B2（`ledger.py`）、B3（`runs.py`）只作背景；主工作区中审查期间出现的 `src/data_io/{audit,layout,ledger}.py` 未提交改动不在本轮审查范围内。
- Checks run by Reviewer（均在上述 worktree 内）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -q` → 408 passed in 6.31s
  - `uv run pytest tests/test_audit.py -v` → 3 passed
  - 临时探测脚本（scratchpad，未入库）：
    - **hot journal**：先在账本中提交 3000 行，再用 `cache_size=2` 的写事务触发 cache spill 后 `os._exit(9)`，`ledger.sqlite3-journal` 头为 `d9d505f920a163d7`（确为 hot journal）。`main(["audit"])` 返回 2，stderr 为 `pipeline audit failed: Cannot open ledger … read-only: attempt to write a readonly database`；整个 `DATA_ROOT` 的 size/mtime/SHA-256 快照前后完全一致，journal 未被回滚或删除。“不写任何文件”成立。
    - **没有 `manifests/` 的根目录**（只有 `silver/`）：返回 0，`ledger: absent`，目录不变。
    - 账本是目录 → 2（`Ledger must be a regular file`）；账本是垃圾字节 → 2（`file is not a database`）。
    - `DATA_ROOT` 名含空格、`#`、`?`、`%20` 或中文时，`as_uri()?mode=ro` 正常打开，`ok: true`。
    - `gold` 本身是指向 `DATA_ROOT` 外目录的软链接 → 返回 1，只报 `unregistered_file: gold/x`，没有 `unexpected_symlink`（见 B4-R1-2）。
    - 已登记文件权限为 `000` → 整个 audit 返回 2（`Permission denied`），其他问题都不再输出（见 B4-R1-5）。
    - `manifests/runs/.partial-zzz`、`quarantine/.partial-q`、`recovery/partials/orphan.json`（无 `.bin`）→ 均不报告（见 B4-R1-6）。
  - 文档一致性：`git grep -n -i postgres b8d1c69 -- . ':!docs/pr2'`。README、PROJECT §3/§6、FOUNDATION_RULES、ADR-003、`developing.md`、`ledger.py` 都写“SQLite，以后可换 PostgreSQL”，一致。ADR-001 正文仍写 PostgreSQL，但开头已注明由 ADR-003 补充，作为历史决定可以接受。`git grep -E "PR ?2|run registry"` 只在 ADR-002 中发现一处旧表述（见 B4-R1-7）。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R1-7 | resolved | `CHANGELOG.md:10` 新增 `writer_lock_timeout_seconds` 条目（0–3600，默认 0）；`docs/adr/ADR-003-pr2-sqlite-ledger.md:21-23` 记录 D2：默认 0 保持立即失败、超时报错且数据不变，扫描范围不缩小。ADR-002 本身没有指向 ADR-003 的后续说明，另列为 B4-R1-7（suggestion）。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B4-R1-1 | should-fix | `src/cli.py:39-54`；`src/data_io/ledger.py:205-216`（`open_read_only`，由 audit 调用）；`README.md:85`；`src/config/README.md:52-55`；`tests/test_audit.py` | 账本有 hot journal（写进程在事务中被杀）时，audit 返回 2，提示 `attempt to write a readonly database`。只读命令出现“写数据库”的报错容易误导，没有说明原因（中断的账本事务），也没有说明处理方法（打开写连接即可由 SQLite 回滚）。这正是 audit 最需要的场景：崩溃之后检查状态，但此时 audit 恰好无法运行。revision packet 把它列为已知限制，但 README、`src/config/README.md` 和 ADR-003 都没写；测试也没有覆盖“账本错误 → 2 且不写入”（现有退出码 2 只测了 `DATA_ROOT` 不存在）。 | 打开失败且存在 `ledger.sqlite3-journal` 时，给出明确错误，例如“账本有未完成的事务日志（上次写入被中断）；只读 audit 不会回滚它，请先运行一个写任务或打开账本让 SQLite 回滚”。在 README 和 `src/config/README.md` 的 audit 说明及排错表中写上这条限制。加测试：构造 hot journal（或至少 `user_version` 不符、账本非数据库），断言 `main(["audit"]) == 2`，并且 `DATA_ROOT` 快照（含 journal）不变。 |
| B4-R1-2 | should-fix | `src/data_io/audit.py:35-37`（`_walk`）、`:62-69` | `_walk` 用 `directory.exists()` 判断，而 `os.walk(top, followlinks=False)` 仍会进入本身就是软链接的 `top`。所以 `bronze/`、`silver/` 或 `gold/` 整个层是软链接时，不报 `unexpected_symlink`，而是遍历 `DATA_ROOT` 外的目录，把那里的文件报成 `gold/x` 之类的 `unregistered_file`（探测：返回 1，只有 `unregistered_file`）。同样，已登记文件只检查最后一级是否为软链接，`root / entry["path"]` 经过软链接父目录时会被当作正常文件哈希通过。这与模块说明“报告 unexpected symbolic link”不符，也违背硬规则 8 的“数据位于 `DATA_ROOT` 下”。 | 遍历前对每个层根和 `recovery/` 先做 `is_symlink()` 检查：是软链接就报 `unexpected_symlink` 并跳过。manifest 检查改用 `path.resolve(strict=True) == path`（或逐级 `lstat`），父目录有软链接时报 `manifest_file_not_regular`。加对应测试。 |
| B4-R1-3 | should-fix | `src/data_io/audit.py:51-57`、`:77-88`；`README.md:85`；`src/config/README.md:55`；ADR-003 | audit 不持写锁，也不在同一个读事务中读 `manifests()` 和 `runs()`（`isolation_level=None`，每条 SELECT 各自一个快照），文件遍历和账本读取之间也没有先后保证。有写任务在跑时，audit 会报出暂时性的 `unregistered_file`、`partial_file`、`run_unfinished`，甚至两次查询之间状态不一致；而且按 B2-R1-2 的探测，audit 的 `mode=ro` 读事务还可能让并发写任务的 `BEGIN IMMEDIATE` 报 `disk I/O error`。文档只说“只读”，没有说明 audit 需要在没有写任务时运行，结果才可信。 | 至少在 README、`src/config/README.md` 和 ADR-003 中写明：audit 是快照，应在没有写任务时运行；有写任务时的结果可能有暂时性问题，并可能干扰写任务（引用 B2-R1-2）。代码上可以把两次查询放进同一个 `BEGIN`…`COMMIT` 读事务，或者以只读方式打开已有的 `.writer.lock` 并加锁（不创建该文件），锁被占用时报告“有写任务正在运行”。 |
| B4-R1-4 | should-fix | `tests/test_audit.py:56-85`、`:88-98` | 测试只证明 `audit()` 函数不写入，没有证明 CLI 路径（`main(["audit"])`，包括配置加载、日志和 `validate_for_read()`）不写入。快照只比较 size 和 mtime，不比较内容。PLAN B4 验收要求“不创建目录、不写任何文件”和“没有账本时报告清楚”，但没有测试检查报告里 `ledger: "absent"` 时 CLI 返回 0 并有 JSON 输出，也没有测试检查 `manifest_file_not_regular`（例如已登记路径被换成软链接或目录）。 | 在 `test_every_mismatch_is_reported_without_writes` 中对同一目录再调用一次 `main(["audit"])`，断言返回 1，快照不变（快照可加上 SHA-256）。补充 `manifest_file_not_regular` 和 CLI 在无账本时的用例。B4-R1-1、B4-R1-2 的测试也一并加入。 |
| B4-R1-5 | suggestion | `src/data_io/audit.py:69`；`:37`（`onerror=fail`） | 只要有一个已登记文件不可读（`PermissionError`），或遍历中有一个目录不可读，整个 audit 就以 2 退出，其他问题都不再报告（探测：权限 `000` 的文件 → 返回 2）。崩溃后排查时，可见的问题越完整越好。 | 对单个文件的 `OSError` 记为 `manifest_file_unreadable` / `scan_error` 并继续，最终返回 1；只有账本或配置错误才返回 2。 |
| B4-R1-6 | suggestion | `src/data_io/audit.py:92-94`；`:77-88` | (a) `recovery/` 中只报 `.bin`：只有 sidecar `.json` 没有 payload 的不完整恢复（README 说初始化时会记日志供审查），以及 `recovery/` 下的其他文件或软链接，都不报告。(b) `.partial-*` 只在 bronze/silver/gold 中检查；`manifests/runs/<run_id>/` 中发布记录时遗留的 partial 不报（`DataLayout.create()` 的 `_recover_partials` 会扫描所有层）。`run_record_missing` 能覆盖大部分情况，但 README 写的是笼统的“abandoned partials”。(c) `run_record_missing` 只检查 `record.json` 是否存在，用 `is_file()` 会跟随软链接，也不检查默认开启的 `report.md`（与 B3-R1-6 相关）。 | 报告 `recovery_metadata_without_payload`、`recovery` 中的非预期文件，以及 `manifests/` 下的 partial；或在文档中写明 audit 只检查哪些层的 partial。记录检查改用 `lstat`。 |
| B4-R1-7 | suggestion | `docs/adr/ADR-002-pr1-foundation.md:11` | ADR-002 仍写“带超时等待和缩小扫描范围留待 PR2”，但没有指向已实现它的 ADR-003。ADR-001 已加“由 ADR-003 补充”的说明，ADR-002 没有。 | 在 ADR-002 开头或该句后加“超时等待已由 ADR-003 实现（默认仍为 0）；扫描范围按 agent 决定未缩小”。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B4-R1-1 | fixed | 只读打开前检查 `ledger.sqlite3-journal`，存在时报清楚的 `LedgerError`（说明原因和处理方法），不交给 SQLite；`test_rollback_journal_is_refused_without_writing` 验证 CLI 返回 2、提示 “rollback journal”、所有文件内容哈希不变。README、`src/config/README.md`、ADR-003 已写明。 |
| B4-R1-2 | fixed | 层目录本身是软链接时报 `unexpected_symlink` 且不遍历；已登记文件的父目录含软链接时报 `manifest_file_not_regular` 且不计算哈希；`test_symlinks_are_reported_not_followed`。 |
| B4-R1-3 | fixed | `Ledger.snapshot()` 在一个读事务中取 manifests 和 runs；文档与 docstring 写明须在无写任务时运行；读写冲突由 B2-R1-2 的修复处理。 |
| B4-R1-4 | fixed | 快照加入文件内容 SHA-256；`test_cli_writes_nothing_and_reports_absent_ledger`（CLI 路径不写、无账本时输出 `absent`）；`manifest_file_not_regular` 由软链接测试覆盖。 |
| B4-R1-5 | fixed（采纳） | 无法读取的已登记文件报 `manifest_file_unreadable` 并继续；`test_recovery_partials_and_unreadable_files_are_reported`。 |
| B4-R1-6 | fixed（部分采纳） | 报告 `recovery_metadata_without_payload`、`recovery_unexpected_file`、`manifests/` 下的 partial；`run_record_missing` 不跟随软链接。`report.md` 可由任务关闭，不作为缺失检查。 |
| B4-R1-7 | fixed（采纳） | ADR-002 头部增加指向 ADR-003 的“后续”行（与 ADR-001 的处理方式一致，不改正文）。 |

- Round result: `changes requested`

Analyst 检查（B2/B3/B4 修复后，主工作区）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 30 files already formatted；`uv run pytest tests/ -q` → 420 passed。

## Block B4 · Round 2 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `1167712`；本块相关文件：`src/data_io/audit.py`、`src/data_io/ledger.py`（`open_read_only`、`snapshot`、`MIN_BUSY_TIMEOUT_SECONDS`）、`tests/test_audit.py`、`README.md`、`src/config/README.md`、`docs/adr/ADR-002-pr1-foundation.md`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`。`src/cli.py` 在 `b8d1c69..1167712` 中没有改动。同一提交中 B2/B3 的其他改动只作背景。
- 审查方式：在 `/private/tmp/pr2-b4-review-r2` 以 `git worktree add --detach 1167712` 检出，结束后已移除。探测数据只放在本会话 scratchpad 的专用目录中，结束后按确切路径删除。
- Checks run by Reviewer（均在上述 worktree 内）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -q` → 420 passed in 6.65s
  - `uv run pytest tests/test_audit.py -q` → 7 passed
  - 临时探测脚本（scratchpad，未入库）。每项都对 `DATA_ROOT` 做含 SHA-256 的快照，在 `main(["audit"])` 前后比较：
    1. 真实 hot journal（cache spill 后 `os._exit(9)`，头为 `d9d505f920a163d7`）→ 返回 2，提示 “rollback journal …”，快照无差异。
    2. **WAL 模式账本**（外部执行 `PRAGMA journal_mode=wal` 后关闭，WAL 标志留在文件头中）→ 返回 0，但 audit 之后新出现 `manifests/ledger.sqlite3-shm`（32768 字节）和 `manifests/ledger.sqlite3-wal`（0 字节），`manifests/` 目录的 mtime 也变了（见 B4-R2-1）。
    3. 写连接持有 `BEGIN IMMEDIATE` 且已有未提交的 UPDATE（此时还没有 journal 文件）→ audit 返回 0，耗时约 0s，读到的是提交前的状态。
    4. 只读快照：audit 连接持有读事务 1 秒，其间另一线程执行 `Run.start` + `finish` → 写者等待约 1.12s 后成功。B2-R1-2 的修复在 audit 场景下有效。
    5. 账本权限 0444、`manifests/` 权限 0555 → 返回 0，快照无差异。
    6. `bronze/locked` 目录权限 000 → 整个 audit 返回 2（`Permission denied`），见 B4-R2-3。
    7. `manifests/` 是指向同设备目录的软链接 → 返回 1，报告 `unexpected_symlink: manifests`，但 `ledger: present`：账本是经由该软链接读取的，见 B4-R2-3。
    8. 0 字节的 `ledger.sqlite3-journal`（不是 hot journal）→ 返回 2。这是保守处理，可以接受。
    9. 普通 `sqlite3.connect()` 打开不存在的路径并执行 `PRAGMA query_only`、`PRAGMA user_version` → 创建了 0 字节文件；`file:…?mode=rw` 则报 `unable to open database file`，不会创建（见 B4-R2-2）。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B4-R1-1 | resolved | `ledger.py` 的 `open_read_only` 在连接前检查 `-journal`（含软链接），报错说明原因和处理方法；探测 1 中真实 hot journal 返回 2 且快照无差异；`test_rollback_journal_is_refused_without_writing` 通过；README、`src/config/README.md`、ADR-003 已记录。 |
| B4-R1-2 | resolved | `audit.py` 中层根（含 `manifests`、`recovery`）是软链接时，报 `unexpected_symlink` 且不遍历；`_has_symlinked_parent` 对已登记文件报 `manifest_file_not_regular`；`test_symlinks_are_reported_not_followed` 通过。账本本身仍会经由软链接读取，另见 B4-R2-3。 |
| B4-R1-3 | resolved | `Ledger.snapshot()` 在一个 `BEGIN`…`COMMIT` 读事务中读取；README、`src/config/README.md` 和 `audit()` 的 docstring 都写明须在没有写任务时运行；探测 4 显示读事务不再让写者失败。 |
| B4-R1-4 | resolved | `_snapshot` 加入了内容哈希；`test_cli_writes_nothing_and_reports_absent_ledger` 覆盖 CLI 不写入和 `ledger: absent`；软链接测试覆盖 `manifest_file_not_regular`。 |
| B4-R1-5 | partially resolved（suggestion，不阻塞） | 不可读的已登记文件改报 `manifest_file_unreadable` 并继续（测试通过）；但不可读的目录仍使整个 audit 返回 2（探测 6），见 B4-R2-3。 |
| B4-R1-6 | resolved | 新增 `recovery_metadata_without_payload`、`recovery_unexpected_file`，并报告 `manifests/` 下的 partial；记录检查不再跟随软链接。不检查 `report.md` 的理由（任务可关闭它）合理。 |
| B4-R1-7 | resolved | ADR-002 头部增加了“后续：写锁等待已由 ADR-003 实现”。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B4-R2-1 | should-fix | `src/data_io/ledger.py`（`open_read_only`，普通连接 + `query_only`）；`src/data_io/audit.py:1-5` 的 docstring；README、`src/config/README.md` 中的“不写任何文件” | 改为普通读写连接后，“audit 永不写入”只在账本为 DELETE 模式时成立。账本如果被外部工具切到 WAL（这正是 B2-R1-4 的场景；写路径的 `_configure` 现在会拒绝，但 WAL 标志会持久保存在文件头中），audit 会创建 `ledger.sqlite3-shm` 和 `ledger.sqlite3-wal`，并在退出后留下（探测 2：返回 0，`manifests/` 多出两个文件，目录 mtime 改变）。以前的 `mode=ro` 不会这样。现在的 journal 检查只看 `-journal`，看不到这种情况。 | 打开前读取文件头第 18、19 字节（WAL 时为 2）；或者在 `-journal` 之外，`-wal`/`-shm` 存在时也拒绝；更稳妥的是先读文件头，非 DELETE（legacy）模式就以 `LedgerError` 拒绝并说明原因，然后才连接。加测试：WAL 账本 → 返回 2 且快照不变。 |
| B4-R2-2 | suggestion | `src/data_io/ledger.py`（`open_read_only` 中 `_check_file` 之后的 `sqlite3.connect(str(path), …)`） | 先检查后打开存在两个竞态窗口。(a) 检查通过后，账本恰好被移走或删除，普通 `connect` 会新建一个 0 字节的 `ledger.sqlite3`（探测 9）。(b) 检查 `-journal` 之后，写者在打开前崩溃，留下 hot journal，普通连接的第一次读取就会回滚它。窗口都很窄，并且 (b) 的回滚正是 SQLite 的标准恢复，但 docstring 和文档写的是“never creates, changes, or deletes anything”这样的绝对表述。 | 用 `sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, …)`：它不会创建文件，也不会引发 B2-R1-2 中 `mode=ro` 的问题。打开后、第一次读之前再检查一次 `-journal`。或者在文档中把 (b) 写成已知的残留窗口。 |
| B4-R2-3 | suggestion | `src/data_io/audit.py:37`（`_walk` 的 `onerror=fail`）；`ledger.py` 的 `_check_file` 只检查最后一级路径 | (a) 遍历中只要有一个目录不可读，整个 audit 仍以 2 退出，其他问题都不输出（探测 6；B4-R1-5 的剩余部分）。(b) `manifests/` 本身是软链接时，audit 正确报告 `unexpected_symlink: manifests`，但账本仍经由该软链接读取（`ledger: present`），与 README 中“symbolic links (never followed)”的表述不完全一致；`_require_same_device` 只能挡住跨设备的情况。 | (a) 把目录扫描错误记为 `scan_error` 并继续。(b) `open_read_only` 发现 `manifests` 是软链接时拒绝或跳过账本；或在文档中注明“账本路径的父目录软链接只会被报告，不会被拒绝”。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B4-R2-1 | fixed | `Ledger.open_read_only` 连接前读取文件头第 18–19 字节，WAL 模式或存在 `-wal`/`-shm` 时拒绝；`test_wal_mode_ledger_is_refused_without_writing`（CLI 返回 2，文件内容哈希不变）。 |
| B4-R2-2 | fixed（采纳） | 只读连接改用 `file:…?mode=rw`，不会创建缺失文件；`test_read_only_open_never_creates_a_missing_ledger`。docstring 与文档写明剩余的窄窗口（审计期间写者崩溃）及须在无写任务时运行。 |
| B4-R2-3 | fixed（采纳） | 无法列出的目录报告 `scan_error` 并继续（`test_unreadable_directory_is_reported_and_audit_continues`）；`manifests/` 为软链接时拒绝打开账本（同上测试文件）。B4-R1-5 随之完整解决。 |

- Round result: `changes requested`

## Block B2 · Round 2 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `1167712`（`git diff ee1ddf6..1167712 -- src/data_io/ledger.py src/data_io/layout.py tests/test_ledger.py`）；files: `src/data_io/ledger.py`、`src/data_io/layout.py`、`tests/test_ledger.py`。B4 的改动（`audit.py`、`cli.py`、文档）不在本轮范围，只在与账本行为交叉处查看。
- 审查方式：在 `/private/tmp/pr2-review-b2b3-r2` 以 `git worktree add --detach 1167712` 检出运行，结束后已移除；Python 3.9 的临时 venv `/private/tmp/pr2-review-b2b3-r2-venv39` 也已删除。
- Checks run by Reviewer（worktree 内，默认解释器为 CPython 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -q` → 420 passed in 6.64s
  - `uv run pytest tests/test_ledger.py tests/test_runs.py -q -rs` → 37 passed（大小写测试在本机大小写不敏感的 APFS 上实际执行，没有被跳过）
  - `UV_PROJECT_ENVIRONMENT=/private/tmp/pr2-review-b2b3-r2-venv39 uv run --python 3.9 pytest tests/ -q` → 420 passed
  - 探测脚本（`PYTHONPATH=. uv run python <scratchpad>/probe_r2.py`）：通过 `Run.commit_file` 用大小写变体及 NFC/NFD 变体重复提交；只读打开时的 TOCTOU；`mode=rw` URI 连接的并发行为。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B2-R1-1 | resolved | `ledger.py:505-509` 逐级用 `os.listdir` 核对目录项名称。探测：通过 `Run.commit_file` 提交 `silver/trades/A.parquet` 被拒（`must match the file's exact name on disk`），manifest 只有 `a.parquet`；NFD 形式的 `café` 也被拒。`test_case_variant_path_cannot_register_the_same_file_twice` 在本机实际执行并通过。 |
| B2-R1-2 | resolved | 只读打开改为普通连接加 `query_only`（`ledger.py:318-320`）；busy timeout 为 `max(lock_timeout, MIN_BUSY_TIMEOUT_SECONDS=5)`，已记入 PLAN A10。`test_concurrent_reader_does_not_fail_a_commit` 证明读者持有读事务时写者会等待而不是失败。另一处行为见 B2-R2-1。 |
| B2-R1-3 | resolved | `ledger.py:389-401`：只在 `in_transaction` 时回滚，回滚失败时报出包含原因的 `LedgerError`；`test_rollback_after_sqlite_auto_rollback_keeps_original_error` 覆盖。`COMMIT` 失败分支中的 `ROLLBACK` 仍没有保护，见 B2-R2-3。 |
| B2-R1-4 | resolved | `ledger.py:358-362` 读取返回值，不是 `delete` 时拒绝；有测试覆盖。 |
| B2-R1-5 | resolved | 时间改在事务内取得（`:532`）；history 按 `checkpoint_key, version` 排序；watermark 后退或被去掉时拒绝且不登记（`:546-550`）。比较用的是 ISO 文本，所有值都由 `utc_text` 生成且固定为 `+00:00`，带微秒与不带微秒混合时字典序也正确（`+` < `.` < 数字），已核对。 |
| B2-R1-6 | resolved | `layout.py:404` 改用 `casefold()`。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B2-R2-1 | suggestion | `ledger.py:307-320`（`open_read_only`） | 只读打开先检查文件是否存在，再用普通 `sqlite3.connect(str(path))`。如果两步之间文件消失，`connect` 会创建一个空的 `ledger.sqlite3`。探测中模拟了检查通过但文件不存在的情况：报 `Unsupported ledger schema version 0`，同时留下了新文件。这与 B4“只读、不写任何文件”的要求冲突，但只在竞态时出现。 | 改用 `sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, ...)`。探测确认：`mode=rw` 不会创建缺失的文件（`unable to open database file`），也不会出现 `mode=ro` 的 `disk I/O error`（读者持有读事务时，写者的 `BEGIN IMMEDIATE` 正常）。 |
| B2-R2-2 | suggestion | `ledger.py:505-509` | 每次登记都要对路径的每一级目录执行 `os.listdir`。大型 Bronze/Silver 目录中有成千上万个文件时，一次回填的总开销接近 O(N²)。 | 可以只列一次直接父目录，并对上级目录做缓存；或使用 `os.scandir` 后提前结束。在 ADR-003 或 PLAN 的风险栏记录这一开销即可。 |
| B2-R2-3 | suggestion | `ledger.py:402-407` | `COMMIT` 失败分支中的 `ROLLBACK` 没有用 try 包住。如果它也失败，抛出的就是原生 `sqlite3.Error`，而不是 `LedgerError`，与 B2-R1-3 已修复的出错分支不一致。 | 与出错分支一样包住，报出包含两个原因的 `LedgerError`。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B2-R2-1 | fixed（采纳） | 同 B4-R2-2：`mode=rw`。 |
| B2-R2-2 | 转 Reporter | 逐级列目录的开销记为已知风险；建议真实回填 PR 中按目录缓存或只列父目录并测量。 |
| B2-R2-3 | fixed（采纳） | COMMIT 失败后的 ROLLBACK 也包装为 `LedgerError` 并保留原因。 |

- Round result: `converged`（所有 R1 的 must-fix/should-fix 已解决；本轮只有 suggestion；lint、format 和全量测试均由 Reviewer 亲自运行并通过）

## Block B3 · Round 2 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `1167712`（`git diff ee1ddf6..1167712 -- src/data_io/runs.py tests/test_runs.py`）；files: `src/data_io/runs.py`、`tests/test_runs.py`。
- Checks run by Reviewer：与 B2 第 2 轮相同（同一个 `1167712` worktree）：ruff check 通过；format check 通过（30 files）；全量 `pytest` 420 passed（Python 3.9.6），另以临时 3.9 venv 运行也是 420 passed。另运行探测脚本，结果见下。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B3-R1-1 | resolved | `runs.py` 引入显式 `_state`；`finish` 先校验参数，`finish_run` 成功后才转为 `closed`；`__exit__` 不再依靠异常推断状态，无法记录时写 `run.finish_failed` 日志，没有原异常时抛错。`test_invalid_finish_arguments_keep_run_open`、`test_unrecordable_exit_is_logged_and_raised` 覆盖。日志文案问题见 B3-R2-1。 |
| B3-R1-2 | resolved | `Run.start` 在 `Ledger.open` 之前调用 `run_values(**fields)`；`test_invalid_start_has_no_side_effect` 断言 `manifests/ledger.sqlite3` 与 `manifests/runs` 都不存在。 |
| B3-R1-3 | resolved | `commit_file` 发布前依次检查 `_require_running()`、`commit_values()` 和 `ledger.require_running()`；测试匹配具体消息并断言没有产生文件。发布后才可能出现的失败（checkpoint 版本过期）由 `test_registration_failure_after_publication_leaves_file_unregistered` 覆盖。 |
| B3-R1-4 | resolved | `Run.start` 在任何副作用前比较解析后的 `DATA_ROOT` 与 `layout.root`，以及两处锁等待秒数；有测试覆盖。 |
| B3-R1-5 | resolved | `error` 必须为字符串，且只能用于 `partial`/`failed`；有测试覆盖。 |
| B3-R1-6 | out-of-scope（未变） | 按约定交给 B4 或后续 PR。 |
| B3-R1-7 | out-of-scope（未变） | 按约定交给 PR3。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B3-R2-1 | should-fix | `runs.py` `__exit__` 的 `except LedgerError as finish_exc` 分支（日志 `cannot record failed run; it remains marked running in the ledger` 与随后抛出的 `... could not be recorded as failed`） | `finish("failed")` 有两种失败方式，但日志和错误只按一种来写：(a) `finish_run` 本身失败，此时运行确实仍是 `running`；(b) `finish_run` 已成功、`_state` 已变为 `closed`，失败发生在发布 `record.json`/`report.md` 时。情况 (b) 下文案与事实相反。探测：先占用 `record.json` 再无 finish 退出，日志写“remains marked running”，抛出“could not be recorded as failed”，但账本中该运行的状态已是 `failed`。负责人或 audit 排查时会被误导，可能误以为需要手工补记失败状态。 | 在 except 分支按 `self._state` 区分两种情况：仍是 `running` 时保留现有文案；已是 `closed` 时写“已记为 failed，但运行记录未发布”（并附 `finish_exc`），没有原异常时抛出的 `LedgerError` 文案也要相应区分。补一个测试：占用 `record.json` 后无 finish 退出，断言账本状态为 `failed`，日志和错误消息中出现“record 未发布”，而不是“remains running”。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B3-R2-1 | fixed | `__exit__` 按 `_state` 区分：最终状态未写入时说明“仍标记为 running”，已写入时说明“已记为 failed，但运行记录未发布”；`test_exit_with_unpublishable_record_reports_failed_status` 断言账本状态为 failed 及日志和错误消息。 |

- Round result: `changes requested`

Analyst 检查（Round 2 修复后）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 通过；`uv run pytest tests/ -q` → 424 passed。

## Block B3 · Round 3 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `0ab20e7`（`git diff 1167712..0ab20e7 -- src/data_io/runs.py tests/test_runs.py src/data_io/ledger.py`）；files: `src/data_io/runs.py`、`tests/test_runs.py`，以及 `src/data_io/ledger.py` 中已采纳的 B2 suggestion（B2-R2-1、B2-R2-3），另有 WAL 检查和父目录软链接检查（与 B4 交叉）。B4 的其余改动不在本轮范围。
- 审查方式：在 `/private/tmp/pr2-review-b3-r3` 以 `git worktree add --detach 0ab20e7` 检出运行，结束后已移除。
- Checks run by Reviewer（worktree 内，CPython 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -q` → 424 passed in 6.76s
  - `uv run pytest tests/test_ledger.py tests/test_runs.py -q` → 38 passed
  - 探测（`PYTHONPATH=. uv run python <scratchpad>/probe_r3.py`）：用相对路径的 root 调用 `Ledger.open_read_only` → 原生 `ValueError: relative path can't be expressed as a file URI`；root 路径含空格、`?`、`#`、`%` 时只读打开正常。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B3-R2-1 | resolved | `runs.py` 的 `__exit__` 按 `_state` 区分两种情况：最终状态没写入时报 “remains marked running”；状态已写入、只是 record 未发布时报 “was recorded as failed, but its run record was not published”，日志与抛出的 `LedgerError` 文案一致。新测试 `test_exit_with_unpublishable_record_reports_failed_status` 断言错误消息、日志内容和账本中的 `failed` 状态；原测试改为匹配 “remains marked running” 文案。两者均通过。 |
| B3-R1-6 | out-of-scope（未变） | 交给 B4 或后续 PR。 |
| B3-R1-7 | out-of-scope（未变） | 交给 PR3。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B2-R3-1 | suggestion | `src/data_io/ledger.py` `open_read_only`（`path.as_uri()`） | 采纳 B2-R2-1 改用 `mode=rw` URI 后，`Path.as_uri()` 要求绝对路径。用相对 root 直接调用时抛原生 `ValueError`，不是 `LedgerError`；改动之前相对路径可以正常工作。唯一的调用方（`audit`，经 `validate_for_read()`）传入的是已解析的绝对路径，因此当前没有实际影响，只是接口契约（只抛 `LedgerError`）有缺口。 | 使用 `path.absolute().as_uri()`（或先 `root.resolve()`），并补一个相对路径的测试。 |

B2 的其他新增代码复核后无问题：`COMMIT` 失败后的 `ROLLBACK` 已包住并报出 `LedgerError`；`mode=rw` 不会创建缺失的文件，且写者能正常等待（`test_concurrent_reader_does_not_fail_a_commit` 通过）；WAL 头字节（偏移 18–19 为 2）与 `-wal`/`-shm` 文件的检查正确；`manifests` 父目录为软链接时拒绝。WAL 与软链接的拒绝场景由 B4 的 `tests/test_audit.py` 覆盖。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B2-R3-1 | fixed（采纳） | 改为 `path.absolute().as_uri()`；`test_read_only_open_accepts_a_relative_root`。 |

- Round result: `converged`（B3 所有 must-fix/should-fix 已解决，没有新的 must-fix/should-fix；lint、format 和全量测试均由 Reviewer 亲自运行并通过。B2 保持 converged，B2-R3-1 只是 suggestion，交给 Reporter）

## Block B4 · Round 3 · 2026-11-13

- Revision: `codex/pr2-run-ledger` @ `0ab20e7`；本块相关文件：`src/data_io/audit.py`、`src/data_io/ledger.py`（`open_read_only`、`_check_file`）、`tests/test_audit.py`、`README.md`、`src/config/README.md`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`。
- 审查方式：在 `/private/tmp/pr2-b4-review-r3` 以 `git worktree add --detach 0ab20e7` 检出，结束后已移除。探测数据只放在本会话 scratchpad 的专用目录中，结束后按确切路径删除。
- Checks run by Reviewer（均在上述 worktree 内）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -q` → 424 passed in 6.67s
  - `uv run pytest tests/test_audit.py -q` → 10 passed
  - 临时探测脚本（scratchpad，未入库）。每项都对 `DATA_ROOT` 做含 SHA-256 的快照，在 `main(["audit"])` 前后比较：
    1. 真实 hot journal → 返回 2，提示 “Ledger has a rollback journal …”，快照无差异。
    2. WAL 标志留在文件头中、没有 `-wal`/`-shm`（与 R2 探测 2 相同）→ 返回 2，快照无差异。WAL 连接仍打开、`-wal`/`-shm` 都存在 → 返回 2，快照无差异。
    3. 0 字节账本 → 返回 2（`Unsupported ledger schema version 0`），快照无差异。
    4. `gold/` 和 `recovery/conflicts/` 权限 000 → 返回 1，报告 `scan_error:gold` 和 `scan_error:recovery/conflicts`，审计继续。
    5. `manifests/` 是软链接 → 返回 2（`Ledger directory must not be a symbolic link`）。
    6. audit 连接持有读事务 1 秒，其间写者执行 `Run.start` + `finish` → 约 1.09s 后成功。
    7. 干净目录 → 返回 0，快照无差异。
    8. **文档所说的 WAL 恢复路径**：外部把账本切到 WAL 并关闭后，执行写路径 `Ledger.open(layout)`。文件头确实变回 DELETE（`0101`），但 `manifests/ledger.sqlite3-shm`（32768 字节）留了下来。此后 `main(["audit"])` 一直返回 2（“is in WAL mode or has WAL files”），写任务也不会删除这个 `-shm`。另外确认：账本头为 DELETE、只有遗留 `-shm` 时，`mode=rw` + `query_only` 连接读取后，所有文件（含 `-shm`）的 size/mtime/SHA-256 都不变（见 B4-R3-1）。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B4-R2-1 | resolved | `open_read_only` 检查文件头第 18、19 字节以及 `-wal`/`-shm`，WAL 账本在连接前就被拒绝；探测 2 两种形态都返回 2 且快照无差异；`test_wal_mode_ledger_is_refused_without_writing` 通过。拒绝条件过宽带来的新问题见 B4-R3-1。 |
| B4-R2-2 | resolved | 只读连接改为 `file:…?mode=rw`，不会新建缺失的账本；`test_read_only_open_never_creates_a_missing_ledger` 通过；`audit.py` 和 `open_read_only` 的 docstring 已把“写者在检查与首次读取之间崩溃”写成剩余的窄窗口，不再是绝对表述。 |
| B4-R2-3 | resolved | `_walk` 的 `onerror` 改为记录 `scan_error` 并继续（探测 4，`test_unreadable_directory_is_reported_and_audit_continues`）；`_check_file` 拒绝软链接的 `manifests/`（探测 5）。B4-R1-5 的剩余部分随之解决。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B4-R3-1 | should-fix | `src/data_io/ledger.py`（`open_read_only` 中 `any(item.exists() … for item in wal_files)` 的条件）；`README.md:85`、`src/config/README.md:55`、ADR-003 中“下一个写任务会以 DELETE 模式重新打开”的说法 | 只要 `-shm` 存在就拒绝，这个条件过宽，而文档给出的恢复方法也不成立。账本被外部切到 WAL 后，写路径 `Ledger.open` 确实把文件头改回 DELETE，但 SQLite 在 macOS 上留下了 `ledger.sqlite3-shm`，写任务也不会删除它。之后 audit 每次都返回 2，只能人工删除 `-shm`（探测 8）。而 DELETE 模式下遗留的 `-shm` 对只读连接无害，读取不会改动任何文件（探测 8）。真正有风险的是文件头为 WAL，或存在 `-wal`（SQLite 打开时发现 `-wal` 会进入 WAL 处理）。用户照 README 操作仍然无法使用 audit。 | 只在文件头为 WAL 或存在 `-wal` 时拒绝；文件头为 DELETE 且只有 `-shm` 时允许打开，并在报告中加一条 `ledger_stale_shm` 之类的提示，或者只在文档中说明。另一种做法：保留现有拒绝，但更正文档，写明还需人工删除 `-shm`，并由写路径 `_configure` 在切回 DELETE 后清理它（这属于 B2 代码，需协调）。加测试：WAL → `Ledger.open` → 关闭 → audit 返回 0 或给出明确的指引。 |

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B4-R3-1 | fixed（待负责人决定是否开第 4 轮复核） | 只读打开只在文件头为 WAL 或存在 `-wal` 时拒绝，遗留 `-shm` 允许；`test_leftover_shm_after_returning_to_delete_mode_is_allowed`（WAL → 写路径打开 → 审计 ok 且文件不变）。README、`src/config/README.md`、ADR-003 同步修改。 |

- Round result: `escalated`。B4 已达 3 轮上限，仍有 1 个 should-fix（B4-R3-1）未关闭。所有 B4-R1、B4-R2 的发现都已解决；lint、format 和全量测试（424 passed）均由 Reviewer 亲自运行并通过。B4-R3-1 只在“账本曾被外部工具切到 WAL”这一越出契约的情况下出现，不影响正常写入路径，也不会写入数据；但文档给出的恢复步骤会失效，audit 会一直无法使用。Reviewer 的立场：修改很小（拒绝条件改为“文件头为 WAL 或存在 `-wal`”，并加一条测试），建议再修一次后由 Reviewer 确认；也可由负责人接受为已知限制，只更正文档。请 Reporter 交负责人决定。

Analyst 检查（B2-R3-1、B4-R3-1 修复后）：`uv run ruff check .` 通过；`uv run ruff format --check .` 通过；`uv run pytest tests/ -q` → 426 passed。

## Block B4 · Round 4 · 2026-11-18

**结论先说：** B4-R3-1 已经真正修好，B4 收敛（`converged`）。审计命令现在只在“账本真的处于 WAL 状态”时拒绝；账本恢复正常后留下的那个无害的 `-shm` 文件不再挡住审计。没有新的 must-fix 或 should-fix，只有一条措辞上的 suggestion。

背景（一句话）：SQLite 账本有两种记“未完成修改”的方式。一种是默认的回滚日志（DELETE 模式），另一种是 WAL 模式。WAL 模式会在账本旁边生成 `-wal`（存放还没并回主文件的修改）和 `-shm`（只是一个索引，不存数据）两个文件。本项目只允许 DELETE 模式。

- Revision: `codex/pr2-run-ledger` @ `62a4012`（HEAD）。本轮审查的是 `e69f167` 中属于 B4 的改动：`src/data_io/ledger.py`（`open_read_only` 的拒绝条件，以及 `path.absolute().as_uri()`）、`tests/test_audit.py`（新增 `test_leftover_shm_after_returning_to_delete_mode_is_allowed`）、`tests/test_ledger.py`（新增相对路径测试，属于 B2-R3-1，只作背景）、`README.md`、`src/config/README.md`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`。`git diff e69f167 HEAD --stat -- src tests README.md CHANGELOG.md src/config docs/adr` 没有输出，说明之后的 `6e6dfe0`、`62a4012` 没有再改这些代码和文档。工作区中未提交的改动（`AGENTS.md`，以及可能由 B1 Analyst 同时修改的 README 等）不在本轮范围，文档一律以 HEAD 版本为准。
- Addresses: B4-R3-1（升级后修复的复核，依据 `PLAN.md` §4b 负责人 2026-11-18 的决定）；同时复查 B4 之前所有发现的状态，并按 `PLAN.md` B4 验收示例整体复核。
- 审查方式：在本会话 scratchpad 中用 `git worktree add --detach <scratchpad>/wt-b4-r4 HEAD` 检出 HEAD 运行全部检查，探测数据放在 scratchpad 的专用目录中；结束后用 `git worktree remove --force` 和按确切路径删除清理，`git worktree list` 确认只剩主工作区。
- Checks run by Reviewer（均在上述 worktree 内，CPython 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v` → 426 passed in 6.18s
  - `uv run pytest tests/test_audit.py tests/test_ledger.py -q` → 37 passed
  - 临时探测脚本（scratchpad，未入库，`PYTHONPATH=. uv run python <scratchpad>/probe-b4r4/probe.py`、`probe2.py`）。每项都通过 CLI `main(["audit"])` 运行，并在前后对整个 `DATA_ROOT` 做快照（每个文件的大小、修改时间、SHA-256，外加根目录和 `manifests/` 的修改时间）：
    1. **B4-R3-1 原场景**：外部把账本切到 WAL 并关闭，再执行写路径 `Ledger.open(layout)`。之后 `manifests/` 中是 `ledger.sqlite3`、`ledger.sqlite3-shm`、`runs`，文件头第 18–19 字节为 `0101`（DELETE）。这个 `-shm` 是 SQLite 在 macOS 上自然留下的，不是人工造的。audit → 返回 0，快照无差异。之后再跑一个写任务（`Run.start` + `commit_file` + `finish`），audit 仍返回 0，快照无差异。
    2. **WAL 写进程崩溃，留下有内容的 `-wal`**（4152 字节，里面有一条已提交、但还没并回主文件的修改）→ audit 返回 2，提示 “is in WAL mode or has a WAL file … A write task reopens it in DELETE mode.”，快照无差异。然后执行写路径 `Ledger.open(layout)`：`-wal` 消失，文件头变回 `0101`，那条修改被保留（读到 `task='walprobe'`）。之后 audit 返回 0。文档写的恢复方法（“下一个写任务会以 DELETE 模式重新打开”）这次实际成立。
    3. 文件头为 DELETE，但存在 0 字节的 `-wal` → 返回 2，快照无差异（保守拒绝，合理）。
    4. 只有内容为随机字节的 `-shm` → 返回 0，快照无差异（DELETE 模式下 SQLite 根本不读 `-shm`）。
    5. `-shm` 是指向 `DATA_ROOT` 外文件的软链接 → 返回 1，报告 `unexpected_symlink`，快照无差异，外部文件内容不变。
    6. 验收示例：干净目录 → 0；篡改已登记文件、删除已登记文件、未登记文件、遗留 `.partial-x`、未结束运行、已结束但 `record.json` 被删 → 返回 1，依次报告 `manifest_file_changed`、`manifest_file_missing`、`unregistered_file`、`partial_file`、`run_unfinished`、`run_record_missing`，快照无差异。
    7. 没有 `manifests/`、只有 `silver/` 的目录 → 返回 0，`ledger: absent`，没有新建任何目录或文件。
  - 文档一致性：`git grep -n -e "-shm" -e "WAL" HEAD -- . ':!docs/pr2'`。README.md:85、`src/config/README.md:55`、ADR-003 第 18 行都已改成“文件头为 WAL 或存在 `-wal` 时拒绝，遗留 `-shm` 允许”，与代码一致。`docs/README.md:53` 索引了 ADR-003；`CHANGELOG.md:9` 有 audit 条目。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B4-R3-1 | resolved | `src/data_io/ledger.py:325-333` 的拒绝条件改为 `header[18:20] == b"\x02\x02" or wal.exists() or wal.is_symlink()`，不再看 `-shm`。探测 1 用 SQLite 自然留下的 `-shm` 复现了 R3 的场景，audit 返回 0 且不改任何文件；探测 2 证明真正有风险的 `-wal` 仍被拒绝，并且文档说的恢复方法确实有效。新测试 `test_leftover_shm_after_returning_to_delete_mode_is_allowed` 通过（在不留 `-shm` 的平台上，测试会自己造一个，因此各平台都能覆盖这个分支）。三份文档已同步。 |
| B4-R2-1 | resolved（维持） | 探测 2、3：文件头为 WAL 或存在 `-wal` 时仍返回 2，快照无差异；`test_wal_mode_ledger_is_refused_without_writing` 通过。 |
| B4-R2-2 | resolved（维持） | `open_read_only` 仍用 `?mode=rw`，并改为 `path.absolute().as_uri()`，不会新建缺失的账本；探测 7 和 `test_read_only_open_never_creates_a_missing_ledger` 通过。 |
| B4-R2-3 | resolved（维持） | `audit.py` 的 `_walk` 仍把无法列出的目录记为 `scan_error` 并继续；`_check_file` 仍拒绝软链接的 `manifests/`。相关测试通过。 |
| B4-R1-1 | resolved（维持） | 回滚日志检查在 `ledger.py:312-319` 未变；`test_rollback_journal_is_refused_without_writing` 通过。 |
| B4-R1-2 | resolved（维持） | 层根软链接和父目录软链接的处理未变；`test_symlinks_are_reported_not_followed` 通过；探测 5 中 `manifests/` 下的软链接也被报告。 |
| B4-R1-3 | resolved（维持） | `Ledger.snapshot()` 单个读事务未变；文档仍写明须在没有写任务时运行。 |
| B4-R1-4 | resolved（维持） | `test_cli_writes_nothing_and_reports_absent_ledger` 通过；探测 6、7 走 CLI 路径，快照无差异。 |
| B4-R1-5 | resolved（维持） | 不可读文件报 `manifest_file_unreadable`、不可读目录报 `scan_error`，审计都继续；相关测试通过。 |
| B4-R1-6 | resolved（维持） | `test_recovery_partials_and_unreadable_files_are_reported` 通过。 |
| B4-R1-7 | resolved（维持） | `e69f167` 之后 ADR-002 没有改动。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B4-R4-1 | suggestion | `src/data_io/audit.py:3-5`（模块说明） | 模块说明仍写 “refuses to open a ledger that has a rollback journal or WAL files”。现在单独的 `-shm` 是允许的，“WAL files”（复数）容易让读代码的人以为 `-shm` 也会被拒绝。例子：有人看到 `manifests/ledger.sqlite3-shm`，读了这句说明，会以为 audit 一定失败，实际上它返回 0。只是措辞问题，行为和对外文档都正确。 | 改成 “a rollback journal, a WAL-mode header, or a `-wal` file”。以后有人改这个文件时顺手修改即可。 |

### Owner questions
none

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `converged`。B4 之前所有 must-fix 和 should-fix 都已 resolved，其中 B4-R3-1 由本轮确认；没有新的 must-fix 或 should-fix；没有待回答的阻塞问题；lint、format 和全量测试（426 passed）均由 Reviewer 在 HEAD 的独立 worktree 中亲自运行并通过。B4 的验收示例（干净返回 0；篡改、删除、未登记、遗留 partial、未结束运行、缺失 record 都报告并返回 1；不创建目录、不写文件；没有账本时报告 `absent`）已由测试和本轮 CLI 探测再次确认。B4-R4-1 是 suggestion，交给 Reporter。说明：以上只证明本机（macOS、CPython 3.9.6、系统自带 SQLite）上的行为；Linux 上 SQLite 是否会留下 `-shm` 没有实测，但新测试在不留 `-shm` 时会自己造一个，所以代码分支在两种情况下都有覆盖。

## Block B1 · Round 4 · 2026-11-18

**结论先说：** 第 3 轮留下的 B1-R2-1 已经真正修好，这次在真正的 Python 3.13 上验证过。P1-F1 的文档修改大体正确，但有一句话说得太绝对（B1-R4-1，should-fix）：账本锁等不到时，文件**不一定**已经写入，要看卡在哪一步。P1-F2 和 P1-F3 负责人已决定在本 PR 处理，做法需要负责人选，下面作为两个 blocking 问题提出。本轮结果：`waiting for owner`。

先解释两个词：
- **锁**：像一个只有一把钥匙的房间。同一时间只有拿到钥匙的任务能写数据，别的任务要等钥匙。本项目有两把锁：`.writer.lock` 管“往数据目录写文件”，SQLite 自己的锁管“改账本”。
- **账本**：`DATA_ROOT/manifests/ledger.sqlite3`，记录每次运行、每个已登记文件和 checkpoint。

- Revision: `codex/pr2-run-ledger` @ `4cd778e`（HEAD），加上工作区未提交的 `CHANGELOG.md`、`README.md`、`src/config/README.md`、`src/config/README_FOR_DEVELOPER.md`（B1 Analyst 的 P1-F1 文档修改）。`9d0e8f3`（B1-R2-1 的修复）已在 HEAD 的历史里（`git branch --contains 9d0e8f3` → `codex/pr2-run-ledger`），本轮复核其中的 `src/config/models/pipeline.py` 和 `tests/test_writer_recovery.py`。工作区里的根目录 `AGENTS.md` 是工作流文档，不属于 B1，未审查。`git diff` 显示的四个文档改动与 revision packet 所述一致。
- Addresses: B1-R2-1（升级后修复的复核，依据 `PLAN.md` §4b）；P1-F1（文档）；P1-F2、P1-F3（按 §4b 由 Reviewer 向负责人提问）；同时复查 B1 之前的所有发现。
- Checks run by Reviewer：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v` → 426 passed in 5.71s（主工作区，CPython 3.9.6）
  - `uv run pytest tests/ -q -k "lock or invalid_fields or json_default or zero_padded"` → 40 passed, 386 deselected
  - **真实 Python 3.13 探测**（scratchpad 中用 `uv venv --python 3.13` 建临时环境，CPython 3.13.18，装上 pydantic、python-dotenv、pytest、duckdb、pyarrow；结束后已删除）：`PYTHONPATH=. <venv>/bin/python <scratchpad>/probe-b1r4/cfg.py`，`PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS` 取 `"0"*5000+"5"` → 5；`"0"*5000` → 0；`"0"*10000+"1"` → 1；`"9"*5000` → `ConfigError`；`"0"*5000+"3601"` → `ConfigError`；`"0003600"` → 3600；`"3601"` → `ConfigError`；`" 0030 "` → 30。来源都记为 `environment:PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS`。没有任何输入再抛出原生 `ValueError`。
  - **回归保护验证**：在 scratchpad 中 `git worktree add --detach <scratchpad>/wt-b1r4 HEAD`，把那一行临时改回 `int(raw_timeout)`，`test_long_zero_padded_lock_timeout_is_parsed_without_long_int_conversion` 在 3.13.18 和 3.9.6 上都是 2 failed；改回后通过。说明这个测试在 3.9 上也能抓住回退。之后 `git worktree remove --force`，`git worktree list` 只剩主工作区。
  - 同一 worktree 用 3.13.18 跑全量：`python -m pytest tests/ -q -p no:cacheprovider` → 2 failed, 424 passed。失败的是 PR1 的 `tests/test_adapter_contract.py::test_excessively_nested_source_json_retains_evidence[False/True]`，与 B1 无关，见 B1-R4-3。
  - **P1-F1 文档对照探测**（`PYTHONPATH=. uv run python <scratchpad>/probe-b1r4/ledgerwait.py`）：先 `Run.start`，再用另一个 SQLite 连接占住账本锁，然后依次调用 `commit_file`、`add_counts`、`Run.start`：
    - 另一个连接用 `BEGIN IMMEDIATE`（相当于“另一个任务正在改账本”）、写锁超时 0：三个调用都在约 5.2 秒后报 `LedgerError: ... database is locked`；`silver/trades/a.parquet` **已经写入**；放开锁后 `audit` 报 `unregistered_file` 和 `run_unfinished`。
    - 另一个连接用 `BEGIN EXCLUSIVE`（相当于“另一个任务正在把修改真正写进账本文件”，DELETE 模式下每次提交都会短暂进入这种状态）、写锁超时 0：三个调用都在约 5.1 秒后报 `LedgerError`；但 `commit_file` 卡在写文件**之前**的检查（`Ledger query failed`），`silver/trades/a.parquet` **没有写入**，`audit` 只报 `run_unfinished`。
    - 同样用 `BEGIN EXCLUSIVE`、写锁超时 7：三个调用都在约 7.4 秒后报 `LedgerError`，符合 `max(7, 5)`。
  - **P1-F3 现状探测**（`PYTHONPATH=. uv run python -u <scratchpad>/probe-b1r4/starve2.py`，脚本另起一个进程 A 连续写 1 字节小文件 3.5 秒，主进程 B 在 0.3 秒后用 2 秒等待时间写 1 个文件，重复 5 次）：3 次 B 等满 2.0 秒后报 `WriteBoundaryError`，同时 A 写了 669–680 个文件；2 次 B 分别在 1.01 秒和 0.30 秒拿到锁，此时 A（等待时间 0）反而立刻失败退出。数据都没有损坏。这只测了现在的代码；Analyst 所说方案 B 的效果（0.001–0.003 秒拿到锁）我没有复现。
  - **P1-F2 现状核对**：`grep -rn "DataLayout.create(" src/` → 只有 `src/data_io/runs.py:7`（模块说明里的示例）和 `src/config/README.md:29,74`（文档），没有真实写任务；`tests/` 中 61 处、`Run.start(` 19 处，与 packet 一致。`src/data_io/runs.py:121-123` 的一致性检查确认存在。
  - 探测数据都放在 scratchpad 的专用目录，结束后已删除。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R2-1 | resolved | `src/config/models/pipeline.py:163` 改为 `int(raw_timeout.lstrip("0") or "0")`，配合第 155-156 行“去零后超过 4 位就报 `ConfigError`”，传给 `int()` 的字符串最多 4 位。真实 3.13.18 上全部长输入都得到正确数字或 `ConfigError`（见上）。新测试用替身 `int` 模拟 3.11+ 的长度限制，撤销修复后在 3.9 和 3.13 上都失败，能防止回退。 |
| B1-R1-1 | resolved（维持） | 相关测试都在 40 个目标用例中通过。 |
| B1-R1-2 | resolved（维持） | `pipeline.py:175-180` 来源区分未变；`test_lock_timeout_sources` 通过。 |
| B1-R1-3 ~ B1-R1-6 | resolved（维持，已采纳的 suggestion） | 代码未变，测试通过。 |
| B1-R1-7 | resolved（由 B4 完成） | `CHANGELOG.md:10` 有 PR2 的写锁条目；ADR-003 第 17 行记录了账本等待规则。 |

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R4-1 | should-fix | `README.md:56`、`src/config/README.md:29`（未提交的 P1-F1 修改）；代码 `src/data_io/runs.py:174-178` | 文档说“账本锁等完仍拿不到时报 `LedgerError`，**此时文件已写入但未登记**”，还说 `commit_file`“最多停顿 5 秒”。实际 `commit_file` 碰账本两次：先在写文件**之前**检查运行是否还在进行（第 174 行 `require_running`），写完文件后再登记（第 178 行 `commit`），两步各自最多等 5 秒。例子（已实测）：另一个任务正在把修改写进账本文件时，第一步就等不到，5.1 秒后报错，文件**没有**写入，audit 也不会报未登记文件；另一个任务只是开始改账本时，第二步等不到，文件**已**写入，audit 报 `unregistered_file`。按代码推断（未实测），如果第一步等了接近 5 秒才拿到，第二步又等 5 秒，总共可能停约 10 秒。这正是 P1-F1 要讲清楚的事情，写错会让排查问题的人以为“报错了文件就一定在磁盘上”。 | 两份 README 改成大意：“每次碰账本最多等 `max(writer_lock_timeout_seconds, 5)` 秒。`commit_file` 碰两次：写文件前检查一次，写文件后登记一次。卡在检查时文件不会写入；卡在登记时文件已写入但未登记，由 `python -m src audit` 报告。”去掉“最多 5 秒”这种总时长说法，或改成“每一步最多 5 秒”。`CHANGELOG.md:10` 和 `README_FOR_DEVELOPER.md` 的写法正确，不用改。 |
| B1-R4-2 | suggestion | `tests/test_writer_recovery.py:532` | 参数化用例没有给名字，`pytest -v` 会把 5000 个 `0` 整段打印成测试名，输出很难看。 | 加 `ids=["zero_padded_5", "all_zeros"]`。 |
| B1-R4-3 | out-of-scope | `tests/test_adapter_contract.py:494-502`（PR1） | 在 Python 3.13.18 上这两个用例失败：嵌套 1200 层的 JSON 在 3.13 上能正常解析，不再触发 `RecursionError`，于是报的是“缺少字段”。错误仍然被抛出、原始数据仍然保留，所以没有数据被悄悄丢掉，只是测试假设的“原因”不同。项目声明支持 Python 3.9 及以上，这属于 PR1 的兼容性问题，不是 B1 的。 | 交给 Reporter 作为提议：以后在 3.11+ 上跑一次全量测试，把这个用例改成不依赖解释器的递归限制（例如嵌套更深，或只断言抛出 `NormalizationError` 并保留原始数据）。 |

### Owner questions

**问题 1（P1-F2，blocking）：怎样保证以后的真实写任务一定用上配置里的“等锁秒数”？**

1. 背景：`writer_lock_timeout_seconds` 是“钥匙被别人拿着时最多等几秒”，它写在配置里，但现在要靠每个写任务自己记得把它传给 `DataLayout.create`（建数据目录、拿到写入工具的那一步），忘了传就等于 0 秒。
2. 场景：你把 `PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS` 设成 30。PR3 写下载器的人写成了 `DataLayout.create(root)`，忘了传这个值。10:00:00 回填任务正在写文件；10:00:01 下载器启动，发现钥匙被占，**立刻**失败，而不是等 30 秒。如果下载器用了 `Run.start`，会因为“配置是 30、实际是 0”报错，能发现；如果是不经过 `Run` 的小工具，没人会发现它一直按 0 秒在跑。现在代码里还没有真实写任务，所以这个问题只是“以后可能发生”。
3. 选项：
   - **A. 只留一个入口。** 在 `src/data_io/` 加一个函数，例如 `open_write_layout(config)`：先做写入前检查 `validate_for_write()`，再用配置里的秒数建目录。再加一个自动测试：扫描 `src/` 下的代码，发现有人直接写 `DataLayout.create(` 就让测试失败。会发生什么：以后的任务只能走这个入口，忘传参数的情况不会出现；测试代码不受影响。代价：约 10 行代码加 2 个测试；“扫描源码”的测试比较死板，将来真有特殊需要时要改这个测试。
   - **B. 让 `Run.start` 自己建目录。** 写任务只给 `Run.start` 配置，由它建目录。会发生什么：用 `Run` 的任务不会出错。代价：要改约 19 处测试；不经过 `Run` 的任务仍然可能忘传。
   - **C. 去掉默认值。** `DataLayout.create` 必须明确写出等待秒数，不写就报错。会发生什么：不会“不知不觉用 0”。代价：要改约 61 处测试；任务仍可以手写一个数字（比如 0），不保证这个数字来自配置。
4. 我的建议：**A**。只有它能保证数字一定来自配置，而且同时保证“先检查、再建目录”的顺序（硬规则 9），代价最小，违反时测试会自动报出来。

**问题 2（P1-F3，blocking）：多个任务等同一把写锁时，要不要保证“先来的先拿到”？**

1. 背景：现在等钥匙的方式叫“轮询”：每隔 50 毫秒（1 毫秒是千分之一秒）去看一眼钥匙在不在；如果占着钥匙的任务一放下就马上又拿起来（中间不到 1 毫秒），等的人每次去看都刚好看到钥匙被拿着，可能一直等到超时。
2. 场景（我本轮实测）：任务 A 不停地写 1 字节的小文件，每写一个就拿一次、放一次钥匙；任务 B 只想写 1 个文件，最多等 2 秒。5 次试验里有 3 次 B 等满 2 秒后报错，同时 A 写了约 670 个文件；另外 2 次 B 运气好拿到了钥匙，结果 A（等待时间 0）反而立刻失败。时间线：10:00:00.000 A 放下钥匙；10:00:00.0001 A 又拿起钥匙；10:00:00.050 B 来看，被占；…… 10:00:02.000 B 报“等了 2 秒”退出。数据不会坏，失败的任务会明确报错，只是“该写的没写成”。如果 A 每写一个文件之间停 1–10 毫秒，Analyst 测到 B 在 0.01–0.4 秒内就能拿到（这个数字我没有复现）。
3. 选项：
   - **A. 只写进文档。** 说明“不保证先来先得”，建议连续写很多文件的任务在文件之间稍停一下，或调大等待时间。会发生什么：代码不变；以后实时采集和回填同时跑时，可能有一个反复失败。代价：零代码，风险留给以后。
   - **B. 改成“等通知”。** 等的人不再每 50 毫秒去看一次，而是请操作系统“钥匙一放下就叫醒我”。为了能在超时时放弃，这个等待放在一个后台线程里（线程是同一个程序里同时干另一件事的帮手），主程序负责计时；超时放弃后，那个帮手以后拿到钥匙会马上还回去。会发生什么：Analyst 在 macOS 上测到 B 5 次都在 0.001–0.003 秒内拿到钥匙。代价：约 30–40 行代码；不是严格的先来先得，只是等的人会先被叫醒，所以几乎总能拿到；只在 macOS 上测过，而正式服务器很可能是 Linux，需要在 Linux 上再测；超时后的帮手会一直留到钥匙空出来为止。
   - **C. 严格排队取号。** 在 `DATA_ROOT/.writer.queue/` 下给每个等待的任务发一个号，按号依次拿钥匙，并能识别崩溃任务留下的号。会发生什么：严格先来先得。代价：约 100 行；磁盘上多出需要清理的排队文件；任务崩溃后的残留号码会让半夜排查问题更难。
4. 我的建议：**B**，并附两个条件：加一个自动测试，复现“一个任务连续写、另一个任务能在等待时间内拿到钥匙”；在 PR 合并前至少在 Linux 上实测一次（做不到就在文档里写明“只在 macOS 验证过”）。理由：它直接解决了实测出来的问题，改动小，失败时仍然是明确报错；C 太重，A 等于把问题留给以后。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `waiting for owner`。两个 blocking 问题（P1-F2、P1-F3）要等负责人回答；B1-R4-1（should-fix）可以和负责人选定的做法一起交给下一轮 Analyst。B1-R2-1 已 resolved。lint、format 和全量测试（426 passed）由 Reviewer 本轮亲自运行通过；但因为还有未解决的 should-fix 和 blocking 问题，B1 尚未收敛。说明：以上探测只在本机（macOS、CPython 3.9.6 和 3.13.18）上运行，Linux 行为未测。

负责人确认（2026-11-19）：问题 1（P1-F2）选 A；问题 2（P1-F3）选 B，附 Reviewer 提出的两个条件（自动测试；合并前 Linux 实测或在文档写明只在 macOS 验证）。

### Analyst response（Analyst 第 5 步，2026-11-19，由 Orchestrator 按 Analyst 回复填写）
| ID | Action | Detail and checks |
| --- | --- | --- |
| B1-R4-1 | fixed | `README.md` 写锁段落、`src/config/README.md:29`、`README_FOR_DEVELOPER.md`：每次访问账本最多等 `max(writer_lock_timeout_seconds, 5)` 秒；`Run.commit_file` 访问两次（写前检查、写后登记），卡在检查时文件不写入，卡在登记时文件已写入但未登记、由 `audit` 报告；删掉“最多 5 秒”的总时长说法。 |
| B1-R4-2 | fixed（采纳 suggestion） | `tests/test_writer_recovery.py` 参数化用例加 `ids=["zero_padded_5", "all_zeros"]`。 |
| P1-F2 | fixed（负责人选 A） | `src/data_io/layout.py` 新增 `open_write_layout(config)`：类型检查 → `validate_for_write()` → `DataLayout.create(..., lock_timeout_seconds=config.writer_lock_timeout_seconds)`；文档示例改用它；测试 `test_open_write_layout_uses_configured_timeout`、`test_open_write_layout_runs_write_preflight_before_layout`、语法树扫描 `test_only_open_write_layout_calls_datalayout_create_in_src`。 |
| P1-F3 | fixed（负责人选 B） | `_lock` 先试 `LOCK_NB`；超时 0 立即失败、不起线程；否则后台线程用自己的句柄阻塞 `flock`，调用方计时，放弃后拿到锁立即释放，打断时不留锁，线程加锁出错转 `WriteBoundaryError`。新增 6 个测试（含条件 1 的连续写场景）；条件 2：无 Linux 环境，README、ADR-003、`src/config/README.md`、CHANGELOG、`layout.py` 说明写明只在 macOS 验证。Analyst 检查：ruff、format 通过；全量 436 passed（含 B2 未提交测试）；相关测试连跑 20 次全部通过；换回旧轮询后连续写测试 3/3 失败。 |

## Block B2 · Round 3 · 2026-11-19

**结论先说：** P1-F5（版本检查放到 watermark 检查前面）已经正确完成，第 3 轮提出的 B2-R3-1（相对路径）也确认修好。没有新的 must-fix 或 should-fix。但 P1-F4（数据集必须放在自己的文件夹里）还没有做，因为路径规则要负责人定。负责人已决定这件事在本 PR 做，所以下面作为一个 blocking 问题提出。本轮结果：`waiting for owner`。

先解释几个词：
- **数据集**：一类数据的名字，例如 `silver.trades`（统一格式后的成交记录）、`silver.markets`（市场信息）、`gold.market_1m`（1 分钟研究产品）。点号前面是层，后面是名字。
- **registry**：`src/data_schema/schema_registry.json`，列出全部 14 个数据集和它们的字段，但没有写文件该放在哪个目录。
- **manifest 登记**：账本里给每个数据文件记一张“身份证”（路径、行数、校验和、属于哪个数据集）。
- **checkpoint 与 version**：checkpoint 记录“采集进行到哪里了”；每推进一次 version 加 1。推进时调用方要说明“我看到的是第几版”（`expected_version`），对不上就说明别人已经抢先推进过。watermark 是“数据已经覆盖到的时间”，不能往回退。

- Revision: `codex/pr2-run-ledger` @ `4cd778e`（HEAD）加上工作区中 B2 Analyst 未提交的 `src/data_io/ledger.py`、`tests/test_ledger.py`；另外复核从未审查过的 `e69f167` 中 B2-R3-1 的修复（`ledger.py` 中 `path.absolute().as_uri()`、`tests/test_ledger.py` 中 `test_read_only_open_accepts_a_relative_root`）。`git diff --stat -- src/data_io/ledger.py tests/test_ledger.py` → 2 个文件，+39/−4，与 revision packet 所述一致。工作区里其他未提交改动（`layout.py`、各 README、`CHANGELOG.md`、`AGENTS.md` 等，B1 Analyst 正在修改）不在本轮范围，没有审查，也没有放进检查环境。
- Addresses: P1-F5；B2-R3-1（`e69f167` 的复核）；P1-F4（按 `PLAN.md` §4b 由 Reviewer 向负责人提问）；同时复查 B2 之前所有发现和 `PLAN.md` B2 验收示例。
- 审查方式：为了不受 B1 并行修改的影响，在本会话 scratchpad 中 `git worktree add --detach <scratchpad>/wt-b2r3 HEAD`，再执行 `git -C <repo> diff -- src/data_io/ledger.py tests/test_ledger.py | git -C <worktree> apply`，worktree 中只有这两个文件有改动（`git status --short` 确认）。所有检查都在这个 worktree 中运行。结束后 `git worktree remove --force`，`git worktree list` 只剩主工作区；探测数据按确切路径删除。
- Checks run by Reviewer（均在上述 worktree 内，CPython 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v` → 427 passed in 6.15s
  - `uv run pytest tests/test_ledger.py -q` → 27 passed
  - `uv run pytest tests/test_ledger.py tests/test_runs.py tests/test_audit.py -q` → 51 passed
  - **新测试能否抓住旧代码**：在 worktree 中 `git checkout -- src/data_io/ledger.py`（恢复为 HEAD 的旧顺序），`uv run pytest tests/test_ledger.py -q -k "stale_racing or watermark"` → `test_stale_racing_run_reports_version_conflict_before_watermark` 失败，报的正是 `Checkpoint k watermark cannot move backwards or be removed`；重新应用修复后 `-k "stale_racing or watermark or relative"` → 4 passed。
  - **B2-R3-1 的测试能否抓住旧代码**：临时把 `path.absolute().as_uri()` 改回 `path.as_uri()`，`uv run pytest tests/test_ledger.py -q -k relative` → 1 failed（原生 `ValueError: relative path can't be expressed as a file URI`）；恢复后通过。
  - 探测脚本（scratchpad，未入库，`PYTHONPATH=. uv run python <scratchpad>/probe-b2r3/probe_f4.py <dir>`）：
    1. **P1-F4 现状**：以下 5 个“放错位置”的登记全部成功：`silver.trades` 放在 `silver/quotes/c.parquet`、`silver/markets/m.parquet`（另一个已有数据集的目录）、`silver/flat.parquet`（没有数据集目录）；`gold.market_1m` 放在 `gold/kalshi/MKT-1/market_1s/v1/20261113.parquet`（产品名是 `market_1s`）；`gold.training_datasets` 放在 `gold/x/a.parquet`。
    2. **检查顺序**：checkpoint `k` 在 version 1、watermark T0。`expected_version=0`、不带 watermark → 报 `is at version 1, expected 0`；`expected_version=1`、watermark 比 T0 早 1 秒 → 报 `watermark cannot move backwards`；`expected_version=1`、不带 watermark → 报 `watermark cannot move backwards`；`expected_version=5`、watermark 晚一天 → 报 `is at version 1, expected 5`。四次都没有登记任何东西（manifest 数、`rows_written`、checkpoint version 都不变）。也就是说：版本对得上时，watermark 后退仍然被拒绝；版本对不上时，先报版本冲突。
  - 事实核对：`schema_registry.json` 版本 7.0.0，14 个数据集（`bronze.raw`；8 个 silver；5 个 gold），每个只有 `fields`、`primary_key`、`rules`，没有路径信息。8 个 silver 数据集的名字与 `agent/PROJECT.md` §5 的 silver 子目录完全一一对应。5 个 gold 产品的主键都含 `venue`、`market_id`；`gold.training_datasets` 的主键是 `dataset_name, venue, market_id, observation_time`，即一个训练集包含很多市场的行。`docs/FOUNDATION_RULES.md:87` 的 gold 路径注明“仅示意”。`src/data_io/runs.py:171-174`：`commit_file` 先调用 `commit_values` 再写文件，所以以后在 `commit_values` 里加的路径检查会在写文件前拒绝。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| P1-F5 | resolved | `ledger.py` 中版本检查已移到 watermark 检查之前，两条错误文字没变，两者仍在同一个事务里，出错时 manifest 插入和 `rows_written` 一起回滚。新测试 `test_stale_racing_run_reports_version_conflict_before_watermark` 断言两种迟到情况（不带 watermark；watermark 介于两次推进之间）都报 `is at version 2, expected 1; nothing was registered`，且表、`run-2` 的 `rows_written`、checkpoint、`run-2` 的 manifest 和 checkpoint 历史都不变。撤销修复后该测试失败（见上）。原有 `test_watermark_cannot_move_backwards_or_disappear` 仍通过，探测 2 也确认版本正确时 watermark 后退仍被拒绝。`README.md:83` 和 ADR-003 第 19 行都没有写两项检查的先后，不需要改文档。 |
| B2-R3-1 | resolved | `e69f167` 把 `open_read_only` 改为 `path.absolute().as_uri()`；`test_read_only_open_accepts_a_relative_root` 通过，改回旧写法时这个测试以原生 `ValueError` 失败。 |
| B2-R1-1 ~ B2-R1-6 | resolved（维持） | 相关代码未变；`test_case_variant_path_cannot_register_the_same_file_twice`、`test_concurrent_reader_does_not_fail_a_commit`、`test_rollback_after_sqlite_auto_rollback_keeps_original_error`、`test_non_delete_journal_mode_is_rejected`、`test_watermark_cannot_move_backwards_or_disappear`、`test_registry_writer_cannot_create_ledger_files` 均通过。 |
| B2-R2-1、B2-R2-3 | resolved（维持，已采纳的 suggestion） | `mode=rw` 只读打开和 COMMIT 失败后的 ROLLBACK 包装未变。 |
| B2-R2-2 | out-of-scope（未变） | 已记入 `PLAN.md` §4c，由真实回填 PR 测量。 |

B2 验收示例（`PLAN.md` §4 B2）逐条对照，全部有通过的测试：校验和由账本计算（`test_commit_registers_manifest_and_advances_checkpoint`）；文件不存在、不在对应层、数据集未知、时间不是 UTC、范围颠倒时拒绝且账本不变（`test_invalid_commit_is_rejected_without_change` 的 11 个参数）；`expected_version` 不符时拒绝且不登记 manifest（`test_stale_checkpoint_version_registers_nothing` 和新测试）；运行已结束、同一路径重复登记被拒绝（`test_duplicate_registration_and_finished_run_rejected`）；未知 `user_version`、账本为软链接时拒绝打开（`test_ledger_persists_and_rejects_unknown_schema_or_symlink`）。验收示例中的“不在对应层”目前只查到层，不查到数据集目录，这正是 P1-F4。

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B2-R3-2 | owner-question（blocking） | `src/data_io/ledger.py` `commit_values`（`relative.parts[0] != layer` 只查第一级）；`docs/adr/ADR-003-pr2-sqlite-ledger.md:15` | P1-F4 尚未实现：数据集和目录对不上时照样登记（探测 1，5 个例子全部成功）。负责人已决定本 PR 处理，但路径规则要负责人选，见下方问题。 | 负责人回答后，由 Analyst 在 `commit_values` 中加检查（这样 `Run.commit_file` 会在写文件之前就拒绝），在 ADR-003 第 15 行写明规则；如果选了改目录约定的方案，同步改 `agent/PROJECT.md` §5 和 `docs/FOUNDATION_RULES.md` §7。测试至少包括：放到别的数据集目录、放在层根下、产品名不对，都被拒绝且账本不变；正确位置照常登记；bronze 不受影响。 |

### Owner questions

**问题（P1-F4，blocking）：一个数据文件必须放在哪个文件夹里，账本才允许登记？**

1. 背景：现在账本登记文件时，只检查它在不在正确的“层”（`bronze/`、`silver/`、`gold/`）下面，不检查它是不是放在自己数据集的文件夹里。
2. 场景（本轮实测）：一个任务把成交记录（数据集 `silver.trades`）写成了 `silver/markets/m.parquet`，账本照样登记成功。以后研究时读取 `silver/markets/` 下的全部文件，会把成交记录当成市场信息读进来；同样，`gold.market_1m` 的文件放进名为 `market_1s` 的文件夹也能登记。
   说明：不管选哪个方案，bronze 都只检查层。bronze 只有一个数据集 `bronze.raw`，放在 `bronze/` 下任何位置都不会和别的数据集混；它下面按来源分（例如 `bronze/kalshi/…`），保持不变。silver 也没有争议：第二级目录必须是数据集名，`silver/trades/…` 只能登记 `silver.trades`，和 `PROJECT.md` §5 现有的 8 个目录完全一致。**真正要选的是 gold。** gold 有 5 个产品，现有文档只给了 `market_1m` 一个路径示例：`gold/<venue>/<market_id>/market_1m/<数据版本>/<UTC 日期>.parquet`（产品名在第四级）；另外 4 个（`market_daily`、`market_1s`、`liquidity_features`、`training_datasets`）还没有路径约定。其中 `training_datasets`（训练集）一个文件里有很多市场的数据，没法放进“某个 venue 的某个市场”这样的文件夹。
3. 选项：
   - **A. 保留现有 gold 路径，产品名必须在第四级。** 例如 `gold/kalshi/MKT-1/market_1m/v1/20261113.parquet` 可以登记，`gold/kalshi/MKT-1/market_1s/…` 不能登记为 `market_1m`。还要再选一项：没有路径约定的 4 个产品怎么办：
     - A1：先按同样的形状要求（`gold/<venue>/<market_id>/<产品名>/…`）。代价：`training_datasets` 跨很多市场，放不进去，等于还是不能登记，或者以后要改规则。
     - A2：先拒绝登记，等以后做这些产品的 PR 定好路径再放开。代价：以后每做一个 gold 产品都要回来改账本规则。
     A 的共同代价：不用改文档；但规则依赖“第几级”，要求 venue 和市场 ID 都恰好只占一级目录（市场 ID 怎么安全变成目录名还没定）。
   - **B. gold 改成“产品名放第二级”，和 silver 用同一条规则。** 规则只有一句：silver 和 gold 的第二级目录必须是数据集名。`market_1m` 的路径变成 `gold/market_1m/<venue>/<market_id>/<数据版本>/<UTC 日期>.parquet`，内容和“一个文件只含一个市场、一个 UTC 日期”的规则都不变，只是产品名移到最前面；训练集可以放 `gold/training_datasets/<训练集名>/…`。会发生什么：5 个 gold 产品现在都能正确登记，不用猜。代价：要改你确认过的 `PROJECT.md` §5 和 `FOUNDATION_RULES.md` §7 中的 gold 路径示例；现在还没有任何 gold 文件，不用搬数据。第二级以下的结构（venue、市场、版本、日期）这次不检查，留给做各个 gold 产品的 PR。
   - **C. 在 registry 里给每个数据集写一个完整的路径模板**，例如 `silver.trades → silver/trades/<venue>/<日期>.parquet`，每一级都检查。会发生什么：最严格。代价：要改数据契约（registry 从 7.0.0 升版本），而且要为还没设计的 gold 产品现在就猜路径，猜错以后还得再改契约；改动最大。
4. 我的建议：**B**。一条规则就覆盖全部 14 个数据集，不用为还没设计的 4 个 gold 产品猜路径或先拒绝，跨市场的训练集也放得下；代价只是改两处文档里的示例，而且现在没有 gold 数据需要移动。（Analyst 推荐的是 A；如果你更想保留现有 gold 路径，我建议 A 里选 A2：先拒绝、等定好路径再放开，因为正确性优先，不猜。）

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `waiting for owner`。P1-F5 和 B2-R3-1 已 resolved；B2 之前所有 must-fix 和 should-fix 仍为 resolved；没有新的 must-fix 或 should-fix。lint、format 和全量测试（427 passed）由 Reviewer 在只含 B2 改动的独立 worktree 中亲自运行并通过。B2 不能收敛的唯一原因是 P1-F4 的 blocking 问题（B2-R3-2）：负责人回答后，由新的 Analyst 按答案实现，再由新的 Reviewer 复核。说明：以上只在本机（macOS、CPython 3.9.6）上运行。

负责人确认（2026-11-19）：B2-R3-2（P1-F4）选 B，silver 和 gold 的第二级目录必须等于数据集名，bronze 只查层；同步修改 PROJECT.md §5 和 FOUNDATION_RULES §7 的 gold 路径示例。

### Analyst response（Analyst 步骤，2026-11-19，由 Orchestrator 按 Analyst 回复填写）
| ID | Action | Detail and checks |
| --- | --- | --- |
| B2-R3-2 | fixed（负责人选 B） | `commit_values`：非 bronze 数据集要求路径至少三段且第二段等于数据集名（区分大小写），否则 `LedgerError`；`Run.commit_file` 在写文件前调用它，放错位置的文件不会写入。测试：`test_file_outside_its_dataset_folder_is_rejected_without_change`（8 个参数）、`test_files_in_their_dataset_folder_register`（13 个 silver/gold 数据集 + 3 个真实形状）、`test_bronze_files_are_checked_by_layer_only`、`tests/test_runs.py::test_file_outside_its_dataset_folder_is_not_written`。文档：ADR-003、`agent/PROJECT.md` §5、`docs/FOUNDATION_RULES.md` §7 的 gold 路径改为产品名在第二级，README、CHANGELOG 各加一条。Analyst 检查：ruff、format 通过；全量 447 passed（含 B1 未提交改动）；关掉新检查后 9 个新测试失败。 |

## Block B2 · Round 4 · 2026-11-19

**结论先说：** P1-F4（数据文件必须放在自己数据集的文件夹里）已按负责人选的方案 B 正确实现，P1-F5（版本检查先于 watermark 检查）维持正确。没有新的 must-fix 或 should-fix，只有 1 条措辞上的 suggestion。lint、format 和全量测试（447 passed）由我在独立 worktree 中亲自运行并通过。本轮结果：`converged`。

先解释两个词：
- **路径的第几段**：路径按 `/` 切开后的每一部分。例如 `gold/market_1m/kalshi/MKT-1/v1/20261113.parquet` 的第一段是层 `gold`，第二段是 `market_1m`。
- **变异检查**：故意把新加的检查关掉或改坏，看测试会不会失败。测试失败，说明它真的在保护这条规则。

- Revision: `codex/pr2-run-ledger` @ `4cd778e`（HEAD）+ B1 的 `b1-round5.patch`（作为底座，不在本轮审查范围）+ B2 的 `b2-round4.patch`；B2 补丁涉及的文件：`src/data_io/ledger.py`、`tests/test_ledger.py`、`tests/test_runs.py`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`、`agent/PROJECT.md`、`docs/FOUNDATION_RULES.md`、`README.md`、`CHANGELOG.md`。两份补丁都能干净应用（`git apply --check` 通过）。应用后 worktree 中 12 个对比文件与主工作区当前未提交内容逐字节一致（`cmp`），即 revision packet 与磁盘一致。
- Addresses: P1-F4（B2-R3-2，负责人 2026-11-19 选 B）；复查 P1-F5；同时复查 B2 之前所有发现。
- 审查方式：在本会话 scratchpad 中 `git worktree add --detach <scratchpad>/wt-b2r4 HEAD`，依次 `git apply` B1、B2 补丁，所有检查和探测都在其中运行。结束后 `git worktree remove --force`，`git worktree list` 只剩主工作区和另一位 Reviewer 的 `wt-b1r5`（未动）；探测目录已删除。
- Checks run by Reviewer（均在上述 worktree 内，CPython 3.9.6）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v` → 447 passed in 8.19s
  - `uv run pytest tests/test_ledger.py tests/test_runs.py tests/test_audit.py -q` → 62 passed
  - **变异检查 1**（把 `if layer != "bronze":` 临时改成 `if False and layer != "bronze":`，即关掉新检查）：`uv run pytest tests/ -q` → 9 failed, 438 passed。失败的正是 `test_file_outside_its_dataset_folder_is_rejected_without_change` 的 8 个参数和 `tests/test_runs.py::test_file_outside_its_dataset_folder_is_not_written`，与 Analyst 所说一致。
  - **变异检查 2**（把比较改成不区分大小写 `relative.parts[1].casefold() != name`）：`uv run pytest tests/test_ledger.py -q` → 1 failed（`silver/Trades/a.parquet` 那一例）。说明“区分大小写”有测试保护。
  - **变异检查 3**（去掉“至少三段”的条件 `len(relative.parts) < 3 or`）：`uv run pytest tests/ -q` → 2 failed（`silver/trades`、`gold/market_1m` 这两个“文件名就叫数据集名、直接放在层下”的例子）。说明“至少三段”也有测试保护。
  - **变异检查 4**（P1-F5：把 B2 补丁中调换检查顺序的那一段反向应用，恢复旧顺序）：`uv run pytest tests/test_ledger.py -q -k "stale_racing or watermark"` → 1 failed, 1 passed，失败的 `test_stale_racing_run_reports_version_conflict_before_watermark` 报的是旧的 `watermark cannot move backwards`。每次变异后都把 `ledger.py` 恢复，并用 `cmp` 确认与主工作区一致。
  - **探测**（scratchpad 脚本，未入库，`PYTHONPATH=. uv run python <scratchpad>/probe-b2r4/probe.py <dir>`）：`silver/./trades/a.parquet`、`./silver/trades/b.parquet`、`silver//trades/c.parquet` 登记成功，账本里存的是规范写法 `silver/trades/…`（Python 的 `Path` 会去掉多余的 `.` 和 `/`，这是原有行为）；`silver/trades/sub/../d.parquet` 被原有的“不能含 `..`”规则拒绝；`silver/trades /e.parquet`（目录名末尾多一个空格）和 `silver/trades.parquet/h` 被新检查拒绝，报 `silver.trades file must be under silver/trades/`；`gold/market_1m/f.parquet`、`gold/training_datasets/g.parquet`（直接放在产品目录下，没有更深的子目录）登记成功，这符合“第二级以下不检查”的决定，但见 B2-R4-1。
  - **旧 gold 路径残留**：`grep -rn "gold/" agent docs README.md CHANGELOG.md src tests .claude AGENTS.md`（排除 `docs/pr2/`）和 `grep -rniE "<venue>/<market|venue>/<market_id>|产品名在|第四级|silver/<|gold/<"`：正式文档、代码注释、`.claude/` 和 `agent/` 中已没有“产品名在第四级”的旧写法；`docs/SCHEMAS.md`、`docs/SCHEMA_GUIDE.md`、`schema_registry.json` 只出现产品名，没有路径；README 和 `runs.py` 文档字符串中的示例路径 `silver/trades/x.parquet` 符合新规则。唯一残留是过程记录 `docs/pr2/PROGRESS.md:27` 描述 P1-F4 时引用的旧例子 `gold/<venue>/…`；它是当时问题的描述，不是规则，由 Orchestrator 更新快照时处理即可，不算发现。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B2-R3-2（P1-F4） | resolved | `ledger.py:235-243`：非 bronze 数据集要求路径至少三段，且第二段与数据集名完全一致（区分大小写），否则报 `LedgerError("<数据集> file must be under <层>/<名字>/: <路径>")`。检查在 `commit_values` 中，`Ledger.commit`（`:524`）和 `Run.commit_file`（`runs.py:172`，在 `write_new` 之前）都调用它，所以放错位置时既不登记也不写文件。测试覆盖：别的数据集目录（`silver/markets/` 放 `silver.trades`；`gold/market_1s/` 放 `gold.market_1m`；`gold/market_1m/` 放 `gold.training_datasets`）、直接放在层下（`silver/a.parquet`，以及文件名恰好叫 `silver/trades`、`gold/market_1m`）、旧 gold 路径（产品名在第四级）、大小写不同（`silver/Trades/`），每例都断言账本三张表和 checkpoint 历史不变；13 个 silver/gold 数据集各在自己目录下登记成功，另有 3 个真实形状的路径；bronze 第二段是来源（`bronze/kalshi/…`）照常登记，`bronze.raw` 放在 `silver/` 下仍被拒绝；`Run.commit_file` 4 种放错位置都被拒绝，且 `silver/`、`gold/` 目录保持为空，之后正确位置的文件正常登记、checkpoint 推进到 1、`rows_written` 为 2。变异检查 1–3 证明三个条件各自都有测试保护。文档：ADR-003 第 16 行、`agent/PROJECT.md` §5（目录树与说明段）、`docs/FOUNDATION_RULES.md` §7（说明与路径示例）、README、CHANGELOG 都已改为“产品名在第二级”，与负责人决定（`PLAN.md` §4b，2026-11-19）一致；没有发现遗漏的旧写法。 |
| P1-F5 | resolved（维持） | 代码与第 3 轮确认时相同（版本检查在 watermark 检查之前，同一事务内）；变异检查 4 显示恢复旧顺序后 `test_stale_racing_run_reports_version_conflict_before_watermark` 失败；`test_watermark_cannot_move_backwards_or_disappear` 仍通过。 |
| B2-R3-1 | resolved（维持） | `open_read_only` 相关代码未变；`test_read_only_open_accepts_a_relative_root` 在全量测试中通过。 |
| B2-R1-1 ~ B2-R1-6、B2-R2-1、B2-R2-3 | resolved（维持） | 相关代码未变，对应测试全部在 447 个中通过。 |
| B2-R2-2 | out-of-scope（未变） | 已在 `PLAN.md` §4c。 |

`PLAN.md` §4 B2 的验收示例仍全部有通过的测试；其中“不在对应层”现在进一步检查到数据集目录（silver、gold）。

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B2-R4-1 | suggestion | `docs/adr/ADR-003-pr2-sqlite-ledger.md:16` | 措辞比代码严格。ADR 写“`gold.market_1m` 只能登记 `gold/market_1m/<venue>/<market_id>/…`”“`gold.training_datasets` 只能登记 `gold/training_datasets/<训练集名>/…`”，但代码只查第二段，探测中 `gold/market_1m/f.parquet`、`gold/training_datasets/g.parquet`（没有 venue、市场或训练集名这一级）都能登记。同一句后面虽然写了“第二级以下的结构不检查”，但只读前半句的人会以为 venue、市场那几级也被检查了。这与负责人决定一致（第二级以下留给以后的 PR），只是说法容易误读，所以不阻塞。README 的写法（先给示例，再写 “Levels below the dataset folder are not checked yet”）没有这个问题。 | 把“只能登记”改为“只能登记在 `gold/market_1m/` 下（目标路径为 `gold/market_1m/<venue>/<market_id>/…`）”之类，让“检查的是哪一级”和“约定的完整路径”分开写。可在下次改 ADR-003 时顺手处理。 |
| B2-R4-2 | out-of-scope | `src/data_io/audit.py` | `audit` 不会重新检查已登记文件是否在自己数据集的目录里（Analyst 已在 packet 中说明）。现在这不是问题：账本是本 PR 新建的，从第一条记录起就受这条规则约束，不存在规则之前登记的文件。将来如果某个 gold 产品的 PR 收紧第二级以下的规则，已登记的旧文件不会被自动复查。 | 交给 Reporter，作为后续 gold 产品 PR 的提醒：收紧路径规则时，同时让 `audit` 复查已登记文件的路径。 |

### Owner questions
无。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `converged`。B2 之前所有 must-fix 和 should-fix 都已 resolved；B2-R3-2 的 blocking 问题负责人已回答（选 B），代码和文档按答案实现；本轮没有新的 must-fix 或 should-fix（B2-R4-1 为 suggestion，B2-R4-2 为 out-of-scope，均交给 Reporter）；lint、format 和全量测试（447 passed）由 Reviewer 亲自运行并通过。说明：检查只在本机（macOS、大小写不敏感的 APFS、CPython 3.9.6）上运行；本轮的底座包含 B1 第 5 轮补丁，B1 本身由另一轮审查，如果 B1 补丁之后变化，B2 不受直接影响，但提交时应以最终合在一起的代码再跑一次全量测试。

## Block B1 · Round 5 · 2026-11-19

**结论先说：** 负责人选的两个做法都已实现，而且主要效果我亲自验证过：P1-F2 的唯一入口 `open_write_layout(config)` 顺序正确（先检查、再建目录、用配置里的秒数）；P1-F3 的“等通知”确实解决了“连续写时另一个任务抢不到锁”的问题（换回旧的轮询写法，新测试 3 次都失败；新写法下等待者每次约 3–17 毫秒拿到锁）。B1-R4-1、B1-R4-2 已修好。但还有三处 should-fix：(1) 防止绕过入口的源码扫描测试有漏洞，最普通的写法 `layout.DataLayout.create(...)` 就能绕过；(2) 每次“等不到、放弃”都会留下一个后台帮手和一个打开的文件，同一个程序反复重试会把“可打开文件数”用完，文档没写；(3) 程序在放弃等待之后再“分身”（fork），分身出来的子程序会一直占着锁。另有一个 suggestion。本轮结果：`changes requested`。

先解释几个词：
- **后台帮手（线程）**：同一个程序里同时干另一件事的帮手。新写法里，帮手负责“排队等钥匙”，主程序负责计时。
- **文件句柄**：程序每打开一个文件，操作系统就发给它一个“号码牌”；号码牌有上限（macOS 终端默认常见为 256，Linux 常见为 1024），用完后程序再打开任何文件都会失败。
- **fork（分身）**：一个程序把自己复制成两个；复制出来的子程序会带着父程序所有打开文件的号码牌副本。Python 的 `multiprocessing` 在 Linux 上（Python 3.13 及以前）默认就用这种方式起子进程。

- Revision: `codex/pr2-run-ledger` @ `4cd778e` + B1 补丁 `<scratchpad>/b1-round5.patch`。按隔离要求，我在 scratchpad 里 `git worktree add --detach <scratchpad>/wt-b1r5 HEAD`，`git apply` 补丁，`git status --short` 显示 8 个文件被修改：`CHANGELOG.md`、`README.md`、`docs/adr/ADR-003-pr2-sqlite-ledger.md`、`src/config/README.md`、`src/config/README_FOR_DEVELOPER.md`、`src/data_io/layout.py`、`src/data_io/runs.py`、`tests/test_writer_recovery.py`，与 packet 一致，没有未跟踪文件。全部阅读、检查和探测都在这个 worktree 里做，没有看主工作区里 B2 正在改的副本。
- Addresses: B1-R4-1、B1-R4-2、P1-F2（负责人选 A）、P1-F3（负责人选 B，附两个条件）。
- Checks run by Reviewer（全部在 worktree 中，CPython 3.9.6，macOS，除非另注）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v -p no:cacheprovider` → **435 passed** in 7.98s（= 第 4 轮的 426 + 本轮新增 9 个；Analyst 的 436 含 B2 未提交的测试，这里没有）。
  - **重复跑，查是否偶发失败**：`uv run pytest tests/test_writer_recovery.py -q -p no:cacheprovider -k "waiter or zero_timeout or successful_wait or interrupted_wait or back_to_back or open_write_layout or lock"` 连续 30 次 → 30/30 通过（每次 26 passed, 41 deselected）。
  - **加负载再跑**：12 核机器上起 24 个 `yes > /dev/null` 占满 CPU，同时 6 个上面的 pytest 并行，共 3 轮 → 18/18 退出码 0，每次 26 passed（4.86–5.11 秒）。
  - **Python 3.13.18**（scratchpad 临时环境 `uv venv --python 3.13` + `uv pip install --offline pydantic python-dotenv pytest duckdb pyarrow`，结束后已删除）：全量 `python -m pytest tests/ -q -p no:cacheprovider` → 2 failed, 433 passed，失败的只是已知的 B1-R4-3（PR1 的 `test_excessively_nested_source_json_retains_evidence`）；上面的锁测试连跑 10 次 → 10/10 通过。
  - **新测试能不能抓住旧问题**：把 worktree 里的 `_lock` 临时换回 HEAD 的轮询版本，`-k back_to_back` 跑 3 次 → 3/3 failed（B 的 `DataLayout.create(root, lock_timeout_seconds=2)` 等满 2 秒报 `WriteBoundaryError`）；换回补丁版本 → 1 passed。负责人条件 1 满足。
  - **等待速度实测**（scratchpad 脚本 `fair.py`：子进程 A 不停写 1 字节文件，主进程 B 用 2 秒等待时间写 50 个文件，每次之间停 20 毫秒，跑 3 遍）：B 每次写入（含等锁和自己写文件）中位数 6.7–7.6 毫秒，最慢 10.8–17.4 毫秒；同期 A 写了 301–308 个文件。与文档“约 10 毫秒”大体一致。
  - **线程/句柄探测**（`threads.py`）：① 另一个句柄一直占锁，用 1 秒等待重试 10 次：每次 1.00–1.01 秒报错，后台帮手和多占的文件句柄从 1 个涨到 10 个；放开锁后 0.001 秒内全部退出、句柄全部归还、锁是空的、没有写出任何文件。② 同一线程已经拿着锁，再用 1 秒等待写：1.00 秒后报 `WriteBoundaryError`（不会死锁），外层放锁后帮手退出、锁空、句柄归还。③ 同一进程另一个线程占锁 0.3 秒：主线程 0.310 秒拿到锁，之后无残留。④ `DataLayout.create` 等 1 秒：1.01 秒报 `WriteBoundaryError`，之后无残留。
  - **句柄耗尽探测**（`emfile.py`，`ulimit -n 24`，起始占用 6 个）：一直占锁、1 秒等待反复重试，第 19 次报 `WriteBoundaryError: ... Too many open files`，此时同一程序里打开 `/dev/null` 也失败；放开锁后句柄恢复、再写成功。见 B1-R5-2。
  - **fork 探测**（`fork.py`）：一次等待放弃后（帮手仍在等），程序 `os.fork()` 出一个睡 3 秒、完全不碰锁的子进程；原占锁者放锁 0.5 秒后，从外面看锁**仍被占**；子进程退出后锁才空出来。见 B1-R5-3。
  - **打断时机探测**（`interrupt.py`）：把 `_LockWaiter.take` 临时换成“一进来就抛 `KeyboardInterrupt`”，模拟 Ctrl-C 恰好落在“帮手已启动、`take` 还没进入 `try`”的瞬间：调用方收到中断后，占锁者放锁 0.5 秒，锁仍被占，帮手线程已结束（0 个），同一程序下一次写报 “waited 0s”。见 B1-R5-4。
  - **源码扫描测试探测**：在 worktree 的 `src/` 临时放一个 `_probe_bypass.py`，逐个换成 5 种写法后跑 `-k only_open_write_layout`：`L.DataLayout.create(root)`（`from src.data_io import layout as L`）→ 1 passed（没抓到）；`Layout.create(root)`（`import DataLayout as Layout`）→ passed；`DataLayout(root=root).writer` → passed；`ScopedWriter(root=root, role=...)` → passed；`DataLayout.create(root)` → 1 failed（抓到）。见 B1-R5-1。之后删除该文件。
  - **硬规则 8–11 与文档对照**：见下方表格。
  - 结束后 `git worktree remove --force <scratchpad>/wt-b1r5`，`git worktree list` 只剩主工作区 `4cd778e [codex/pr2-run-ledger]`；探测脚本、临时环境、输出文件都已删除。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R4-1 | resolved | `README.md:60`、`src/config/README.md:29`、`README_FOR_DEVELOPER.md:29` 都改为“每次访问账本最多等 `max(writer_lock_timeout_seconds, 5)` 秒；`Run.commit_file` 访问两次；卡在写前检查时文件不写入，卡在写后登记时文件已写入但未登记，由 `audit` 报告”，与第 4 轮实测的两种情况一致；“最多 5 秒”的总时长说法已删除。CHANGELOG 第 10 行也同步写清 `.writer.lock` 与账本锁分开。 |
| B1-R4-2 | resolved | `tests/test_writer_recovery.py:537-539` 加了 `ids=["zero_padded_5", "all_zeros"]`，`pytest -v` 输出中显示为 `[zero_padded_5]`、`[all_zeros]`。 |
| P1-F2（负责人选 A） | resolved（入口本身）；测试有漏洞，见 B1-R5-1 | `layout.py:464-474`：先类型检查，再 `validate_for_write()`，再用 `config.writer_lock_timeout_seconds` 调 `DataLayout.create`。`test_open_write_layout_uses_configured_timeout`（配置为 3 → layout 和 writer 都是 3）、`test_open_write_layout_runs_write_preflight_before_layout`（空间不足时 `ConfigError` 且 `DATA_ROOT` 不存在；调用顺序为 `["validate_for_write", "create"]`）都通过。`load(environ=...)` 传了 `environ` 时不读 `.env`（`loader.py:48`），测试与本机环境隔离。文档示例（README、`src/config/README.md`、`runs.py` 模块说明）都改用 `open_write_layout`。`Run.start` 的一致性检查仍在（`runs.py:121-122`）。 |
| P1-F3（负责人选 B） | resolved（做法本身）；附带问题见 B1-R5-2 ~ B1-R5-4 | `layout.py:106-200`：先试 `LOCK_NB`；超时 0 直接报错、不起线程（`test_zero_timeout_fails_immediately_without_waiter_thread` 把 `_LockWaiter` 换成会报错的替身仍通过）；否则后台线程用自己的句柄阻塞 `flock`，主线程 `Event.wait` 计时；放弃后帮手拿到锁立刻关闭句柄（我的探测 ① ④ 和 `test_waiter_that_gave_up_releases_lock_as_soon_as_it_gets_it` 都确认）；帮手出错时原样抛出 `OSError`，由 `write_new`（`:517-518`）和 `create`（`:455-456`）统一转成 `WriteBoundaryError`（`test_waiter_lock_error_is_reported_without_writing`、句柄耗尽探测都看到 `WriteBoundaryError`）。负责人条件 1：`test_waiting_writer_gets_lock_while_another_process_writes_back_to_back` 在新写法下 30 次 + 负载 18 次 + 3.13 下 10 次全部通过，换回轮询 3/3 失败。条件 2：没有 Linux；README:58、ADR-003:29-31、`src/config/README.md:29`、CHANGELOG:16、`layout.py` 模块说明和类说明都写明“只在 macOS 验证过”。PLAN §4 B1 验收：超时 0 立即失败、超时 1 秒约 1 秒失败且数据不变、等待中释放则成功、非法值被拒绝，都有通过的测试，我的探测也看到 1.00–1.01 秒。 |
| B1-R4-3 | out-of-scope（未变） | 3.13.18 上仍是那 2 个 PR1 用例失败，与 B1 无关。 |
| B1-R2-1、B1-R1-1 ~ B1-R1-7 | resolved（维持） | 相关代码未变，测试在 435 个中通过。 |

**硬规则 8–11 核对：** 规则 8：`open_write_layout` 只用 `validate_for_write()` 返回的、由 `DATA_ROOT` 得到的路径，写入仍走分层 writer。规则 9：入口内先 `validate_for_write()` 再 `DataLayout.create`，测试证明了顺序和“检查失败不建目录”；但直接构造 `DataLayout(...)`/`ScopedWriter(...)` 能跳过检查，见 B1-R5-1。规则 10：等锁秒数只来自配置，没有新增散落的数字。规则 11：`src/config/` 本轮只改了 `README.md` 和 `README_FOR_DEVELOPER.md` 两份文档，两份同步更新，没有改配置代码；`layout.py` 引入 `src.config.PipelineConfig`，`src/config/` 不反向引用 `data_io`，没有循环引用。

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R5-1 | should-fix | `tests/test_writer_recovery.py:817-837`；文档 `README.md:56`、`src/config/README_FOR_DEVELOPER.md:29`、ADR-003:28、CHANGELOG:11 | 负责人的决定是“加测试禁止 `src/` 里其他地方直接调用 `DataLayout.create(`”。现在的扫描只认“`DataLayout` 这个名字后面紧跟 `.create`”。实测：PR3 的人如果写 `from src.data_io import layout` 然后 `layout.DataLayout.create(root)`——代码里明明有 `DataLayout.create(` 这几个字——测试照样通过。另外，直接写 `DataLayout(root=root)` 或 `ScopedWriter(root=root, role=...)` 也能拿到可写的 writer，而且比绕过 `create` 更糟：既不做写前检查（硬规则 9），也不扫描遗留的半成品文件，等锁秒数还是 0。例子：下载器写成 `ScopedWriter(root=Path(os.environ["DATA_ROOT"]), role=WriterRole.COLLECTOR)`，磁盘快满也照写，锁被占立刻失败，测试全绿。文档却写“有测试拒绝直接调用”，读者会以为已经堵死了。 | (1) 扫描时把 `<任意>.DataLayout.create` 也算进去（`node.value` 是 `ast.Attribute` 且 `.attr == "DataLayout"`）；(2) 在 `layout.py` 以外，调用 `DataLayout(...)` 或 `ScopedWriter(...)` 也算违规（`layout.py` 里 `create` 的 `cls(...)` 和 `writer()` 本身除外）；(3) 把扫描逻辑抽成一个小函数，用几段写好的源码字符串（上面 5 种写法）测试它自己，证明真能抓到；(4) 文档如实写明还抓不到的情况（例如 `import DataLayout as X` 这类改名）。也可以另加一道纯文本检查 `DataLayout\s*\.\s*create\s*\(` 作为第二道网。 |
| B1-R5-2 | should-fix | `layout.py:106-200`（`_LockWaiter`）；文档 `README.md:58`、ADR-003:29、`src/config/README.md:29` | 每次“等不到、放弃”都会留下一个后台帮手**和一个打开的文件句柄**，直到锁空出来。同一个程序如果反复重试，它们会一直累积。实测：锁一直被占，用 1 秒等待重试 10 次，帮手和句柄各涨到 10 个；把可打开文件数限制为 24 时，第 19 次重试报 `Too many open files`，而且这时同一程序里打开任何文件（包括账本、运行记录）都会失败。时间线（推断）：10:00 回填任务 A 开始 `DataLayout.create`，要扫描和重新算校验和，持锁几分钟；同一台机器上的定时任务 B 用 1 秒等待、失败后每秒重试；按 macOS 常见上限 256 个，约 4 分钟后 B 不只是拿不到锁，连写日志文件、开账本都失败。锁一空所有句柄会立刻归还，数据不会坏，但报错原因会让人误以为是别的问题。文档只写了“该线程会一直阻塞到锁空出来”，没写“每放弃一次就多一个、并占一个文件句柄”。Analyst 在 packet 中承认了这个限制，但它没有进入文档。 | 至少：README、ADR-003、`src/config/README.md` 写明“每次放弃会留下一个后台线程和一个打开的文件，直到锁空出来；不要在同一个程序里用很短的等待时间反复重试，应改用一次较长的 `writer_lock_timeout_seconds`”。更好（推荐，改动小）：同一程序对同一个锁文件最多保留一个“已放弃但仍在等”的帮手，新的等待直接接手它（用一个按路径索引的表加互斥锁），这样重试次数再多也只占一个线程和一个句柄；并加测试：重试 10 次后帮手数仍为 1。 |
| B1-R5-3 | should-fix | `layout.py:106-200`（`_LockWaiter`） | 放弃等待后的帮手句柄一直开着；这时如果程序 fork 出子进程，子进程会带走这个句柄的副本。之后帮手拿到锁并关闭自己那一份，但子进程那份还开着，锁就一直被占，直到子进程退出。实测：放弃一次后 fork 一个睡 3 秒、从不碰锁的子进程，原占锁者放锁 0.5 秒后锁仍被占，子进程退出后才空出来。例子（推断）：PR3 的下载器在 Linux 上用 `multiprocessing` 起一个长期运行的工作进程池；某次写入等锁超时被重试逻辑接住后，程序再起进程池，于是整台机器上所有写任务都会一直“等锁超时”，而占锁的竟是一个从来不写数据的工作进程，半夜排查非常困难。旧的轮询写法只在调用者正在等或正在写的那一刻有这个风险；新写法把风险延长到“放弃之后、锁空之前”的整段时间。当前代码里没有 fork，所以现在不会发生。 | 用 `os.register_at_fork(after_in_child=...)` 在子进程里关闭所有仍存在的帮手句柄（子进程里没有帮手线程，关掉是安全的；需要一个记录存活帮手的集合），加一个用 `os.fork()` 的测试（子进程存活期间锁能被别人拿到）。如果 Analyst 认为现在不值得改代码，至少在 README 和 ADR-003 写明“写任务不要在等锁失败后 fork 子进程；用 `multiprocessing` 时请用 `spawn` 方式”。 |
| B1-R5-4 | suggestion | `layout.py:125-130`、`:192` | 测试名说“打断不会留下锁”，大体成立，但有两个很窄的时间缝：(a) Ctrl-C 恰好落在 `_LockWaiter(path)` 返回之后、`take()` 进入 `try` 之前：没人把帮手标记为“已放弃”，帮手拿到锁后就一直拿着（实测模拟：中断后锁一直被占，同一程序下一次写失败），直到程序退出；(b) Ctrl-C 恰好落在 `self._thread.start()` 内部等待线程启动时：`except` 分支会关闭一个帮手线程可能正在用的句柄，帮手随后可能再关一次同一个号码，而这个号码可能已被别的文件（例如账本）重新使用。通常 Ctrl-C 会让程序退出，系统会收回所有句柄，所以实际影响很小。 | 把 `self._thread.start()` 挪进 `take()` 的 `try/finally` 里（或在 `_lock` 里用 `try/except BaseException` 包住“创建帮手 + take”，异常时标记放弃）；`start()` 失败时只有在线程确实没启动（`self._thread.ident is None`）时才关闭句柄。测试名或注释改成不那么绝对的说法。 |

### Owner questions
无。上面三条 should-fix 都有明确的工程做法，不涉及需要负责人取舍的设计选择；负责人已接受的“放弃后帮手会留到锁空出来”这一点不变。说明：fork 和句柄问题都是在 macOS 上实测的，Linux 未测；另外按 Linux 的实现推断，放锁时所有等待者被唤醒后要重新抢，放锁的一方紧接着再拿锁也可能抢到，所以负责人条件 2 中“合并前在 Linux 上跑一次连续写测试”仍然很有价值（文档已按条件写明只在 macOS 验证过）。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `changes requested`。B1-R4-1、B1-R4-2 已 resolved；P1-F2、P1-F3 按负责人的选择实现，负责人两个条件都满足；但 B1-R5-1、B1-R5-2、B1-R5-3 三条 should-fix 未解决，B1 尚未收敛。lint、format、全量测试（435 passed）由 Reviewer 本轮亲自在隔离的 worktree 中运行通过；新锁测试重复 30 次、加负载 18 次、3.13 下 10 次均无偶发失败。

### Analyst response（Analyst 第 6 步，2026-11-19，由 Orchestrator 按 Analyst 回复填写）
| ID | Action | Detail and checks |
| --- | --- | --- |
| B1-R5-1 | fixed | 扫描抽成 `_layout_bypasses(source, filename)`：`src/` 中除类型标注、`isinstance`/`issubclass` 的类参数、普通导入外，任何对 `DataLayout`/`ScopedWriter` 的名字或属性引用都算违规（改名导入也算）；只允许 `layout.py` 的 `open_write_layout` 和 `DataLayout.writer`，并断言这两处存在。新测试覆盖 11 种绕过写法（含 Reviewer 的 5 种）、合法写法不误报、报告位置正确。抓不到的写法（`type(layout)(...)`、`__class__`、`dataclasses.replace`、运行时字符串查找、`src/` 以外）写进 README、ADR-003、CHANGELOG、两份 config README、`open_write_layout` 说明。 |
| B1-R5-2 | fixed | `layout.py` 新增按锁文件 `(st_dev, st_ino)` 记录的空闲等待者表；新的等待优先接手“已放弃但仍在等”的帮手；单线程重试最多 1 个帮手和 1 个句柄。3 个新测试；关掉接手后其中 2 个失败。探测：`ulimit -n 24`、1 秒等待重试 30 次，始终 1 个帮手、多占 1 个文件，放锁后归还并写入成功。多线程同时等待时各留一个，已写进文档。 |
| B1-R5-3 | fixed | `os.register_at_fork`：fork 前拿住表锁，子进程中关闭所有帮手句柄并清空表。新测试 `test_forked_child_does_not_keep_an_abandoned_waiter_lock`（无 fork 时跳过）；去掉登记后测试失败。持锁写文件期间 fork 仍会继承锁（与改动前相同），已写进 README、ADR-003。 |
| B1-R5-4 | fixed（采纳 suggestion） | 选帮手、`thread.start()`、等待都放进 `_wait_for_lock` 的 `try/finally`；被打断时未拿到锁的帮手放回空闲表、已拿到的句柄关闭；`start()` 失败时只关闭句柄。2 个新测试；把 `start()` 挪回 `try` 外后测试失败。剩余字节码级空隙写在文档字符串中（不会占着锁）。 |

Analyst 检查：ruff、format 通过；全量 466 passed（含 B2 未提交测试）；锁相关测试连跑 30 次、负载下 18 次、Python 3.13 上 10 次全部通过（3.13 全量仍有已知的 B1-R4-3 两个失败）。只在 macOS 运行。

## Block B1 · Round 6 · 2026-11-19

**结论先说：** 上一轮的三条 should-fix 和一条 suggestion 都按要求做了，我用自己的探测逐条确认：(1) 源码扫描现在能抓住所有“写出了类名”的绕过写法；(2) 同一线程反复放弃等待，始终只多 1 个后台帮手、1 个打开的文件；(3) 放弃等待后 fork，子进程不再占着锁（关掉新加的 fork 钩子，问题立刻重现）；(4) 两个被点名的打断时间缝已堵上。lint、format、全量测试（466 passed）都通过。**但新加的“帮手复用”引入了一个真正的锁错误（B1-R6-1，must-fix）**：同一个程序里有两个线程在等同一把锁时，先放弃的那个线程可能误以为自己拿到了锁，于是两个线程同时在写。另有一条 suggestion（B1-R6-2）。本轮结果：`changes requested`。

先解释几个词：
- **线程**：同一个程序里同时干活的几个“帮手”。本轮的问题只在“一个程序里有几个线程同时等锁”时出现；只有一个线程的程序不受影响。
- **模块互斥锁 `_WAITERS_MUTEX`**：程序内部的一把小锁，保证“空闲帮手表”同一时间只被一个线程修改。
- **复用（reuse）**：上一次等锁放弃后，后台帮手还在排队；下一次等锁直接接手这个帮手，而不是再开一个。

- Revision: `codex/pr2-run-ledger` @ `4cd778e` + `<scratchpad>/all.patch`（B1 + B2 未提交改动）。按隔离要求在 `<scratchpad>/wt-b1r6`（`git worktree add --detach … HEAD` 后 `git apply all.patch`）中审查；`git status --short` 显示 13 个修改文件、没有未跟踪文件。逐个 `cmp` 与主工作区对比，13 个文件完全一致，packet 与磁盘相符。为了只看本轮变化，另建 `<scratchpad>/wt-r5base`（HEAD + `b1-round5.patch`）做对比：本轮 B1 改动集中在 `src/data_io/layout.py`（帮手表、`_wait_for_lock`、fork 钩子）、`tests/test_writer_recovery.py`（扫描函数和 10 个左右新测试）以及 README、CHANGELOG、ADR-003、两份 `src/config` README 的相关段落；`src/data_io/runs.py` 与第 5 轮相同。B2 的改动不在本轮审查范围，只确认整体测试通过。
- Addresses: B1-R5-1、B1-R5-2、B1-R5-3、B1-R5-4（suggestion，Analyst 采纳）。
- Checks run by Reviewer（worktree 中，macOS，CPython 3.9.6，除非另注）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v -p no:cacheprovider` → **466 passed** in 12.40s（含 B2 已收敛的测试）。
  - 锁相关测试重复跑：`.venv/bin/python -m pytest tests/test_writer_recovery.py -q -p no:cacheprovider -k "waiter or zero_timeout or successful_wait or interrupt or back_to_back or open_write_layout or lock or fork or layout_bypass or reuse or bounded"` 连续 30 次 → 30/30 通过（每次 47 passed, 39 deselected）。
  - 加负载：24 个 `yes > /dev/null` 占满 12 核，同时 6 个上面的 pytest 并行，共 3 轮（`<scratchpad>/probe-b1r6/load.sh`）→ 18/18 退出码 0，每次 47 passed（9.3–9.5 秒）；其中一次有 pytest 自己清理临时目录时的 `PytestWarning`（并行运行互相删目录），与本项目代码无关。
  - **Python 3.13.18**（临时环境 `uv venv --python 3.13` + `uv pip install --offline pydantic python-dotenv pytest duckdb pyarrow`，结束后已删除）：全量 `python -m pytest tests/ -q -p no:cacheprovider` → 2 failed, 464 passed，失败的仍只是已知的 B1-R4-3（PR1 的 `test_excessively_nested_source_json_retains_evidence`）；锁测试连跑 10 次 → 10/10 通过。
  - **多线程竞争探测**（见 B1-R6-1）：`race.py` 强制制造先后顺序 → 3/3 次出现“线程 1 报告拿到锁但手里没有句柄、锁其实在线程 2 手里”；`stress.py`（不改任何代码，8 个线程用 0.5 毫秒超时反复等锁，另一个进程不停拿锁放锁，各 10 秒）在 `sys.setswitchinterval(1e-6)` 下 3 次分别出现 5、11、13 次“两个线程同时在临界区”；默认切换间隔（5 毫秒）下 3×10 秒没有出现。
  - **扫描绕过探测**：在 worktree 的 `src/` 临时放 `_probe_bypass.py`，逐个换 13 种写法跑 `-k only_open_write_layout`：`DataLayout.create(root)`、`layout.DataLayout.create(root)`、`from … import *` 后调用、`class Mine(DataLayout)`、`typing.Optional[L.DataLayout]` → 都被抓到（最后一种是误报，但会大声失败，无害）；`getattr(layout, "Data"+"Layout")`、`layout.__dict__["DataLayout"]`、`dataclasses.replace(lay, …)`、`type(lay)(…)`、`lay.__class__.create(…)`、`type(w)(…)` → 没抓到，正是文档列出的“抓不到”的写法；另外 `def f(a: DataLayout.create(root))` 这种把调用写进类型标注的怪写法没抓到（标注被整体跳过），不现实，不算发现。之后删除该文件，`git status` 确认已删。
  - **反复放弃 + 低句柄上限**（`emfile.py`，`ulimit -n 24`）：锁一直被另一个句柄占着，1 秒等待重试 30 次 → 第 1、10、30 次时都是 1 个帮手、多占 1 个文件、`_WAITER_HANDLES` 里 1 个；没有出现 “Too many open files”；放锁后帮手退出、句柄归还、表清空、再写成功。
  - **fork 探测**（`fork2.py`，锁由一个独立进程占着）：放弃等待后 `os.fork()` 一个睡 3 秒的子进程 → 放锁 0.5 秒后锁是空的；用 `multiprocessing` 的 `fork` 方式起子进程 → 同样是空的；对照组（fork 前临时清空 `_WAITER_HANDLES`，模拟没有钩子）→ 锁仍被子进程占着，说明是钩子在起作用。`fork.py` 第 3 段：4 个线程不停等锁、另一个线程不停拿锁放锁，主线程 5 秒内 fork 5253 次，子进程都能在 1 秒内拿到模块互斥锁且表为空，没有死锁，结束后无残留。
  - **锁文件被替换**（`replace.py`）：帮手在旧锁文件上排队时删除 `.writer.lock`，之后的写在新文件上 0.008 秒成功；新旧文件的空闲帮手分别按 inode 记录、互不复用；两边放锁后表清空、无残留线程。
  - **真实信号打断探测**（见 B1-R6-2）：`intr2.py`/`intr5.py` 用 `SIGALRM` 在随机时刻（20 微秒–4 毫秒）抛 `KeyboardInterrupt`，循环 `with _lock(root, 1)` 约 6–8 秒，另一个进程用非阻塞方式不停拿锁放锁。本轮代码 3.9 上共 17 次：13 次结束时锁仍被本进程占着，1 次正常，2 次卡死（其中 1 次用 `faulthandler` 抓到栈：主线程永久卡在 `layout.py:225` 的 `with _WAITERS_MUTEX`，另一次只看到主线程在等一把 Python 锁），1 次没有打印结果（原因未查）；3.13 上 12 次：5 次锁被占着，2 次正常，5 次没有打印结果（原因未查，看门狗未触发，所以不是卡死）。HEAD（旧的轮询写法）3.9 上 11 次中 1 次锁被占着，没有卡死。各版本都会漏掉几十个“没拿锁”的句柄。定位到的打断点都在 `_lock` 的 `finally`（`for handle in (fd, *waited)`、`if handle is not None`、`os.close(handle)` 这几行）。
  - **硬规则 8–11 与文档对照**：见下方。
  - 结束后删除 `wt-b1r6`、`wt-r5base`、`wt-head` 三个 worktree 和 3.13 临时环境，`git worktree list` 只剩主工作区。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R5-1 | resolved | `tests/test_writer_recovery.py:1055` 的 `_layout_bypasses` 把除类型标注、`isinstance`/`issubclass` 类参数、普通导入外的所有 `DataLayout`/`ScopedWriter` 名字或属性引用都算违规，改名导入也算；`:1161` 的测试只允许 `layout.py` 的 `open_write_layout` 和 `writer` 两处，并断言这两处确实存在（允许清单不会悄悄失效）。11 种写法的参数化测试、合法写法不误报、报告位置正确都通过。我的 13 种写法探测：所有写出类名的都被抓到；抓不到的 6 种正是 README:56、ADR-003、CHANGELOG、两份 config README 列出的那几类（`type(...)`、`__class__`、`dataclasses.replace`、运行时字符串查找）。文档描述与代码一致。 |
| B1-R5-2 | resolved（单线程）；复用本身带来新问题，见 B1-R6-1 | 低句柄上限下重试 30 次始终 1 个帮手、1 个多占的文件；`test_repeated_abandoned_waits_reuse_one_waiter_and_handle`、`test_waiters_are_bounded_by_waits_in_progress_at_the_same_time` 通过。文档（README:58、ADR-003、CHANGELOG、`src/config/README.md`）写明“单线程反复重试最多多一个；几个线程同时等时各留一个”，与实测一致。 |
| B1-R5-3 | resolved | `layout.py:252` 用 `os.register_at_fork`：fork 前拿住模块互斥锁，子进程里关闭 `_WAITER_HANDLES` 中所有句柄并清空表。我的 `os.fork` 和 `multiprocessing`（fork 方式）探测都确认子进程不再占锁；去掉钩子的对照组重现原问题。fork 与等锁同时大量发生（5253 次）也没有死锁。`test_forked_child_does_not_keep_an_abandoned_waiter_lock` 通过。“持锁写文件期间 fork，子进程仍会继承锁”已写进 README、ADR-003，表述准确。 |
| B1-R5-4（suggestion） | resolved（两处点名的时间缝） | 选帮手、`thread.start()`、等待都进了 `_wait_for_lock` 的 `try/finally`；`start()` 里被 Ctrl-C 打断时帮手作为“未认领”放回表中（`test_interrupt_right_after_waiter_starts_does_not_leave_the_lock_held`），`start()` 真失败时只关句柄（`test_waiter_thread_that_cannot_start_closes_its_handle`）。更一般的“任意时刻被信号打断”见 B1-R6-2。 |
| P1-F2、P1-F3（负责人选 A、B） | 维持 resolved | 入口与“等通知”的做法没有变；负责人条件 1 的测试（连续写时另一任务能拿到锁）在 30 次重复、18 次负载、3.13 下 10 次中全部通过。条件 2：仍未在 Linux 上运行，文档照旧写明“只在 macOS 验证过”。 |
| B1-R4-3 | out-of-scope（未变） | 3.13.18 上仍是那 2 个 PR1 用例失败。 |
| B1-R4-1、B1-R4-2、B1-R2-1、B1-R1-1 ~ B1-R1-7 | resolved（维持） | 相关代码未变，测试在 466 个中通过。 |

**硬规则 8–11 核对：** 规则 8：本轮没有新增数据路径；锁文件仍是 `DATA_ROOT/.writer.lock`。规则 9：`open_write_layout` 仍先 `validate_for_write()` 再建目录；扫描现在也拦住了直接构造 `DataLayout(...)`/`ScopedWriter(...)` 这种跳过写前检查的写法。规则 10：没有新增可调参数或散落的数字。规则 11：`src/config/` 本轮只改了 `README.md` 和 `README_FOR_DEVELOPER.md`，两份同步，没有改配置代码。

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R6-1 | must-fix | `src/data_io/layout.py:224-236`（`_wait_for_lock` 的 `finally` 和最后两行） | **复用帮手后，先放弃的线程可能误以为自己拿到了锁。** `finally` 在模块互斥锁里把没拿到锁的帮手放回空闲表（`:233`），然后**在互斥锁外面**读 `waiter.error`、`waiter.acquired`（`:234-236`）。帮手一放回表，别的线程就可以接手它；如果这时锁正好空出来，帮手把锁交给新线程并把 `acquired` 设为 `True`，旧线程随后读到 `True`，就返回“拿到了”，但它的 `held` 是空的——它手里根本没有锁。`_lock` 于是放行，两个线程同时进入“持锁”区。时间线：10:00:00.000 线程 A 等锁 1 秒到点，把帮手放回表；10:00:00.000（同一瞬间）线程 B 开始等锁，接手这个帮手；另一个进程刚好放锁，帮手拿到锁交给 B；A 接着读 `acquired`，读到 `True`，以为自己也拿到了；A、B 同时写文件或同时做半成品恢复（恢复会把“看起来被放弃”的 partial 挪到 `recovery/`，可能挪走对方正在写的文件）。实测：强制这个先后顺序 3/3 次重现（A 返回 `(True, [])`，B 返回 `(True, [5])`）；不改代码的压力测试在线程切换间隔调到 1 微秒时 30 秒内出现 29 次“两个线程同时在临界区”；默认切换间隔下 30 秒内没出现，所以很少见，但一旦发生就是锁失效、数据可能被弄乱，而且 README:58 专门描述了“同一程序里几个线程同时等锁”的情况，说明这是预期会出现的用法。同理，A 也可能抛出本该属于 B 的错误。现有测试没有覆盖这个顺序。 | 在 `finally` 的 `with _WAITERS_MUTEX:` 里就把结果定下来：拿到锁时记 `got = True`（并 `held.append`）；帮手已结束且带错误时，在同一个块里把 `waiter.error` 存进局部变量；帮手要放回表时，结果就是“没拿到、没有错误”。放回表之后不再读这个帮手的任何字段；或者直接用“`held` 有没有新加句柄”作为返回值。加一个确定性的测试：让线程 A 放回帮手后暂停，线程 B 接手并拿到锁，再让 A 继续，断言 A 返回 `False` 且 `held` 为空、B 拿到句柄（可以像我的 `race.py` 那样替换互斥锁对象，在 A 的最后一次释放后等一个 `Event`）。 |
| B1-R6-2 | suggestion | `src/data_io/layout.py:280-285`（`_lock` 的 `finally`）、`:156`/`:225`（`with _WAITERS_MUTEX`）、`:186-193`（文档字符串） | **被信号打断后继续运行的程序，可能留下一把一直被占的锁，或（3.9 上）卡死。** Python 的 Ctrl-C（`KeyboardInterrupt`）或会抛异常的信号处理函数可以在任意两条字节码之间生效。如果它恰好落在 `_lock` 的 `finally` 里“关句柄之前”，持锁的句柄就漏掉了，锁一直被占到程序退出；如果在 3.9 上落在 `with _WAITERS_MUTEX` 退出的空隙（CPython 3.9 已知的 `with` 退出不原子问题），模块互斥锁就永远不释放，之后本程序所有线程等锁都会永久卡住、无视等待秒数，fork 也会卡住（fork 钩子要先拿这把锁）。这类问题旧代码也有（HEAD 在同样的探测下 11 次中 1 次锁被占），本轮代码更容易碰到（3.9 上 17 次中 13 次被占、2 次卡死；3.13 上 12 次中 5 次被占，另有 5 次没有打印结果），因为释放路径更长、互斥锁是全进程共享的。本项目里确实有“打断后继续跑”的路径：`Run.__exit__` 收到 `KeyboardInterrupt` 后会调用 `finish("failed")`，它要通过 REGISTRY writer 写 `record.json`，需要再拿一次写锁。正常的 Ctrl-C 会让程序退出、系统收回所有锁，所以实际影响很小；文档字符串说剩下的空隙“都不会占着锁”，只对它点名的那一处成立。 | 可选：(1) 在 `_wait_for_lock` 里用 `_WAITERS_MUTEX.acquire(timeout=剩余秒数)` 代替无限等待，等不到就按超时报 `WriteBoundaryError`，至少不会无视等待秒数永久卡住；(2) 把 `_lock` 的 `finally` 缩短（只关一个句柄）；(3) 在 README/ADR-003 写一句“被信号处理函数打断后继续运行的程序，写锁可能一直被占到程序退出；Ctrl-C 后请让程序退出”，并把文档字符串的说法改得不那么绝对。完全消除需要在关键段屏蔽信号（`signal.pthread_sigmask`），复杂度较高，不建议本 PR 做。 |

### Owner questions
无。B1-R6-1 有明确的工程修法，不涉及负责人取舍；B1-R6-2 是可选改进。说明：多线程竞争和信号打断都只在 macOS 上实测；负责人条件 2（合并前在 Linux 上跑一次连续写测试）仍未满足，文档已按条件写明只在 macOS 验证过。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `changes requested`。B1-R5-1、B1-R5-2、B1-R5-3、B1-R5-4 已 resolved；新的 must-fix B1-R6-1（复用帮手后先放弃的线程可能误判自己拿到锁）未解决，B1 尚未收敛。lint、format、全量测试（466 passed）由 Reviewer 本轮在隔离的 worktree 中亲自运行通过；锁测试重复 30 次、负载下 18 次、3.13 下 10 次均通过。

### Analyst response（Analyst 第 7 步，2026-11-19，由 Orchestrator 按 Analyst 回复填写）
| ID | Action | Detail and checks |
| --- | --- | --- |
| B1-R6-1 | fixed | `layout.py`：每次等待带自己的句柄清单（`claim`）；帮手在内部小锁里把拿到的句柄直接放进当前认领者的清单，无人认领则立即关闭；`_wait_for_lock` 在内部小锁里定下结果，交回帮手后不再读它。新测试 `test_wait_that_hands_back_its_waiter_never_takes_the_lock_meant_for_the_next_wait`（在第 6 轮代码上 3/3 失败）。Reviewer 的 `race.py`（3.9、3.13 各 3 次）与 `stress.py`（切换间隔 `1e-6`、`0.005`，3.9、3.13 各 3×10 秒）同时持锁 0 次。 |
| B1-R6-2 | fixed（部分采纳） | 放锁改为先 `LOCK_UN` 再关闭（嵌套 `finally`），且只有拿锁的 pid 才 `LOCK_UN`；内部小锁改为 `RLock`（子进程中重建）；`Event.set` 移到锁外；线程未启动就被打断时关闭句柄。`acquire(timeout=...)` 实测更差，未采用。3 个新测试，均做了反向验证。随机 Ctrl-C 探测每版 10 次：新代码锁被占 0 次（3.9、3.13），第 6 轮代码 8 次 / 7 次，HEAD 0 次；新代码无卡死。剩余限制写进 README、ADR-003、CHANGELOG、`_lock` 说明。 |

Analyst 检查：ruff、format 通过；全量 470 passed（3.9，含 B2）；锁测试连跑 30 次、负载下 18 次通过；3.13 全量 468 passed、2 failed（已知 B1-R4-3），锁测试 10/10。改动文件：`src/data_io/layout.py`、`tests/test_writer_recovery.py`、`README.md`、`CHANGELOG.md`、ADR-003。只在 macOS 运行。

## Block B1 · Round 7 · 2026-11-19

**结论先说：** 第 6 轮的 must-fix B1-R6-1（复用帮手后，先放弃的线程误以为自己拿到锁）已经从结构上修好：拿到的锁只会交给“当时正在认领这个帮手的那次等待”，我用自己的竞争和压力探测都没再看到两个线程同时持锁（同一探测在第 6 轮代码上 10 秒内就出现 7–9 次）。B1-R6-2 的几处改动（先 `LOCK_UN` 再关闭、只有拿锁的进程才解锁、`RLock`、`Event.set` 移到锁外、未启动就关闭句柄）本身也都按说明工作。lint、format、全量测试（470 passed）都通过。**但我发现一个第 6 轮就已存在、上一轮我没发现的问题（B1-R7-1，must-fix）**：如果 Ctrl-C（或会抛异常的信号处理函数）恰好落在“启动后台帮手线程”这一步，代码会误以为线程没启动，于是去关闭一个后台线程正在使用的文件；在 macOS 上这一关会卡住，同时占着内部小锁，几个线程同时等锁时整个程序永久卡死，而且全机的写锁一直被占着。另外，锁相关代码已经从改动前的约 30 行长到约 230 行，远超负责人选 B 时被告知的“约 30–40 行”，我作为 non-blocking 问题提给负责人。本轮结果：`changes requested`。

先解释几个词：
- **后台帮手（线程）**：同一个程序里替调用者“排队等钥匙（写锁）”的帮手。程序里每个线程都可以有自己的帮手。
- **句柄**：程序打开一个文件时操作系统发的“号码牌”。号码牌关掉之后，这个号码可能马上发给下一个打开的文件。
- **内部小锁 `_WAITERS_MUTEX`**：程序内部的一把小锁，保证“帮手表”同一时间只被一个线程修改。
- **信号处理函数抛异常**：Ctrl-C 在 Python 里变成 `KeyboardInterrupt`；有些程序还会用定时信号（`signal.alarm`）给任务限时，到时抛 `TimeoutError` 之类的普通异常。这类异常可以在任意两条 Python 指令之间冒出来。

- Revision: `codex/pr2-run-ledger` @ `4cd778e` + `<scratchpad>/all.patch`（B1 + 已收敛的 B2）。按隔离要求在 `<scratchpad>/wt-b1r7`（`git worktree add --detach … HEAD` 后 `git apply all.patch`）审查；`git status --short` 显示 13 个修改文件、没有未跟踪文件；逐个 `cmp` 与主工作区一致。另建 `<scratchpad>/wt-r6`（HEAD + `all-round6.patch`），`diff -rq` 显示本轮只改了 `src/data_io/layout.py`、`tests/test_writer_recovery.py`、`README.md`、`CHANGELOG.md`、ADR-003，与 packet 一致。B2 内容不在本轮审查范围，只确认整体测试通过。
- Addresses: B1-R6-1（must-fix）、B1-R6-2（suggestion，Analyst 部分采纳）；同时按要求检查本轮改动是否带来新问题和复杂度。
- Checks run by Reviewer（worktree 中，macOS，CPython 3.9.6，除非另注）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v -p no:cacheprovider` → **470 passed** in 13.07s
  - 锁测试重复跑：`.venv/bin/python -m pytest tests/test_writer_recovery.py -q -p no:cacheprovider -k "waiter or zero_timeout or successful_wait or interrupt or back_to_back or open_write_layout or lock or fork or layout_bypass or reuse or bounded or hands_back or release"` 连续 30 次 → 30/30 通过（每次 51 passed, 39 deselected）。
  - 加负载（`<scratchpad>/probe-b1r7/load.sh`）：24 个 `yes > /dev/null` 占满 12 核，同时 6 个上面的 pytest 并行，共 3 轮 → 18/18 都是 51 passed（9.1–9.9 秒）；其中一次有 pytest 自己清理临时目录的 `PytestWarning`（并行运行互删目录），与项目代码无关。
  - **Python 3.13.18**（临时环境 `uv venv --python 3.13` + `uv pip install --offline pydantic python-dotenv pytest duckdb pyarrow`，结束后已删除）：全量 `python -m pytest tests/ -q -p no:cacheprovider` → 2 failed, 468 passed，失败的仍只是已知的 B1-R4-3；锁测试连跑 10 次 → 10/10 通过。
  - **B1-R6-1 竞争探测**：第 6 轮的 `probe-b1r6/race.py`（强制“A 交回帮手后暂停、B 接手并拿到锁、A 再继续”的顺序）3.9、3.13 各 3 次 → 每次 A 返回 `(False, [])`，B 返回 `(True, [句柄])`。
  - **B1-R6-1 压力探测**（新写的 `probe-b1r7/stress7.py`，不改任何代码：8 个线程用 0.5 毫秒超时反复等锁、迫使帮手不断交回和复用，另一个进程不停拿锁放锁，每次 10 秒；在“拿到”的区段里用内核核对：返回的句柄是否真的持有锁、另开一个句柄能否抢到锁、是否有两个线程同时在区段内）：3.9 下切换间隔 `1e-6` 和 `0.005` 各 3 次、3.13 下各 2 次 → 等待模式共约 18 万次“拿到”，**两个线程同时持锁 0 次、拿到却没有句柄 0 次、句柄不持锁 0 次、别人能抢到 0 次**，结束时锁空、帮手表和句柄表为空。用真实入口 `_lock(root, 1)` 跑（3.9 两次、3.13 一次）→ 同样 0 次。对照：同一探测在第 6 轮代码上 2 次各 10 秒 → 出现 7 次和 9 次“拿到却没有句柄、两线程同时持锁”，说明探测能抓到原问题。
  - **flock 语义与 fork 持锁**（`probe-b1r7/flocksem.py`，3.9 和 3.13 结果相同）：①同一进程另开一个句柄执行 `LOCK_UN`，原持有者的锁**仍在**；对持有者的 `dup` 副本执行 `LOCK_UN`，锁**被放掉**（这正是 fork 子进程那份副本的情况，所以 pid 检查是必要的）。②外层 `_lock` 持锁时，同线程嵌套 `_lock(root, 0)` 失败、嵌套 `_lock(root, 1)` 1.01 秒后失败、另一线程 `_lock(root, 1)` 失败，三次之后外层的锁都仍被持有；外层退出后锁空、无残留帮手。③持锁时 fork 出的子进程退出同一个 `with`，父进程的锁仍在；父进程退出后锁空。④持锁时 fork，然后用 `SIGKILL` 杀掉父进程：子进程活着期间锁仍被占，子进程退出后锁空，与 ADR-003 的描述一致。
  - **自己的改动测试（mutation）**（`probe-b1r7/mut7.py`，在单独的 `wt-mut` 中逐个改坏 `layout.py` 后跑锁测试）：“交回后再读帮手状态”（第 6 轮写法）、去掉 pid 检查、去掉 `LOCK_UN`、`RLock` 换回 `Lock`、无人认领时也把句柄交出去、交回时不清除认领、子进程不关继承的句柄、去掉“未启动就关闭”——8 种都有测试失败；只有“把 `Event.set` 挪回小锁里面”没有测试失败（见 B1-R7-3）。之后 `layout.py` 已恢复，`cmp` 与 `wt-b1r7` 一致。
  - **Analyst 修改后的中断探测是否漏掉情况**：`b1r7/intr6.py` 比我第 6 轮的 `intr5.py` 多了一个 `ARMED` 开关：信号处理函数只在 `ARMED` 为真时抛 `KeyboardInterrupt`，而 `ARMED` 只在 `setitimer(0)` 之后、也就是 `with _lock(...)` 已经完全退出之后才变假，下一次进入 `_lock` 之前又变真。所以它**不会**漏掉任何落在 `_lock` 内部的打断，只是丢掉“迟到”的信号。我确认了迟到信号确实存在：不带开关的 `intr5.py` 在本轮代码上 3.9 跑 10 次，有 3 次探测脚本自己在循环开头（`while time.time() < end:`，不在任何 `try` 里）收到 `KeyboardInterrupt` 而退出——这就是我第 6 轮记录的“没有打印结果”的原因，是探测脚本的问题，不是项目代码的问题。结论：这个修改合理。结果：`intr5.py` 3.9 上能跑完的 7 次锁都空；`intr6.py` 3.9 上 10/10、3.13 上 10/10 锁都空，没有卡死。
  - **多线程 + 随机中断探测**（新写的 `probe-b1r7/intr7mt2.py`/`intr7mt3.py`：主线程像 `intr6.py` 一样被随机打断，同时 3 个后台线程不停 `_lock(root, 1)`；用“主线程当前是否正停在持锁区段那一行”来判断主线程是否认为自己持锁，避免标记被打断后残留造成的误报）：3.13 共 30 次、3.9 共 55 次（每次 7 秒，约 1900 次打断）→ **两个线程同时持锁 0 次**；但有 5 次整个程序卡死被看门狗结束（3.13 两次，3.9 三次），栈全都一样，见 B1-R7-1；另有 1 次（3.9）主线程跑完但 3 个后台线程卡住、锁被占，当时没有抓到栈，原因未查明（可能是文档已写明的 3.9 小锁漏放问题，也可能是 B1-R7-1，未验证）。我最早一版多线程探测（`intr7mt.py`）报告过若干“重叠”，查明是探测里主线程的标记被打断后没清掉造成的误报，改进后的版本为 0。
  - **B1-R7-1 的确定性复现**（`probe-b1r7/startexc.py`、`startexc2.py`，3.9 和 3.13 都做）：见下方 B1-R7-1。
  - **硬规则 8–11 与文档对照**：见下方。
  - 结束后删除 `wt-b1r7`、`wt-r6`、`wt-mut` 三个 worktree 和 3.13 临时环境，`git worktree list` 只剩主工作区。探测脚本留在 `<scratchpad>/probe-b1r7/`，供 Analyst 复现 B1-R7-1。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R6-1 | resolved | 从结构上看：`layout.py:241` 认领者在小锁里设 `waiter.claim = held`；`:269` 交回时在小锁里设回 `None`；帮手线程在 `:161-171` 的同一把小锁里读 `claim` 并把句柄直接 `append` 进认领者的清单，没人认领就立即关闭；`_wait_for_lock` 在 `:257-270` 的小锁里根据 `waiter.done` 定下结果，之后只读局部变量 `obtained`/`error`，不再碰帮手。所以“句柄交给谁”和“谁在认领”是在同一把锁里决定的，交回之后旧的等待不可能再收到句柄。实测：`race.py` 6/6 次 A 返回 `(False, [])`；`stress7.py` 等待模式约 18 万次拿锁 0 次重叠（第 6 轮代码 10 秒内 7–9 次）；新测试 `test_wait_that_hands_back_its_waiter_never_takes_the_lock_meant_for_the_next_wait` 在“交回后再读帮手状态”的改法下失败。 |
| B1-R6-2（suggestion） | resolved（采纳部分的改动本身正确）；同一段代码里另有问题，见 B1-R7-1 | 先 `LOCK_UN` 再关闭（`:331-337`，嵌套 `finally`）：`test_release_still_frees_the_lock_when_interrupted_once` 通过，去掉 `LOCK_UN` 后失败。只有拿锁的进程解锁（`:317`、`:332`）：flock 按“打开的文件”计（不是按号码牌、也不是按进程），我的探测①证明另开的句柄 `LOCK_UN` 不会放掉别人的锁，而 fork 子进程那份是同一个“打开的文件”的副本，`LOCK_UN` 会放掉父进程的锁，所以 pid 检查是必要的；去掉检查后 `test_fork_while_holding_the_lock` 失败。pid 被重复使用：子进程是在父进程还活着时创建的，不可能和父进程同号；只有父进程死后再由子进程 fork 出的孙进程才可能拿到同号，这时它最多是提前放掉一把已经没有合法持有者的锁，可以忽略。`RLock`：代码里四处 `with _WAITERS_MUTEX`（`:161`、`:236`、`:248`、`:257`）都没有嵌套，锁内调用的 `_take_idle_waiter`、`_forget_idle`、`_LockWaiter.__init__`、`_open_lock_file` 也不再拿这把锁，所以正常运行时 `RLock` 与 `Lock` 行为相同，不会掩盖问题；只有“同一线程漏放之后再进来”时才不同，换回 `Lock` 后 `test_wait_interrupted_before_releasing_the_waiter_mutex_does_not_deadlock` 失败。子进程里重建小锁（`:276-284`）：fork 测试通过，fork 钩子用 `lambda` 在调用时取全局名，重建后不会引用旧锁。`Event.set` 移到锁外（`:173`）：结果只看 `waiter.done`（锁内设置），不依赖 `Event`，所以正确；但没有测试守住它（B1-R7-3）。未启动就关闭句柄（`:263-267`）：去掉后测试失败。文档：README:58、ADR-003:30、CHANGELOG:17、`_lock` 和 `_wait_for_lock` 文档字符串中“持锁时 fork 的子进程只共享到父进程写完为止”“父进程被杀时子进程那份仍占着锁”都与我的探测③④一致。 |
| P1-F2、P1-F3（负责人选 A、B） | 维持 resolved | 入口与“等通知”的做法没变；负责人条件 1 的测试在 30 次重复、18 次负载、3.13 下 10 次中全部通过。条件 2：仍没有在 Linux 上运行，文档照旧写明“只在 macOS 验证过”。 |
| B1-R4-3 | out-of-scope（未变） | 3.13.18 上仍是那 2 个 PR1 用例失败。 |
| B1-R5-1 ~ B1-R5-4、B1-R4-1、B1-R4-2、B1-R2-1、B1-R1-1 ~ B1-R1-7 | resolved（维持） | 相关代码未变或已在上面复核，测试在 470 个中通过。 |

**硬规则 8–11 核对：** 规则 8：本轮没有新增数据路径；锁文件仍是 `DATA_ROOT/.writer.lock`。规则 9：`open_write_layout` 没有变，仍先 `validate_for_write()` 再建目录。规则 10：没有新增可调参数或散落的数字。规则 11：本轮没有改 `src/config/` 的任何文件（`diff -rq` 确认），`src/config/README.md` 中关于等锁的描述仍然准确。

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R7-1 | must-fix | `src/data_io/layout.py:242-253`（`_wait_for_lock` 中 `waiter.thread.start()` 的 `except Exception:` 分支）；相关说法：该处注释、`_wait_for_lock` 文档字符串、README:58“After Ctrl-C, let the program exit; the operating system then releases the lock”、ADR-003:30 | **代码把“`start()` 抛了普通异常”当成“线程没有启动”，然后关闭后台线程正在使用的句柄。** 实测这个前提是错的：CPython 的 `Thread.start()` 是“先真正创建线程，再等它报到”；如果信号处理函数在“等报到”时抛异常，`start()` 会在线程**已经在跑**之后抛出——Ctrl-C 时有一部分会变成 `RuntimeError: release unlocked lock`（3.9 上被打断的 2550 次中 47 次，3.13 上 2485 次中 12 次，都是“线程已经跑起来了”）；如果程序用定时信号抛普通异常（例如 `TimeoutError`），1369 次中有 1117 次是“线程已经跑起来了”。这些都落进 `except Exception:`，代码在**持有内部小锁**的情况下 `os.close(waiter.fd)`，而后台线程正阻塞在同一个句柄的 `flock` 上。后果（都实测过）：(1) **macOS 上这次关闭会一直卡到 `flock` 返回**。只有一个线程在等时，被打断的这次等待会无视等待秒数，一直卡到别的进程放锁（等待秒数 1，实际卡了 2.51 秒，正好等于另一个进程持锁的时间）；几个线程同时等时会形成**永久死锁**：主线程拿着内部小锁卡在关闭上，它要等帮手 W1 的 `flock` 返回；W1 在等写锁；写锁已被另一个帮手 W2 拿到，W2 又在等主线程手里的内部小锁。整个程序卡死，而且全机的 `.writer.lock` 一直被占，其他任务全部等锁超时，直到有人手动杀掉这个进程。多线程随机中断探测 85 次中 5 次正是这个栈（主线程停在 `layout.py:252`），确定性复现在 3.9、3.13 上都是 8 秒看门狗超时。(2) **同一个号码牌被关两次**：卡住结束后，后台线程在 `:169` 又关一次同一个号码，实测得到 `OSError: [Errno 9] Bad file descriptor`；如果这期间号码已经发给了别的文件（例如账本 `ledger.sqlite3`），关掉的就是那个文件（这一点是推断，未实测）。`Run.__exit__` 收到 `KeyboardInterrupt` 后会继续写账本和 `record.json`，正好可能复用这个号码。时间线：10:00:00.000 线程 A 开始等锁，创建帮手并调用 `start()`；10:00:00.0003 用户按 Ctrl-C，异常在 `start()` 等报到时冒出、变成 `RuntimeError`；代码以为线程没启动，拿着内部小锁去关句柄，卡住；线程 B、C 的等待都卡在内部小锁上，其中一个帮手已经拿到写锁也交不出去；从此这个进程不再动，全机写入被挡住。文档说“Ctrl-C 后让程序退出、系统会放锁”，但这里程序自己退不出来。发生条件很窄（中断恰好落在启动线程的几百微秒里），但后果是死锁和关错文件，而且修法简单。这段代码是第 6 轮为 B1-R5-4 加的，我上一轮没有发现。 | 不要在“不确定线程是否已经启动”时由调用方关闭句柄。可选做法（由 Analyst 选，越简单越好）：(a) 让后台线程自己打开句柄（在 `_wait` 开头、拿小锁登记到 `_WAITER_HANDLES`），这样线程没启动就根本没有句柄，调用方永远不需要替它关；打开失败的错误照常交给认领者。(b) `start()` 抛异常时一律按“被打断”处理：清除认领、放回空闲表或标记放弃，句柄由线程（如果它确实在跑）自己关；真正“无法创建线程”时会留下一个不占锁的句柄，在文档里写明。无论哪种，关闭句柄都不要放在持有内部小锁的时候做可能阻塞的事。加一个确定性测试：替换 `Thread.start` 为“真正启动后再抛 `RuntimeError`”（像 `probe-b1r7/startexc.py` 第 2 部分），另一个线程或进程 0.3 秒后放锁，断言：调用方在等待秒数内收到异常、没有任何线程卡住、没有出现第二次关闭（例如帮手线程没有报 `EBADF`）、锁最终是空的。保留现有 `test_waiter_thread_that_cannot_start_closes_its_handle` 所覆盖的“真的没启动”场景（如果改成做法 b，相应调整断言）。同时把 `:247` 的注释和 README/ADR 的说法改准确。 |
| B1-R7-2 | owner-question（non-blocking） | `src/data_io/layout.py:97-338` | **复杂度大大超过负责人选 B 时的预期。** 负责人选 B 时，问题里写的代价是“约 30–40 行代码”。改动前（HEAD）`_lock` 约 29 行；现在等锁相关代码（帮手类、空闲帮手表、认领交接、fork 钩子、可重入小锁、打断处理）约 230 行（不含空行和注释约 180 行），锁相关测试现在有 51 个（用上面的 `-k` 选出，含以前轮次的）。最近三轮每一轮的修复都带出了新的并发问题（第 5 轮的复用 → B1-R6-1；第 5 轮的打断修复 → B1-R7-1）。这不是某一行写错，而是设计本身在变重，按 PROJECT §11“简单优先”“半夜好排查”，应该让负责人知道并决定。 | 见下方问题。 |
| B1-R7-3 | suggestion | `src/data_io/layout.py:172-173`；`tests/test_writer_recovery.py` | “把 `Event.set` 挪回内部小锁里面”这个改法没有任何测试失败（我的改动测试 I）。目前的正确性不依赖它，所以只是缺一道防回退的网。 | 可选：加一个小测试，例如让 `finished.set` 阻塞一会儿，断言这期间别的线程仍能进入内部小锁；或在注释里写明这是可选的防护，不需要测试。 |

### Owner questions

**问题（B1-R7-2，non-blocking）：等写锁的代码越来越复杂，要继续用现在的做法，还是简化？**

1. 背景：你在第 4 轮选了 B（“等通知”：后台帮手排队等钥匙，锁一放就叫醒），当时估计约 30–40 行代码；为了补上审查中发现的漏洞，现在这部分已经约 230 行。
2. 场景：第 5 轮发现“反复重试会越积越多帮手和打开的文件”，于是加了“复用帮手”；第 6 轮发现“复用帮手后两个线程可能同时以为自己拿到锁”，于是加了“认领交接”；第 6 轮还加了“被 Ctrl-C 打断时的收尾”，本轮又发现其中“线程启动时被打断”会让程序卡死。每补一次都修好了上一个问题，但新代码又带来新的极端情况。正常使用（不按 Ctrl-C、不在多线程里反复超时）时，现在的代码在我的所有探测里都正确。
3. 选项：
   - **A. 保留现在的做法，修好 B1-R7-1 后冻结。** 会发生什么：功能最全（重试不积累、fork 安全、多线程安全）。之后只修真正的错误，不再为“信号打断”之类的极端情况加代码，剩下的限制写在文档里。代价：约 230 行比较难懂的并发代码，以后排查问题需要读懂它。
   - **B. 去掉“复用帮手”，回到“每次等待一个帮手”。** 会发生什么：认领交接整套可以删掉，代码大约少三分之一，B1-R6-1 这类问题不会再出现。代价：同一个程序用很短的等待秒数反复重试时，每放弃一次就多一个帮手和一个打开的文件，直到锁空出来；要在文档里写“不要短等待反复重试，改用一次较长的 `writer_lock_timeout_seconds`”。需要再走一到两轮审查。
   - **C. 退回改动前的轮询（每 50 毫秒看一次）。** 会发生什么：代码最简单（约 30 行）。代价：第 4 轮实测的问题回来——一个任务连续写文件时，另一个任务可能一直等到超时；这等于推翻你之前选 B 的决定。
4. 我的建议：**A**。理由：现在的代码在正常使用下已经通过了所有压力和竞争探测，B1-R7-1 的修法很小；再大改反而要重新经历几轮审查，风险更大；只要从此冻结、把剩余限制写清楚，复杂度不会继续增长。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `changes requested`。B1-R6-1 已 resolved（结构上和实测上都确认），B1-R6-2 采纳的改动本身正确；但新的 must-fix B1-R7-1（启动帮手线程时被打断会关错句柄，macOS 上可导致整个程序死锁并一直占着写锁）未解决，B1 尚未收敛。B1-R7-2 是 non-blocking 的负责人问题，在阶段汇报时问；B1-R7-3 是可选建议。lint、format、全量测试（470 passed）由 Reviewer 本轮在隔离的 worktree 中亲自运行通过；锁测试重复 30 次、负载下 18 次、3.13 下 10 次均通过。说明：所有探测只在 macOS 上运行；Linux 上 `close` 不会等 `flock` 返回，所以推断 B1-R7-1 在 Linux 上不会卡死，但“同一号码关两次”仍会发生（未实测）。负责人条件 2（合并前在 Linux 上跑一次连续写测试）仍未满足，文档已写明只在 macOS 验证过。

负责人确认（2026-11-19）：B1-R7-2 选 A，修好 B1-R7-1 后冻结等锁实现，之后只修真正的错误，剩余极端情况写进文档。

### Analyst response（Analyst 第 8 步，2026-11-19，由 Orchestrator 按 Analyst 回复填写）
| ID | Action | Detail and checks |
| --- | --- | --- |
| B1-R7-1 | fixed | `layout.py`：帮手线程自己在 `_WAITERS_MUTEX` 内打开并登记句柄，之后的 `flock`、交出、关闭都只由该线程完成；调用方不再打开或关闭帮手句柄；删去“未启动就关闭”分支；`start()` 未走到或抛异常时只清除认领、不放回空闲表。净改动 +34/−36。新测试 `test_start_that_raises_after_the_waiter_runs_neither_hangs_nor_closes_its_handle`（在第 7 轮代码上卡住失败）。Reviewer 的 `startexc.py`、`startexc2.py`（3.9、3.13）：约 0.05 秒收到异常，无卡死，无误关文件。 |
| B1-R7-3 | fixed（采纳 suggestion） | 新测试 `test_waiter_signals_the_caller_outside_the_mutex`；把 `Event.set` 挪回锁内时失败。 |
| B1-R7-2 冻结 | done | ADR-003 写锁一节新增“冻结（负责人，2026-11-19）”说明；CHANGELOG 加一句。 |

Analyst 检查：ruff、format 通过；全量 472 passed（3.9，含 B2）；锁测试连跑 30 次、负载下 18 次通过；3.13 全量 470 passed、2 failed（已知 B1-R4-3），锁测试 10/10；`stress7.py` 7 次重叠 0；多线程随机中断 3.9 40 次：卡死在关闭上 0 次，2 次为已写进文档的 3.9 `with` 退出漏放小锁；3.13 25 次全部正常。改动文件：`src/data_io/layout.py`、`tests/test_writer_recovery.py`、ADR-003、`CHANGELOG.md`。只在 macOS 运行。

## Block B1 · Round 8 · 2026-11-19

**结论先说：** 第 7 轮的 must-fix B1-R7-1 已经修好：现在后台帮手线程自己打开、自己关闭它的锁文件句柄，调用方再也不碰这个句柄，所以“启动线程时被打断”不会再让程序卡死，也不会把同一个号码关两次。我用第 7 轮的复现脚本重跑：0.05 秒就收到异常，期间新打开的文件没被误关；新测试在第 7 轮代码上失败、在本轮代码上通过。B1-R7-3 的测试也有效。lint、format、全量测试（472 passed）都通过，锁测试重复 30 次、加负载 18 次都通过。**但这次改动带来了一条新的出错路径——“帮手线程自己打开文件时就失败”——目前没有任何测试覆盖（B1-R8-1，should-fix）。** 现在的代码在这条路径上是对的（我实测过），但我故意改坏其中一行后，53 个锁测试全部仍然通过，而改坏后的程序会在别的进程占着锁时**以为自己拿到了锁，直接开始写**——也就是两个任务同时写。只需要补一个测试，不用改代码。另外两条是可选建议。本轮是 B1 的第 8 轮，已经到轮数上限，需要负责人决定是否再给一轮（见下方问题）。本轮结果：`changes requested`。

先解释几个词：
- **后台帮手（线程）**：替调用者“排队等钥匙（写锁）”的帮手。
- **句柄**：程序打开文件时操作系统发的“号码牌”。号码牌关掉后，这个号码可能马上发给下一个打开的文件。
- **改坏测试（mutation）**：故意把代码改坏一行，看测试能不能发现。如果改坏了测试还全部通过，说明这一行没有测试守着，以后有人不小心改错也不会被发现。

- Revision: `codex/pr2-run-ledger` @ `4cd778e` + `<scratchpad>/all.patch`（B1 + 已收敛的 B2）。在自己的 worktree `<scratchpad>/wt-b1r8`（`git worktree add --detach … HEAD` 后 `git apply all.patch`）审查；`git status --short` 显示 13 个修改文件、没有未跟踪文件；逐个 `cmp` 与主工作区一致（主工作区另有 `AGENTS.md`、`docs/pr2/PLAN.md`、`docs/pr2/REVIEW_LOG.md` 的流程文档改动，不属于本次修订）。另建 `<scratchpad>/wt-r7`（HEAD + `all-round7.patch`），`diff -rq` 显示本轮只改了 `src/data_io/layout.py`、`tests/test_writer_recovery.py`、ADR-003、`CHANGELOG.md`，与 packet 一致。B2 不在本轮审查范围，只确认整体测试通过。
- Addresses: B1-R7-1（must-fix）、B1-R7-3（suggestion）、B1-R7-2 负责人决定（选 A，冻结）的文档落实。
- Checks run by Reviewer（worktree 中，macOS，CPython 3.9.6，除非另注）：
  - `uv run ruff check .` → All checks passed!
  - `uv run ruff format --check .` → 30 files already formatted
  - `uv run pytest tests/ -v -p no:cacheprovider` → **472 passed** in 13.42s
  - 锁测试重复：`.venv/bin/python -m pytest tests/test_writer_recovery.py -q -p no:cacheprovider -k "waiter or zero_timeout or successful_wait or interrupt or back_to_back or open_write_layout or lock or fork or layout_bypass or reuse or bounded or hands_back or release or start or signals"` 连续 30 次 → 30/30 通过（每次 53 passed, 39 deselected）。
  - 加负载（`<scratchpad>/probe-b1r8/load.sh`）：24 个 `yes > /dev/null` 占满 12 核，同时 6 个上面的 pytest 并行，共 3 轮 → 18/18 都是 53 passed（9.97–10.56 秒）；其中一次有 pytest 自己清理临时目录的 `PytestWarning`（并行运行互删目录，与项目代码无关，第 7 轮也出现过）。
  - **Python 3.13.18**（临时环境 `uv venv --python 3.13` + `uv pip install --offline pydantic python-dotenv pytest duckdb pyarrow`，结束后已删除）：全量 `python -m pytest tests/ -q -p no:cacheprovider` → 2 failed, 470 passed，失败的仍只是已知的 B1-R4-3（`test_excessively_nested_source_json_retains_evidence`）；锁测试连跑 10 次 → 10/10 通过。
  - **新测试能否抓住原问题**：把本轮的测试文件放进 `wt-r7`（第 7 轮代码）运行 `-k "start_that_raises or signals_the_caller"` → `test_start_that_raises_after_the_waiter_runs_neither_hangs_nor_closes_its_handle` 失败（“the wait blocked closing the running waiter's handle”），`test_waiter_signals_the_caller_outside_the_mutex` 通过（第 7 轮代码本来就在锁外 `set`，符合预期）。之后已恢复 `wt-r7` 的测试文件。
  - **B1-R7-1 复现脚本**（`<scratchpad>/probe-b1r7/startexc.py 2`、`startexc2.py 2`，在本轮代码上）：两次都是约 0.05–0.06 秒收到 `RuntimeError`，帮手线程仍在、`_WAITER_HANDLES` 里是它自己的号码、空闲表为空；随后新打开的“受害者”文件拿到下一个号码，放锁后该文件**仍然打开**（第 7 轮代码在这里卡住或误关）。
  - **改坏测试**（`<scratchpad>/probe-b1r8/mut8.py`，在单独的 `wt-mut8` 中逐个改坏 `layout.py` 后跑上面的锁测试，结束后 `cmp` 确认已恢复）：
    - M3“`start()` 失败后仍放回空闲表”、M4“在 `start()` 之前就标记已启动”→ 各 10 个测试失败；M5“永不复用”→ 4 个失败；M6“`Event.set` 挪回小锁里”→ 1 个失败（新测试）；M7“打开后不登记句柄”→ 5 个失败。
    - **M1“去掉 `if fd is not None:` 判断”→ 53 个全部通过**；**M8“`except Exception` 改成 `except OSError`”→ 53 个全部通过**；**M2“打开和登记不放在小锁里”→ 53 个全部通过**。见 B1-R8-1、B1-R8-2。
  - **帮手线程打开失败**（新写的 `<scratchpad>/probe-b1r8/openfail.py`：另一个进程一直占着锁，只让帮手线程里的打开失败）：本轮代码上，A“打开报 `EMFILE`（文件开太多）”→ 0.00 秒收到 `OSError: [Errno 24]`；B“不是普通文件”→ 0.00 秒收到 `WriteBoundaryError`；D“真实地把 `.writer.lock` 换成目录”→ 0.00 秒收到 `IsADirectoryError`；三种情况结束后帮手线程 0、`_WAITER_HANDLES` 空、空闲表空、指向锁文件的句柄 0。C“打开慢 0.3 秒后失败、等待时间 0.05 秒”→ 0.31 秒后收到那个 `OSError`（见下方“观察”）。**同一脚本在 M1 上：A、B、D 都是约 1.01 秒后“拿到锁”进入了持锁区段，而锁其实一直被另一个进程占着**；在 M8 上：B 变成 1 秒超时，并在空闲表里留下一个已经死掉的帮手。
  - **fork 恰好发生在“帮手线程启动后、句柄登记前”**（新写的 `<scratchpad>/probe-b1r8/forkopen.py`：另一个进程一直占锁；3 个线程不停新建帮手（只在探测里关掉复用，强迫每次都新开线程和句柄），主线程同时不停 fork，每个子进程数自己手里指向锁文件的句柄）：本轮代码 2 次 → 各 987 次 fork，**子进程持有锁文件句柄 0 次**；结束放锁后帮手 0、句柄 0、锁空。对照 M2（打开和登记不在小锁里）2 次 → 928 次中 70 次、931 次中 66 次子进程带着帮手的句柄。说明 fork 钩子在新做法下仍然有效，而且是靠“打开+登记都在小锁里”这一点。（这个探测因为关掉了复用，最后开到了 4091 个线程、碰到系统线程上限，`start()` 报 `can't start new thread`；这正好又验证了“线程真的没启动”这条路径：结束时帮手 0、句柄 0、锁空。）
  - **正常使用有没有泄漏**（新写的 `<scratchpad>/probe-b1r8/leak.py`：另一个进程不停拿锁放锁，2 个线程反复 `_lock(root, 1)`，2 个线程用 0.3 毫秒超时反复放弃和复用，每次 8 秒）2 次 → 成功 5860/2537 次、放弃 26600/10034 次，帮手最多同时 4 个（= 同时在等的次数），结束后打开的文件数 5→5、线程数 1→1、`_WAITER_HANDLES` 和空闲表为空。
  - **两个线程同时持锁**（第 7 轮的 `<scratchpad>/probe-b1r7/stress7.py 10 <间隔> 8 <模式>`）：等待模式 3 次、真实入口 `_lock` 模式 2 次 → 共约 6 万次“拿到”，重叠 0、拿到却没有句柄 0、句柄不持锁 0、别人能抢到 0；结束时锁空、帮手和句柄表为空。
  - **多线程 + 随机 Ctrl-C**（第 7 轮的 `intr7mt3.py`，复制到 `<scratchpad>/probe-b1r8/mt/`，用 `probe-b1r7/drv3.sh` 驱动，每次 7 秒、约 1800 次打断）：3.9 共 25 次、3.13 共 10 次 → **两个线程同时持锁 0 次，没有一次卡在关闭句柄上（第 7 轮的 B1-R7-1 栈不再出现）**。34/35 次结束时锁空。1 次（3.9，seed 13）：主线程在 `_wait_for_lock` 收尾的 `with` 结束处被打断（`layout.py:265`），之后小锁一直被占：同进程 3 个后台线程卡在 `:256` 等小锁，几个帮手卡在 `:161`/`:167` 等小锁，其中一个已拿到写锁交不出去，于是这个进程一直占着写锁。这正是 ADR-003 和 README 已写明的“Python 3.9 上 Ctrl-C 后继续运行，内部小锁可能一直被占，同进程其他线程的等锁会卡住，锁被占到进程退出”。每次结束时本进程还留着 3–18 个指向锁文件、但不占锁的句柄（文档已写明“可能留下一个打开的锁文件句柄（不占锁）”）。另加诊断版 `intr8diag.py`（3.9 共 8 次）：结束时小锁都是空的；个别“剩 1 个帮手线程”的情况，该线程没有任何正在运行的 Python 栈，且同一次运行里都出现了 `start()` 被打断后抛出的 `RuntimeError: release unlocked lock`，是 CPython 对“启动被打断的线程”的记账残留，不占句柄也不占锁。
  - 结束后删除 `wt-b1r8`、`wt-r7`、`wt-mut8` 三个 worktree 和 3.13 临时环境，`git worktree list` 只剩主工作区。新探测脚本留在 `<scratchpad>/probe-b1r8/`。

### Previous findings
| ID | Status | Evidence |
| --- | --- | --- |
| B1-R7-1 | resolved | 结构上：`layout.py:157-180` 帮手线程在 `_wait` 开头、在小锁里自己 `_open_lock_file` 并登记到 `_WAITER_HANDLES`（`:161-163`），之后 `flock`、交出、关闭都只在这个线程里（`:171-176`）；`_wait_for_lock`（`:250-268`）里调用方不再打开或关闭任何帮手句柄，原来“`start()` 抛异常就关句柄”的分支已删除；`start()` 没走到或抛异常时（`started` 为假）只清除认领、不放回空闲表（`:263-265`），线程如果其实在跑，拿到锁后会因为没人认领而自己关句柄放锁。小锁里不再做会被别人的 `flock` 卡住的 `close`。实测：新测试在第 7 轮代码上失败、本轮通过；`startexc.py`/`startexc2.py` 约 0.05 秒返回，受害者文件没被关；随机 Ctrl-C 35 次没有出现第 7 轮那种卡死栈；M3、M4 两种改坏都有 10 个测试失败。`:247` 那句旧注释已不存在；README:58“Ctrl-C 后让程序退出，系统会放锁”现在对这种情况成立。 |
| B1-R7-3（suggestion） | resolved | 新测试 `test_waiter_signals_the_caller_outside_the_mutex` 在 `set` 时从另一个线程试拿小锁；M6（挪回锁内）时它失败，其他时候通过。 |
| B1-R7-2（owner-question） | 已由负责人决定（选 A，冻结），文档已落实 | PLAN §4b 有 2026-11-19 的决定记录；ADR-003 写锁一节末尾新增“冻结（负责人，2026-11-19，B1-R7-2）”；CHANGELOG 加了 B1-R7-1 的说明。本轮代码净改动很小（删掉了“未启动就关闭”分支和 `start_failed` 标记，没有新机制），符合冻结。 |
| P1-F2、P1-F3（负责人选 A、B） | 维持 resolved | 入口与“等通知”做法没变；负责人条件 1 的测试在 30 次重复、18 次负载、3.13 下 10 次中全部通过。条件 2：仍没有在 Linux 上运行，文档照旧写明“只在 macOS 验证过”。 |
| B1-R4-3 | out-of-scope（未变） | 3.13.18 上仍是那 2 个 PR1 用例失败。 |
| B1-R6-1、B1-R6-2 及更早的 B1 findings | resolved（维持） | 相关结构未变；`stress7.py` 重叠 0；对应测试在 472 个中通过。 |

**按负责人冻结决定对剩余极端情况的分类：** 负责人的标准是：已写进文档的极端打断情况可以接受，除非它会损坏数据、让两个任务同时写、或让一个**没被打断**的进程卡住。本轮实测到的剩余情况：(1) 被打断后留下不占锁的句柄（每次运行 3–18 个）；(2) 3.9 上被打断的进程自己卡住、一直占着写锁到退出（35 次中 1 次）；(3) 启动被打断后留下一个不复用的帮手线程，拿到锁后自己放掉。三者都只发生在“程序捕获 Ctrl-C 后继续运行”的那个进程里，ADR-003 和 README:58 都已写明；别的进程只会等到超时后报 `WriteBoundaryError`，不会卡住；所有探测里两个线程同时持锁都是 0 次，没有写坏数据。所以都归为**可以接受，不需要再改**。

**文档对照：** README:58、`src/config/README.md:29`、`src/config/README_FOR_DEVELOPER.md:29` 本轮没改，内容仍与代码一致（“放弃后后台线程和它打开的文件一直等到锁空，拿到立即释放；复用；fork 子进程关闭继承的文件；Ctrl-C 后可能留下不占锁的句柄”）。ADR-003 新写的“锁文件句柄由该线程自己打开、自己关闭，调用方从不替它关闭”和“`Thread.start()` 可能在线程已经运行之后才抛异常……只是不再复用这个线程”与代码和我的实测一致。CHANGELOG 新句“an exception raised while it is being started cannot block the caller or close that handle twice”与实测一致。`_wait_for_lock` 文档字符串去掉了“可能留下一个打开的句柄”，正确：现在这个函数本身不再打开句柄，留下句柄只可能发生在 `_lock` 自己的第一次打开（`:316`、`:324`），`_lock` 的文档和 README 仍有说明。

**硬规则 8–11 核对：** 规则 8：没有新增数据路径，锁文件仍是 `DATA_ROOT/.writer.lock`。规则 9：`open_write_layout` 未变。规则 10：没有新增可调参数或散落的数字。规则 11：本轮没有改 `src/config/` 的任何文件（`diff -rq` 确认）。另外规则 2（不悄悄丢掉错误）：帮手线程打开失败时，有人在等就把错误交给等的人抛出（实测 A、B、D），没人等就走原来的 `writer.lock_wait_error` 警告日志。

**观察（不作为 finding）：** 帮手线程在小锁里打开文件（`:161-163`），所以如果磁盘很慢、打开要很久，调用方的等待会多出这段时间，同进程其他线程的等锁和 fork 也会等这段时间（实测 C：模拟打开要 0.3 秒，等待时间 0.05 秒的调用 0.31 秒后才返回）。第 7 轮代码同样是在小锁里打开（在调用方线程里），而 `_lock` 自己的第一次打开也不受等待时间限制，所以这不是本轮新增的问题；正常本地文件打开只需几微秒。

### New findings
| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B1-R8-1 | should-fix | `src/data_io/layout.py:160-178`（`_wait` 里 `except Exception` 和 `if fd is not None:`）；`tests/test_writer_recovery.py`（缺测试） | **本轮新出现的“帮手线程自己打开文件就失败”这条路径没有测试守着，其中一行改错就会让两个任务同时写，而现有测试发现不了。** 以前打开是在调用方线程里做的，失败会直接抛给调用方；本轮把打开挪进帮手线程，失败要靠 `except Exception` 接住、靠 `if fd is not None:` 跳过关闭、再把错误交给调用方。现在的代码是对的（实测 A/B/D 都立即收到正确的错误，什么都不留下）。但改坏测试显示：M1 去掉 `if fd is not None:` 这一行，53 个锁测试全部通过，而实际行为是：`os.close(None)` 在帮手线程里报 `TypeError`，线程在交出错误之前就死了，但已经标记了“完成”；调用方等满 1 秒后看到“完成且没有错误”，就当作拿到了锁。时间线：10:00:00 任务 B 正在写、占着锁；10:00:00 任务 A 要写，帮手线程打开文件失败（例如进程打开的文件太多，`EMFILE`）；10:00:01 任务 A 以为拿到锁，开始写——**这时 A 和 B 同时在写**。M8（只接 `OSError`）也没有测试失败：锁文件不是普通文件时，调用方等满超时才报“被别人占着”，错误原因被换掉，还在空闲表里留下一个死掉的帮手。这不是现在的错误，而是本轮新路径缺一道防回退的网；按负责人的冻结决定，补测试不是新机制。 | 只加测试，不改代码。例如：用 `monkeypatch` 让 `_open_lock_file` 只在线程名为 `writer-lock-waiter` 时抛错（一次 `OSError(errno.EMFILE, …)`，一次 `WriteBoundaryError`），另一个进程（或 `_hold_lock`）占着锁，用 `lock_timeout_seconds=1` 的 writer 写文件，断言：很快（远小于 1 秒）收到对应错误（经 writer 后是 `WriteBoundaryError`，信息里含原因）、没有写出任何文件、`_assert_no_waiter_state()`、锁仍被原持有者占着。在 M1、M8 上它应当失败（可以用 `<scratchpad>/probe-b1r8/openfail.py` 的做法对照）。 |
| B1-R8-2 | suggestion | `src/data_io/layout.py:161-163`；`tests/test_writer_recovery.py` | “打开+登记都在小锁里”保证 fork 恰好发生在“帮手启动后、登记前”时，子进程也不会带走帮手的句柄（实测本轮 0/987，改坏后 66–70/930）。现有 fork 测试只覆盖“登记之后才 fork”，所以 M2（把打开挪出小锁）没有测试失败。后果是 B1-R5-3 的老问题回来：子进程替父进程一直占着锁，其他任务等到超时。发生窗口很窄，不会写坏数据，所以只是建议。 | 可选：加一个确定性测试，让帮手线程里的 `_open_lock_file` 打开后通知主线程并停 0.2 秒，主线程这时 fork；子进程数自己手里指向锁文件的句柄，断言为 0（在 M2 上会是 1）。 |
| B1-R8-3 | suggestion | `src/data_io/layout.py:203`、`:120-121` | 两处注释略不准确：`_take_idle_waiter` 里“A thread that never started cannot deliver the lock; drop it.”——本轮之后，没启动成功的帮手根本不会进空闲表，这个 `is_alive()` 检查现在只是防御（例如线程意外死掉）；小锁说明里“Its critical sections only do non-blocking work”——帮手线程在小锁里打开文件，是一次很短但会碰磁盘的系统调用（见上面“观察”）。 | 可选：改成“防御：丢掉已经不在运行的帮手”和“只做很短的操作（包括打开锁文件）”。 |

### Owner questions

**问题（B1 轮数上限，blocking）：B1 已到第 8 轮上限，还剩一个“只需补测试”的问题，要不要再给一轮？**

1. 背景：每块最多审查 8 轮，到了上限要由你决定是否继续。B1 这一轮把第 7 轮的卡死问题修好了，现在代码在我所有的实测里都是对的；只剩一条：本轮新加的一条出错路径没有自动测试守着。
2. 场景：现在的代码遇到“帮手打开锁文件失败”（例如程序同时打开的文件太多）时，会立刻报错、什么都不写，这是对的。但如果以后有人改代码时不小心删掉其中一行判断，现有的 53 个锁测试仍然全部通过，而程序会在别的任务占着锁时以为自己拿到了锁、开始写——两个任务同时写。我实测过这个“改坏一行”的情况。
3. 选项：
   - **A. 再给一轮，只补测试。** 会发生什么：Analyst 加一个约 20–30 行的测试（不改功能代码），下一轮 Reviewer 确认后 B1 收敛。代价：多一轮审查（主要是跑一遍检查）。
   - **B. 现在就按收敛处理，把补测试记为后续要求。** 会发生什么：B1 马上可以提交；测试留到以后的 PR。代价：在补上之前，这一行没有防护，改错了不会被发现。
4. 我的建议：**A**。理由：只加测试、不改代码，不违背冻结决定；它守的是“两个任务同时写”这种最严重的后果，成本很小。

### Analyst response
| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `changes requested`。B1-R7-1 已 resolved（结构上和实测上都确认，新测试能抓住原问题），B1-R7-3 已 resolved，B1-R7-2 的冻结决定已写进 ADR-003；剩余的打断极端情况按冻结标准归为可接受（已写进文档，不会写坏数据、不会让两个任务同时写、不会卡住没被打断的进程）。新的 should-fix B1-R8-1（帮手线程打开失败这条新路径缺测试，改坏一行会导致两个任务同时写而测试发现不了）未解决，只需补测试、不需改代码。B1-R8-2、B1-R8-3 是可选建议。lint、format、全量测试（472 passed）由 Reviewer 本轮在隔离的 worktree 中亲自运行通过；锁测试重复 30 次、负载下 18 次、3.13 下 10 次均通过。本轮是 B1 第 8 轮（上限），是否继续由负责人决定（上方 blocking 问题）。说明：所有探测只在 macOS 上运行；负责人条件 2（合并前在 Linux 上跑一次连续写测试）仍未满足，文档已写明只在 macOS 验证过。

负责人确认（2026-11-19）：B1 再给一轮（第 9 轮），只补测试，不改功能代码。
