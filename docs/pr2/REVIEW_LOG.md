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
