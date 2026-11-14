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
