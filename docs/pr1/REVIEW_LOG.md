# PR1 修复审查记录

## Block B1 · 配置错误处理 · Round 1 · 2026-11-13

- 目标：修复 [代码阅读进度](CODE_READING_PROGRESS.md)“本轮独立 Validator 发现”第 4 项：默认 `.env` 不可读时报告错误；项目配置模型公开校验入口及项目内嵌套模型的错误输出不泄露输入。普通第三方模型外层包装不在该保证内。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本块审查范围为 `src/config/loader.py`、`src/config/validation.py`、`src/config/models/pipeline.py`、两份 config README 和 `tests/test_config.py`。工作区还有其他 PR1 的既有改动，不能将本块结论推广到这些改动。
- 既有未跟踪文件：`docs/adr/ADR-002-pr1-foundation.md`、`docs/pr1/SCHEMA_REVIEW.md`、`scripts/generate_schema_docs.py`、`src/config/validation.py`、`src/logging_config.py`、`tests/test_adapter_contract.py`、`tests/test_cli_logging.py`、`tests/test_config.py`、`tests/test_data_schema.py`、`tests/test_writer_recovery.py`。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 有 2 个文件需格式化；`uv run pytest tests/test_config.py -q` 为 1 failed、39 passed；`uv run pytest tests/ -v` 为 1 failed、365 passed、5 warnings。

### Previous findings

无。

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B1-R1-1 | must-fix | `tests/test_config.py` | 根级输入类型错误没有 `quantity` 字段位置，测试错误要求该字段，导致失败且后续用例未执行。 | 按输入场景分别断言位置。 |
| B1-R1-2 | must-fix | `src/config/validation.py` | Pydantic 的 extra 字段位置来自输入，直接输出字段名可能在完整异常中暴露敏感文本。 | 隐藏未知字段名并测试构造和校验入口的完整 traceback。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B1-R1-1 | fixed | 按根级、嵌套及字段错误分别验证消息；定向测试 41 passed。 |
| B1-R1-2 | fixed | `extra_forbidden` 使用不含字段名的错误信息；增加构造、`model_validate`、`model_validate_json` 的完整 traceback 测试，同步两份 config README；定向测试 41 passed。 |

- Round result：`changes requested`。另外，对既有 `src/data_io/layout.py` 和 `tests/test_adapter_contract.py` 运行 Ruff 格式化以恢复全局格式检查；本轮不审查其行为。

## Block B1 · 配置错误处理 · Round 2 · 2026-11-13

- Revision：同一分支和未提交工作区；相对上轮，修改 `src/config/validation.py`、`tests/test_config.py` 和两份 config README；其他既有改动保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_config.py -q` 为 41 passed；`uv run pytest tests/ -v` 为 367 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B1-R1-1 | resolved | 根级、嵌套和字段错误的测试按场景断言；配置测试通过。 |
| B1-R1-2 | resolved | extra 字段名复现不再泄露；另见本轮字典键的新发现。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B1-R2-1 | must-fix | `src/config/validation.py` | 合法字典字段中，Pydantic 的错误位置可包含用户提供的字典键，完整 traceback 会暴露该键。 | 不输出不可信的位置组件，补充字典键测试。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B1-R2-1 | fixed | 只报告模型声明的顶层字段；构造、`model_validate` 和 `model_validate_json` 均新增字典键脱敏测试，更新两份配置 README，说明自定义校验器错误消息不得插入输入。定向测试 42 passed。 |

- Round result：`changes requested`。

## Block B1 · 配置错误处理 · Round 3 · 2026-11-13

- Revision：同一分支和未提交工作区；相对上轮，修改 `src/config/validation.py`、`tests/test_config.py` 和两份 config README；其他既有改动保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_config.py -q` 为 42 passed；`uv run pytest tests/ -v` 为 368 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B1-R1-1 | resolved | 分场景断言通过。 |
| B1-R1-2 | resolved | extra 字段名的原复现不再泄露。 |
| B1-R2-1 | resolved | 字典键的原复现不再泄露。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B1-R3-1 | must-fix | `src/config/validation.py` | Pydantic 内置 `union_tag_invalid` 错误的 `msg` 包含用户输入的 discriminator 值；构造、`model_validate`、`model_validate_json` 的异常和完整 traceback 均泄露该值。现有测试均通过但未覆盖此场景。 | 使用经过审查的安全错误消息或固定消息，不直接信任任意 Pydantic `msg`；覆盖内置错误及三个入口。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B1-R3-1 | deferred-to-owner | 第三轮出现阻塞性新发现，按工作流停止循环并向负责人报告；尚未修改或验证修复。建议用按错误类型匹配的固定安全消息，未知类型回退通用消息，并保留安全的顶层字段名；代价是部分错误细节更简略。 |

- Round result：`escalated`。本块未收敛；不能将本轮通过的检查解释为已解决此泄露。

### 负责人决定（2026-11-13）

负责人同意继续 B1：使用固定的安全错误消息，未列出的错误类型使用通用说明，同时保留安全的顶层字段名。进入新的审查循环，首先复核 B1-R3-1；前一循环的记录保持不变。

## Block B1 · 第二循环 Round 1 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上一循环，修改 `src/config/validation.py`、`tests/test_config.py` 和两份 config README；其他既有工作区变更保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_config.py tests/test_pipeline_foundation.py -q` 为 119 passed；`uv run pytest tests/ -v` 为 369 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B1-R3-1 | resolved | 使用固定错误消息；discriminator 和自定义校验器消息泄露的回归测试通过。 |
| B1-R1-2、B1-R2-1 | resolved | 未知字段名和字典键的原复现测试通过。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B1-L2-R1-1 | should-fix | `src/config/validation.py`、`tests/test_config.py` | 嵌套模型中，已脱敏的内部错误可能丢失外层字段；原测试在整个 traceback 中找字段，可能误匹配调用代码。 | 保留安全的外层字段；直接断言异常消息并测试同一子模型对应多个外层字段。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B1-L2-R1-1 | fixed | 嵌套包装错误显示已声明的外层字段及固定说明；顶层重新包装保留已脱敏信息。测试直接断言异常内容，分别验证两个外层字段以及构造和 `model_validate`；定向测试 123 passed。 |

- Round result：`changes requested`。

## Block B1 · 第二循环 Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上一轮修改 `src/config/validation.py` 和 `tests/test_config.py`；两份 config README 及其他既有工作区改动保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_config.py tests/test_pipeline_foundation.py -q` 为 123 passed；`uv run pytest tests/ -v` 为 373 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B1-L2-R1-1 | resolved | Reviewer 分别使用构造、`model_validate` 和 `model_validate_json` 验证两个外层字段，错误消息指向对应字段。 |
| B1-R3-1、B1-R1-2、B1-R2-1 | resolved | discriminator、未知字段名和字典键的脱敏回归测试通过。 |

### New findings

无。

### Analyst response

无新发现需要回复。

- Round result：`converged`。结论仅适用于 B1；不代表其他块已收敛或整个 PR 已通过 Validator。

## Block B2 · 写入层 · Round 1 · 2026-11-13

- 目标：核对并修复代码阅读进度中已确认的写入层持久性、恢复及 Validator 发现 1–3；既有方案为接收身份限制小写 ASCII、拒绝跨设备路径、校验恢复说明并保留证据。真实嵌套挂载与硬件断电未实测。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本块关注 `src/data_io/layout.py`、`src/config/models/pipeline.py`、`tests/test_writer_recovery.py`（未跟踪）、`tests/test_config.py`（未跟踪）、`tests/test_pipeline_foundation.py`、`README.md`、`docs/pr1/FOUNDATION_RULES.md`；其余既有 PR1 变更保留。首轮开始时写入层实现已在工作区，本次未另行声称实现了它们。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_writer_recovery.py tests/test_pipeline_foundation.py tests/test_config.py -k 'writer or layout or scoped or recovery or root or preflight or volume or write_check' -q` 为 67 passed、90 deselected；`uv run pytest tests/ -v` 为 373 passed、5 warnings。

### Previous findings

无本工作流之前的 B2 审查轮次；2026-11-11 Validator 发现作为本块输入，最终状态待本循环复核。

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B2-R1-1 | must-fix | `src/data_io/layout.py::_mkdir` | `mkdir` 成功后父目录同步失败，目录残留；重试时因目录已存在而跳过父目录同步，后续可能错误报告写入成功。临时目录故障注入复现。 | 验证目录后对新建和已存在目录均同步父目录，并测试失败重试和发布顺序。 |
| B2-R1-2 | should-fix | `src/data_io/layout.py::_validate_recovery_metadata` | 正常 partial 恢复说明的 `integrity` 可被改为 `valid`，且 `modified_at` 可丢失，初始化仍成功，与要求标记完整性未知并记录修改时间不符。 | 校验完整性和时间；孤儿说明保留未知来源规则，补故障测试。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B2-R1-1 | fixed | `_mkdir` 校验目录后无论是否新建均同步父目录；注入连续两次同步失败，确认不发布文件，随后确认发布前同步成功。 |
| B2-R1-2 | fixed | 正常 partial 说明要求 `integrity=unknown` 和有效带时区的 `modified_at`；重建孤儿说明要求完整性未知，不编造修改时间。缺失和错误字段的测试确认拒绝并保留证据。 |

- Round result：`changes requested`。

## Block B2 · 写入层 · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本轮修改 `src/data_io/layout.py`、`tests/test_writer_recovery.py`（未跟踪）、`README.md`，其余已有改动保留。`agent/REPORTER.md` 另按负责人要求记录汇报格式，与写入行为无关。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_writer_recovery.py tests/test_pipeline_foundation.py tests/test_config.py -k 'writer or layout or scoped or recovery or root or preflight or volume or write_check or directory_sync or partial_metadata' -q` 为 72 passed、90 deselected；`uv run pytest tests/ -v` 为 378 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B2-R1-1 | resolved | 故障注入确认连续同步失败时不发布；恢复后发布前同步父目录。 |
| B2-R1-2 | resolved | 四种 partial 说明损坏均拒绝并保留数据；普通 partial 和孤儿重建说明的不同规则保留。 |

### New findings

无。

### Analyst response

无新发现需要回复。

- Round result：`converged`。真实嵌套挂载、外接盘文件系统和硬件断电未实测；当前接收身份只接受小写 ASCII，跨设备路径被拒绝。本结论仅适用于 B2，不代表整个 PR 已通过 Validator。

## Block B3 · Adapter · Round 1 · 2026-11-13

- 目标：复核代码阅读进度中 Validator 发现 5、6 项及已确认的 adapter 契约，重点是 Bronze 外壳证据、溯源防篡改和来源 JSON 异常。非 venue 或无效字节的持久留证架构仍待负责人确认，不属于本块。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相关文件 `src/adapters/base.py`、`src/adapters/mock.py`、`src/data_schema/contracts.py`、`tests/test_adapter_contract.py`（未跟踪）、`tests/test_data_schema.py`（未跟踪）、`tests/test_pipeline_foundation.py`、`README.md`。首轮的对应修复已经存在，本次先核验；其余 PR1 变更保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_adapter_contract.py tests/test_pipeline_foundation.py tests/test_data_schema.py -k 'adapter or normaliz or bronze or json or contract' -q` 为 80 passed、85 deselected；`uv run pytest tests/ -v` 为 378 passed、5 warnings。

### Previous findings

先前 Validator 发现的外层只读 Mapping、溯源伪造和极端小数指数的原复现测试通过；本轮发现其他输入仍可绕过统一错误处理。

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B3-R1-1 | must-fix | `src/adapters/base.py` | 外壳字段中含只读 Mapping 时，校验前深拷贝抛 `TypeError`，没有 `NormalizationError` 和证据。成交与盘口入口均可复现。 | 安全复制嵌套只读映射并测试保留证据。 |
| B3-R1-2 | must-fix | `src/data_schema/contracts.py::_parse_json` | 来源 JSON 嵌套超过解析器深度时，`RecursionError` 绕过契约和统一规范化错误。 | 将该解析失败转换为 `ContractError`，测试两个 adapter 入口和原始内容。 |
| B3-R1-3 | must-fix | `src/data_schema/contracts.py::validate_record` | 外壳同时存在整数和字符串未知键时，排序直接抛 `TypeError`，缺少统一错误及证据。 | 明确拒绝非字符串字段名，测试两个入口。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B3-R1-1 | fixed | 复制证据时支持嵌套只读映射；测试成交、盘口及外壳两个字段，在原输入后续变化时证据仍保留。 |
| B3-R1-2 | fixed | JSON 解析的 `RecursionError` 转为 `ContractError` 并由 adapter 包装，测试两个入口的异常链和完整输入。 |
| B3-R1-3 | fixed | 行校验先拒绝非字符串字段名，测试两种入口保留整数和字符串未知字段证据。 |

- Round result：`changes requested`。

## Block B3 · Adapter · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上轮修改 `src/adapters/base.py`、`src/data_schema/contracts.py`、`tests/test_adapter_contract.py`（未跟踪）和 `README.md`，其余既有改动保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_adapter_contract.py tests/test_pipeline_foundation.py tests/test_data_schema.py -k 'adapter or normaliz or bronze or json or contract or readonly or envelope' -q` 为 88 passed、85 deselected；`uv run pytest tests/ -v` 为 386 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B3-R1-1 | resolved | 上轮嵌套只读映射的具体复现通过；另见本轮关于其他无法复制对象的发现。 |
| B3-R1-2 | resolved | 超深 JSON 被包装为契约和规范化错误，并保留原始 JSON。 |
| B3-R1-3 | resolved | 非字符串字段名被契约拒绝，异常中保留混合字段证据。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B3-R2-1 | must-fix | `src/adapters/base.py::_copy_raw_record` | 无效外壳字段中包含 `deque` 内的只读映射或超深嵌套列表时，复制仍分别抛 `TypeError` / `RecursionError`，不能通过 `NormalizationError` 获取证据。成交和盘口入口均复现。 | 明确无法创建独立证据副本时如何报告及保留原对象；不要声称任意 Python 对象都可复制。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B3-R2-1 | deferred-to-owner | 任意 Python 对象不一定允许复制，无法同时无条件保证独立副本和原始证据；证据复制失败时的接口与可变性需负责人决定。当前代码仍会抛原始异常，此项未修复。 |

- Round result：`escalated`。需要先确定不可复制证据的处理策略，再实施及复审；真实来源字节持久留证仍属于未决定的独立问题。

### 负责人决定（2026-11-13）

负责人同意：只针对当前出错的记录，能复制时交出独立副本；不能复制时通过统一错误交出原对象引用，并明确标记该证据不是独立副本、可能随原对象变化。异常携带证据不代表已保存到磁盘。进入 B3 新的审查循环。

## Block B3 · 第二循环 Round 1 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上轮修改 `src/adapters/base.py`、`tests/test_adapter_contract.py`（未跟踪）、`README.md`。`agent/REPORTER.md` 按负责人要求补充通俗汇报示例。其他既有更改保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_adapter_contract.py tests/test_pipeline_foundation.py tests/test_data_schema.py -k 'adapter or normaliz or bronze or json or contract or readonly or envelope or evidence' -q` 为 95 passed、85 deselected；`uv run pytest tests/ -v` 为 393 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B3-R2-1 | resolved | 先前无法复制的原复现均返回 `NormalizationError`、原对象引用及非快照标记。另见本轮对于复制行为不可信的新发现。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B3-L2-R1-1 | must-fix | `src/adapters/base.py::_copy_raw_record` | 可变对象的自定义复制方法可能返回它自身，表面复制成功但仍共享；异常错误标记为独立副本。 | 无法确认复制行为独立时保守降级为原引用，并补两个入口的测试。 |
| B3-L2-R1-2 | must-fix | `src/adapters/base.py::_copy_raw_record` | 字符串子类的自定义复制方法可改变 `run_id`，导致规范化结果使用伪造的 Bronze 溯源。 | 不信任自定义复制行为，确保不能静默改写溯源；测试成交和盘口路径。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B3-L2-R1-1 | fixed | 只将可验证复制行为的内置值和容器视为可创建独立快照；不可信类型按负责人确认方案返回原引用及非快照标记。补充可变对象返回自身的测试。 |
| B3-L2-R1-2 | fixed | 拒绝依赖自定义类型（含字符串子类）的复制行为，通过统一错误保留原对象，不继续规范化；补充可伪造 `run_id` 的测试。 |

- Round result：`changes requested`。

## Block B3 · 第二循环 Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上轮修改 `src/adapters/base.py`、`tests/test_adapter_contract.py`（未跟踪）、`README.md`；其他既有更改保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_adapter_contract.py tests/test_pipeline_foundation.py tests/test_data_schema.py -k 'adapter or normaliz or bronze or json or contract or readonly or envelope or evidence' -q` 为 97 passed、85 deselected；`uv run pytest tests/ -v` 为 395 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B3-L2-R1-1、B3-L2-R1-2 | resolved | 字段内可变对象和字符串子类的原复现按非快照处理；另见本轮顶层映射发现。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B3-L2-R2-1 | should-fix | `src/adapters/base.py` | 第二次复制失败时，非快照错误所携带的实际上是第一次副本，却称原对象引用。 | 重用已成功创建的独立副本并准确标记，或保留入口原对象；测试对象身份及后续变化。 |
| B3-L2-R2-2 | must-fix | `src/adapters/base.py::_copy_raw_record` | 顶层自定义 Mapping 在检查前由 `dict(raw)` 调用其访问方法，可能将 Bronze `run_id` 改为伪造值；代理包裹自定义 Mapping 时也可复现。 | 在访问前核实映射的可信边界，不可验证时按负责人决定保留原引用并标记。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B3-L2-R2-1 | fixed | 复用首次已确认独立的副本作为出错证据，不重复复制；测试确保仅复制一次，原记录变化不影响副本。 |
| B3-L2-R2-2 | fixed | 访问前只信任内置字典，以及可通过 `gc.get_referents` 确认为内置字典的只读代理；无法确认的映射按非快照原引用返回。增加顶层自定义映射及其代理的成交/盘口测试；对不可验证情况保守拒绝。 |

- Round result：`changes requested`。

## Block B3 · 第二循环 Round 3 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上轮修改 `src/adapters/base.py`、`tests/test_adapter_contract.py`（未跟踪）、`README.md`，其他既有更改保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_adapter_contract.py tests/test_pipeline_foundation.py tests/test_data_schema.py -k 'adapter or normaliz or bronze or json or contract or readonly or envelope or evidence or mapping or copy' -q` 为 101 passed、85 deselected；`uv run pytest tests/ -v` 为 399 passed、5 warnings。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B3-L2-R2-1 | resolved | 首次独立副本被复用；测试确认仅复制一次，原输入变化不改变副本。 |
| B3-L2-R2-2 | resolved | 顶层自定义映射及其只读代理在访问前拒绝，两个入口保留原引用并标非快照；嵌套代理同样检查。 |
| B3-R1-1、B3-R1-2、B3-R1-3、B3-R2-1、B3-L2-R1-1、B3-L2-R1-2 | resolved | 前述回归测试通过。 |

### New findings

无。

### Analyst response

无新发现需要回复。

- Round result：`converged`。无法确认底层为内置字典的只读代理及自定义映射保守拒绝；`gc.get_referents` 在其他 Python 实现中的行为未测。真实交易所、原始外壳持久化及隔离流程未验证。本结论仅适用于 B3，不代表整个 PR 已通过 Validator。

## Block B4 · 数据契约 · Round 1 · 2026-11-13

- 目标：复核已确认的数据契约执行规则和 Validator 发现 7、8，涵盖盘口覆盖、中间价、缺失值、字段说明、数值精度和 registry 自检；Bronze 非 venue、无效字节的持久留证仍是未决定的独立设计。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；主要文件 `src/data_schema/contracts.py`、`src/data_schema/schema_registry.json`、`docs/SCHEMAS.md`、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`scripts/generate_schema_docs.py`（未跟踪）、`tests/test_data_schema.py`（未跟踪）、`tests/test_pipeline_foundation.py`。首轮对应既有修复已在工作区，本次先核验；其他工作区改动保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_data_schema.py tests/test_pipeline_foundation.py -k 'schema or contract or training or gold or silver or bronze' -q` 为 70 passed、54 deselected；`uv run pytest tests/ -v` 为 399 passed、5 warnings。

### Previous findings

此前 Validator 对一分钟零/未知覆盖、一秒中间价、Silver 缺失事件时间、日成交字段可空的复现，以及 Decimal 上下文和 registry 自检测试通过。

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B4-R1-1 | must-fix | `gold.market_1s.rolling_volume` | 盘口存在但成交数据缺失时，滚动成交量必填，无法表达未知。 | 负责人选择保留盘口记录并将未知成交量留空。 |
| B4-R1-2 | must-fix | `book_levels`、`level_map` | JSON 盘口价格或数量可超过已确认的默认 `decimal128(28,10)` 精度。 | 精确检查且不舍入；Bronze 原始记录不受该限制。 |
| B4-R1-3 | must-fix | `gold.market_daily` | 日成交笔数为零时仍接受正成交份数。 | 当笔数为零时，份数只能为零或未知，不推断反方向。 |
| B4-R1-4 | must-fix | `gold.market_1s.microprice` | 缺少买价或卖价时仍接受需要两侧报价的微价格。 | 非空微价格要求两侧报价；不猜测第一档挂单数量。 |
| B4-R1-5 | must-fix | `gold.market_1s.imbalance` | 两侧深度均为零时仍接受不平衡度，与分母为零时应为空的定义冲突。 | 要求有值时两侧深度均存在，且不能同时为零；完整公式和舍入校验不在本次实现。 |

### Analyst response

| ID | Action | 处理及检查 |
| --- | --- | --- |
| B4-R1-1 | fixed | 负责人选择保留盘口记录、未知滚动成交量留空；字段改为可空，测试 Arrow 中为空且盘口仍保留。 |
| B4-R1-2 | fixed | 两种 JSON 档位规则检查价格、数量和金额的十进制精度，不改 Bronze；补充超小数位、超总位数及原始证据测试。 |
| B4-R1-3 | fixed | 声明通用条件规则：零笔成交时成交份数只允许零或 null；测试未知和有效情况。 |
| B4-R1-4 | fixed | 声明微价格依赖买卖两侧报价，分别测试缺失及可空情况。 |
| B4-R1-5 | fixed | 声明不平衡度依赖双侧深度且双侧零时必须为空；保留不验证完整计算公式的限制。 |

- 版本：按规则收紧和字段可空性变化将工作区未发布的 `3.0.0` 提升至 `4.0.0`；当前 HEAD 为 `2.0.0`，未实现迁移。
- Round result：`changes requested`。

## Block B4 · 数据契约 · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对上轮修改 `src/data_schema/contracts.py`、`src/data_schema/schema_registry.json`、`docs/SCHEMAS.md`、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`tests/test_data_schema.py`（未跟踪）、`README.md`、`CHANGELOG.md`；其他已有改动保留。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/test_data_schema.py tests/test_pipeline_foundation.py -k 'schema or contract or training or gold or silver or bronze or book_levels or one_second or daily' -q` 为 79 passed、54 deselected；`uv run pytest tests/ -v` 为 408 passed、5 warnings。额外实测 Decimal 精度为 2 且 Inexact/Rounded 陷阱开启时，合法盘口精度边界仍可通过。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B4-R1-1 | resolved | 一秒滚动成交量未知时可留空，Arrow 转换保留空值及盘口。 |
| B4-R1-2 | resolved | JSON 盘口数字超精度被拒绝；合法精度边界通过；Bronze 原始文本保持不变。 |
| B4-R1-3 | resolved | 零笔成交时正成交份数被拒绝；零和未知仍可表示。 |
| B4-R1-4 | resolved | 微价格有值时缺任一侧报价被拒绝。 |
| B4-R1-5 | resolved | 不平衡度有值时缺任一侧深度或两侧深度均为零被拒绝。 |

### New findings

无。

### Analyst response

无新发现需要回复。

- Round result：`converged`。未验证真实交易所数据、microprice / imbalance 的完整计算公式、跨行跨文件质量规则或旧契约版本迁移；`4.0.0` 尚未发布。此结论仅适用于本块，不代表整个 PR 已通过 Validator。


## Block B5 · Bronze 来源与原始内容 · Round 1 · 2026-11-13

- 目标：PLAN.md B5 行——非 venue / 无 API 版本可表示；有效 JSON 或原始字节能保存且不混淆；损坏字节保留证据；写入时间早于接收时间时不输出 Silver。依据 CODE_READING_PROGRESS.md 第 160–162 行负责人决定及 FOUNDATION_RULES.md §3。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本块文件 `src/data_schema/schema_registry.json`、`src/data_schema/contracts.py`、`src/adapters/base.py`、`tests/test_data_schema.py`（未跟踪）、`tests/test_adapter_contract.py`（未跟踪）、`tests/test_pipeline_foundation.py`、`docs/SCHEMAS.md`、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`docs/pr1/PLAN.md`、`README.md`、`CHANGELOG.md`。磁盘内容与修订包描述一致（registry `5.0.0`，`raw_bytes` 为 `binary?`，`exactly_one_present` 规则，`_payload` 顺序为外壳→时间→解码/解析→路由）。其他 PR1 工作区改动不在本块范围。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`git diff --check` 通过；`uv run pytest tests/test_data_schema.py tests/test_adapter_contract.py tests/test_pipeline_foundation.py -k 'bronze or raw or time_anomaly or routing or wrong_venue or normaliz or envelope or provenance or schema or registry' -q` 为 106 passed、101 deselected；`uv run pytest tests/ -v` 为 420 passed、5 warnings；用 `scripts/generate_schema_docs.py` 的 `regenerate()` 对比 `docs/SCHEMAS.md`，结果一致。另以临时脚本（`PYTHONPATH=. uv run python <scratchpad>/probe_b5.py`，不写仓库）调用 `MockVenueAdapter.normalize_trade` 复现下列行为。

### Previous findings

无（本块首轮）。

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| B5-R1-1 | should-fix | `src/adapters/base.py:285-303`（`VenueAdapter._payload`） | 路由检查放在时间异常、UTF-8 解码和 JSON 解析之后。实测：`venue="kalshi"` 或 `venue=None` 且 `raw_bytes=b"\xff"` 时得到 `NormalizationError(silver.trades, "'utf-8' codec can't decode ...")`；`venue="kalshi"`/`None` 且 `ingested_at < received_at`、或 `raw_payload="[]"` 时同样得到 `NormalizationError`，而不是 `AdapterRoutingError`。因此一条不属于本 adapter 的记录（例如非 venue 来源的 CSV 字节，本身合法）会被本 adapter 的 UTF-8/JSON 假设判为“损坏数据”，作为本数据集的来源异常进入未来 quarantine，掩盖了调度路由错误；修订包所述“空 venue 不匹配即为路由错误”只在 payload 恰好是合法 JSON 对象时成立。 | 外壳校验通过后先比较 `(venue, api_version, protocol_version)`，再检查时间异常，最后解码和严格解析。补充测试：错误或为空的 venue 分别与损坏字节、非 JSON 字节、时间异常组合时均抛 `AdapterRoutingError`。 |
| B5-R1-2 | should-fix | `tests/test_adapter_contract.py:553-560`（`test_adapter_rejects_wrong_venue_or_version`） | B5 新增可表示的 `venue=None`、`api_version=None`，但 adapter 层路由测试只覆盖非空错误值（`"kalshi"`、`"wrong"`）。临时实测两者目前都抛 `AdapterRoutingError`，但没有回归测试保护“空值不匹配即路由错误”这一本块声明的行为。 | 在该参数组中加入 `{"venue": None}`、`{"api_version": None}`（可与 B5-R1-1 的组合测试合并）。 |
| B5-R1-3 | should-fix | `docs/pr1/PLAN.md:32`；`docs/pr1/SCHEMA_REVIEW.md:56`；`docs/SCHEMAS.md:12`、`docs/pr1/SCHEMA_REVIEW.md:25`、`README.md:76` | 文档与 B5 后的实现不一致：(1) PLAN 第 4 块状态仍为“已实现 JSON 契约”，未反映原始字节表示；(2) SCHEMA_REVIEW“破坏性变更与版本”称由 `4.0.0` 升至 `5.0.0`，但列举的是 `max_feature_available_at` 改名、`gold.market_1m` 等更早变化，没有列出本次真正的破坏性原因（`raw_payload` 改可空、新增必填键 `raw_bytes` 使旧行因缺字段被拒、`venue`/`api_version` 可空、`exactly_one_present`）；(3) SCHEMAS.md 与 SCHEMA_REVIEW 写“mock adapter 拒绝将其规范化”，README 写 “this adapter”，但检查在 `VenueAdapter` 基类，对所有 adapter 生效。 | 更新 PLAN 第 4 块状态；在 SCHEMA_REVIEW 第 1 项分开说明 `4.0.0→5.0.0` 的 Bronze 变化与此前累计变化；把时间异常和原始字节解码的执行位置写为 `VenueAdapter` 规范化边界。 |
| B5-R1-4 | suggestion | `agent/PROJECT.md:115` | 权威文档 §6 “Raw record envelope” 字段列表仍只有 `raw_payload`，未包含 `raw_bytes`、`api_version`、`protocol_version`；第 117 行已允许非 venue 和原始文件，故不构成直接矛盾，但列表已不完整。按 FOUNDATION_RULES 说明，修改 PROJECT.md 需负责人确认。 | 经 Reporter 提交负责人：补全字段列表，或改为“字段见 `docs/SCHEMAS.md`”。 |
| B5-R1-5 | suggestion | `src/data_schema/contracts.py:467` | `binary` 类型用 `isinstance(value, bytes)`，接受 `bytes` 子类；契约通过后 adapter 的证据复制（`base.py:87` 按精确类型）会拒绝，结果为 `NormalizationError("Cannot copy Bronze evidence")` 且 `evidence_is_snapshot=False`。不丢数据，但契约与证据复制对同一字段的接受范围不一致。 | 考虑在契约层使用 `type(value) is bytes`，或在文档中说明子类走非快照路径。 |
| B5-R1-6 | out-of-scope | `src/adapters/base.py:197-204`（`AdapterMetadata`）、`_payload` 路由 | `AdapterMetadata` 要求非空 `api_version`，因此 `api_version=None` 的 venue Bronze 记录可以保存，但没有任何 adapter 能把它规范化为 Silver（总是路由错误）。B5 验收只要求“可表示”，不要求可规范化；历史归档等未知 API 版本来源如何路由需在对应来源设计时决定。 | 交 Reporter 记录为后续来源设计问题（例如 adapter 显式声明可接受未知 API 版本的条件）。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B5-R1-1 | fixed | `src/adapters/base.py` `_payload` 改为：外壳契约校验 → 路由比较 `(venue, api_version, protocol_version)` → 时间异常 → 解码与严格 JSON 解析。新增 `test_routing_is_checked_before_content_and_time`（错误/空 venue × 损坏字节、CSV 字节、非对象 JSON、时间异常 × 普通/盘口路径，16 例）均得到 `AdapterRoutingError`。 |
| B5-R1-2 | fixed | `test_adapter_rejects_wrong_venue_or_version` 增加 `{"venue": None}`、`{"api_version": None}`。 |
| B5-R1-3 | fixed | `docs/pr1/PLAN.md` 第 4 块状态补充 B5 原始字节与无交易所/API 版本表示；`SCHEMA_REVIEW.md` 版本说明分开列出本次 Bronze 破坏性变化与此前累计变化；`docs/SCHEMAS.md`、`SCHEMA_REVIEW.md`、`README.md` 改为由 `VenueAdapter` 基类规范化边界执行、对所有 adapter 生效。 |
| B5-R1-4 | deferred-to-owner | 修改 `agent/PROJECT.md` 须负责人确认，交 Reporter 提出。 |
| B5-R1-5 | fixed（采纳 suggestion） | `contracts.py` `binary` 改为 `type(value) is not bytes`，与证据复制的精确类型检查一致。 |
| B5-R1-6 | deferred（out-of-scope） | 无 API 版本记录的路由由后续来源设计决定，交 Reporter。 |

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 436 passed、5 warnings；`git diff --check` 通过。
- Round result：`changes requested`。已核实满足的部分：契约层 `venue`/`api_version` 可空、`source` 必填；`raw_payload` 与 `raw_bytes` 同时为空或同时有值被拒；`b""`、非 UTF-8、非 JSON、CSV 字节均可保存并经 Arrow 往返；`bytearray` 被拒；UTF-8 BOM、UTF-16 字节和损坏字节在规范化时抛 `NormalizationError` 并保留快照证据；`ingested_at < received_at` 在契约层被接受、在规范化边界阻止输出 Silver；`docs/SCHEMAS.md` 与 registry 生成结果一致。未验证真实来源、原始字节持久化、quarantine 流程和旧版本迁移。

## Block B5 · Bronze 来源与原始内容 · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对 Round 1 修改 `src/adapters/base.py`、`src/data_schema/contracts.py`、`tests/test_adapter_contract.py`（未跟踪）、`docs/pr1/PLAN.md`、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`docs/SCHEMAS.md`、`README.md`。磁盘内容与 Analyst response 一致。其他 PR1 工作区改动不在本块范围。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`git diff --check` 通过；`uv run pytest tests/test_data_schema.py tests/test_adapter_contract.py tests/test_pipeline_foundation.py -k 'bronze or raw or time_anomaly or routing or wrong_venue or normaliz or envelope or provenance or schema or registry' -q` 为 122 passed、101 deselected；`uv run pytest tests/ -v` 为 436 passed、5 warnings；`scripts/generate_schema_docs.py` 的 `regenerate()` 与 `docs/SCHEMAS.md` 一致。重跑 Round 1 的临时复现脚本（不写仓库）。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B5-R1-1 | resolved | `base.py` `_payload` 顺序为外壳校验 → 路由比较 → 时间异常 → 解码/严格解析。复现脚本中 `venue="kalshi"`/`None` 分别与 `b"\xff"`、时间异常、`"[]"` 组合均得到 `AdapterRoutingError`；正确路由的 BOM、UTF-16 字节仍得到带快照证据的 `NormalizationError`。`test_routing_is_checked_before_content_and_time` 覆盖 16 种组合（含 CSV 字节、盘口路径）。 |
| B5-R1-2 | resolved | `test_adapter_rejects_wrong_venue_or_version` 已包含 `{"venue": None}`、`{"api_version": None}`。 |
| B5-R1-3 | resolved | PLAN.md 第 4 块状态已反映原始字节和无交易所/API 版本表示；SCHEMA_REVIEW 第 1 项分列 B5 的 Bronze 破坏性变化与此前累计变化；SCHEMAS.md 第 12 行、SCHEMA_REVIEW 第 25 行、README 第 76 行均写明由 `VenueAdapter` 基类边界执行、对所有 adapter 生效。 |
| B5-R1-4 | deferred-to-owner | 不阻塞收敛，交 Reporter 向负责人提出 PROJECT.md 字段列表更新。 |
| B5-R1-5 | resolved | `contracts.py:467` 改为 `type(value) is not bytes`；复现脚本中 `bytes` 子类被契约拒绝（`ContractError`）。adapter 入口仍先做证据复制，子类走非快照路径并带 `evidence_copy_error_type`，不丢证据。 |
| B5-R1-6 | out-of-scope | 不阻塞收敛，交 Reporter 作为后续来源设计问题。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B5-R2-1 | suggestion | `tests/test_data_schema.py:108-109` | B5-R1-5 的契约改动（拒绝 `bytes` 子类）没有回归测试；现有用例只测 `bytearray`。 | 可在同一测试加入一个 `bytes` 子类的拒绝断言。不阻塞收敛。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B5-R2-1 | | |

- Round result：`converged`。B5-R1-1、B5-R1-2、B5-R1-3、B5-R1-5 已解决；B5-R1-4、B5-R1-6、B5-R2-1 交 Reporter。未验证真实来源、原始字节落盘、quarantine 流程和旧版本迁移。此结论仅适用于 B5，不代表整个 PR 已通过 Validator。

## Block B6 · Silver 市场、outcome 与结算 · Round 1 · 2026-11-13

- 目标：PLAN.md B6 行——可保留市场描述、结算条件、计划与实际时间；outcome 说明可空，不同市场身份区分；未知结算时间不编造。依据 CODE_READING_PROGRESS.md 第 164 行（负责人决定）、第 166 行与第 170 行第 1 条（agent 自主决定）及 FOUNDATION_RULES.md §3。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本块文件 `src/data_schema/schema_registry.json`、`src/adapters/mock.py`、`tests/test_data_schema.py`（未跟踪）、`tests/test_adapter_contract.py`（未跟踪）、`tests/test_pipeline_foundation.py`、`docs/SCHEMAS.md`、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`docs/pr1/PLAN.md`、`README.md`、`CHANGELOG.md`。磁盘内容与修订包一致（registry `6.0.0`；`silver.markets` 无 `open_at`/`close_at`，新增六个可空字段及两组 `compare` 规则；`silver.outcomes` 主键 `(venue, market_id, outcome_id, observed_at)` 且有可空 `description`；`silver.settlements.settled_at` 为 `utc_datetime?`；mock `primary_keys` 中 settlements、outcomes 为 `(market_id, outcome_id)`）。另：`docs/pr1/CODE_READING_PROGRESS.md` 第 177 行已写入“B5-R2-1 的 bytes 子类测试已随 B6 修订补上”，但该文件不在修订包改动列表中（见 B6-R1-2）。其他 PR1 工作区改动不在本块范围。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；`uv run pytest tests/test_data_schema.py tests/test_adapter_contract.py tests/test_pipeline_foundation.py -k 'market or outcome or settlement or schema or registry or bronze_requires or new_normalizers or populated' -q` → 97 passed、131 deselected；`uv run pytest tests/ -v` → 441 passed、5 warnings；`scripts/generate_schema_docs.py` 的 `regenerate()` 与 `docs/SCHEMAS.md` 一致。临时脚本（`uv run python <scratchpad>/probe_b6.py`，不写仓库）实测：mock 收到含 `open_at`/`close_at` 的来源记录时四个时间字段均为空；`description` 为 `""`、`"  "` 或 `5` 时整行 `NormalizationError`；计划组开放晚于关闭被拒；跨组（实际开放早于计划开放、实际关闭早于计划关闭）可通过；`settled_at=None` 时输出为空、`observed_at` 取 Bronze 接收时间；outcome/settlement 主键均为 `(venue, market_id, outcome_id, observed_at)`。全仓 grep：代码、测试、生成文档中除“已删除”说明和拒绝旧字段的测试外，无残留 `open_at`/`close_at`；`5.0.0` 仅作为 B5 历史版本出现；CODE_READING_PROGRESS §4.8 第 311 行的 `open_at <= close_at` 为历史待办原文。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B5-R2-1 | resolved | `tests/test_data_schema.py:111-114` 定义 `BytesSubclass(bytes)` 并断言 `ContractError("must be bytes")`；全量测试通过。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B6-R1-1 | should-fix | `src/data_schema/schema_registry.json:179-191`；`docs/pr1/SCHEMA_REVIEW.md:30`；对照 `docs/pr1/CODE_READING_PROGRESS.md:164` | 负责人确认的决定写的是“来源没有说明时间属于计划还是实际时**保留来源原文**，不猜测字段含义”，并且该句位于 Silver 市场契约决定中。修订包把它解释为“四个 Silver 时间字段都留空，原文只留在 Bronze”，这是 agent 自主的解释，但仓库内只以契约事实的形式写在 registry 描述和 SCHEMA_REVIEW 第 30 行，没有像第 166 行那样作为 agent 自主决定（含理由、与负责人决定的关系）单独记录，也没有标记需交负责人确认。实测后果：此类来源的 Silver 市场行会丢失所有开放/关闭时间信息，且 Silver 使用者无法区分“来源未提供”和“来源提供但未区分计划/实际”，只能回 Bronze 重新解析。若负责人原意是 Silver 保留原文，则与已确认决定冲突（AGENTS.md 要求实施前上报）。 | 不必先改代码：在 CODE_READING_PROGRESS 中以“agent 自主决定”单独记录该解释、理由（简单优先、Bronze 可追溯）和代价（Silver 不可区分两种空值），并由 Reporter 明确交负责人确认；若负责人要求 Silver 保留原文，再另行增加字段并升级版本。 |
| B6-R1-2 | suggestion | `docs/pr1/CODE_READING_PROGRESS.md:164`、`166`、`170`（第 1 条）、`177` | 三处 B6 来源条目仍写“待实施”/“尚未修改代码”，现已实施；第 177 行在本修订中被改动但未列入修订包。参照 B5 的做法（第 177 行在收敛后追加实施条目），不阻塞本轮。 | 收敛时追加 B6 实施条目（含版本 `6.0.0`、review 结果与未验证项），并在修订包中列出该文件。 |
| B6-R1-3 | suggestion | `src/data_schema/schema_registry.json:167,171,272`；`src/adapters/mock.py` `_normalize_market`/`_normalize_outcome` | 描述类字段沿用 `str` 非空白规则，mock 原样透传。实测来源给出 `description: ""` 时整条市场记录规范化失败（`NormalizationError`），而不只是该字段为空；真实来源常见空字符串描述，届时大量正常市场会进入审核。行为不静默、有证据，属于已声明的设计取舍。 | 在 SCHEMA_REVIEW 或 adapter 文档中写明：空字符串描述如何映射由各来源 adapter 决定并说明理由（例如是否视为未提供），避免后续 adapter 各自隐式处理。 |
| B6-R1-4 | suggestion | `tests/test_adapter_contract.py:633-660`；`tests/test_data_schema.py:648` | (1) 本块关键设计“来源未区分计划/实际时四个字段为空”没有直接测试，mock 只是忽略未知键（临时脚本确认含 `open_at`/`close_at` 时四字段为空）；(2) 第 648 行注释写“an early actual close is representable”，但其下一行改动的是 `actual_open_at` 早于计划开放（提前关闭已体现在基础行中），注释与断言不完全对应。 | 增加一条含不明确时间键（如 `open_at`/`close_at`）的 mock 规范化断言；修正注释或补充对应断言。 |
| B6-R1-5 | out-of-scope | `src/adapters/mock.py` `_fetch_settlements`（按 `settled_at` 过滤时间窗） | 结算时间现可未知，但采集接口的时间窗 `[start, end)` 语义仍以结算时间为准；mock 数据总有时间所以不触发。真实来源中无结算时间的结算记录如何按时间窗回填（例如按发布或接收时间），需在 PR5/PR6 adapter 设计中规定，否则可能漏取。 | 交 Reporter 记录为后续 adapter 设计问题。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B6-R1-1 | fixed（负责人决定） | 询问负责人后确认：Silver 新增可空 `source_open_time_text`、`source_close_time_text`，按原样保存未说明计划/实际的来源时间原文，不解析；四个计划/实际时间仍留空。更新 registry（仍为 `6.0.0`，本块未收敛）、mock（mock 的 `open_at`/`close_at` 视为未分类原文，非字符串报 `NormalizationError`）、SCHEMAS 生成表、SCHEMA_REVIEW、CHANGELOG；决定记录在 CODE_READING_PROGRESS。测试：`test_mock_unclassified_source_times_are_kept_as_text_only`，`test_market_keeps_scheduled_and_actual_times_separately` 覆盖原文字段可空与非空白。 |
| B6-R1-2 | fixed（采纳） | CODE_READING_PROGRESS 增加 “B6 实施状态” 条目，说明前述待实施条目已实施；该文件列入本轮修订。 |
| B6-R1-3 | fixed（采纳，文档） | SCHEMA_REVIEW 写明来源空字符串/空白如何映射由各来源 adapter 按来源语义决定并记录，契约拒绝空白值。 |
| B6-R1-4 | fixed（采纳） | 新增未分类时间 mock 测试（见 B6-R1-1）；`test_data_schema.py` 注释对应的断言改为提前的 `actual_close_at`。 |
| B6-R1-5 | deferred（out-of-scope） | 无时间结算的回填方式交 Reporter，留 PR5/PR6。 |

- Round result：`changes requested`。已核实满足的部分：市场描述、结算条件、计划与实际开放/关闭时间可分别保存并经 Arrow 往返；两组时间各自 `open <= close`（允许相等），组间不比较；旧 `open_at`/`close_at` 作为未知字段被拒；outcome `description` 可空且有值时非空白，不同 `market_id` 的相同 outcome 主键不同；`settled_at` 可空，mock 缺时间时不以观察时间代替；版本 `6.0.0` 与 SCHEMAS.md、SCHEMA_REVIEW、README（v6）、CHANGELOG 一致，SCHEMAS.md 与 registry 生成结果一致。未验证真实来源字段映射、ID 唯一范围、跨行主键唯一性和旧版本迁移。

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 442 passed、5 warnings；`git diff --check` 通过。

## Block B6 · Silver 市场、outcome 与结算 · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；相对 Round 1 修改 `src/data_schema/schema_registry.json`、`src/adapters/mock.py`、`tests/test_adapter_contract.py`（未跟踪）、`tests/test_data_schema.py`（未跟踪）、`docs/SCHEMAS.md`（重新生成）、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`CHANGELOG.md`、`docs/pr1/CODE_READING_PROGRESS.md`。磁盘内容与 Analyst response 一致：registry 仍为 `6.0.0`，`silver.markets` 新增可空 `source_open_time_text`、`source_close_time_text`（`str?`），规则未变；mock `_optional_text` 将来源 `open_at`/`close_at` 原样透传、非字符串抛 `SourceDataError`。另顺带核对 `agent/PROJECT.md` §6 原始记录外壳字段列表已补 `api_version`、`protocol_version`、`raw_payload / raw_bytes`（B5-R1-4 后续，非 B6 范围），与 `bronze.raw` 契约一致。负责人选择“Silver 加原文字段”以 CODE_READING_PROGRESS 第 179 行及 Analyst response 的记录为据，Reviewer 无法独立核实负责人原话。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；`uv run pytest tests/test_data_schema.py tests/test_adapter_contract.py tests/test_pipeline_foundation.py -k 'market or outcome or settlement or schema or registry or bronze_requires or new_normalizers or populated or unclassified' -q` → 98 passed、131 deselected；`uv run pytest tests/ -v` → 442 passed、5 warnings；`scripts/generate_schema_docs.py` 的 `regenerate()` 与 `docs/SCHEMAS.md` 一致。临时实测（不写仓库）：mock `open_at=" 2024 "` 原样保存（不去空白）；`""`、`"  "` 得到 `NormalizationError`（契约非空白规则）。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B6-R1-1 | resolved | 负责人决定已记录于 `docs/pr1/CODE_READING_PROGRESS.md:179`；registry 新增两个原文字段，四个计划/实际时间字段描述改为“原文见 source_open_time_text / source_close_time_text”；SCHEMA_REVIEW 第 30 行说明可区分“来源没给”和“来源给了但未分类”，第 56 行版本说明列入新字段；`test_mock_unclassified_source_times_are_kept_as_text_only` 断言原文原样保存、四个时间为空、数字值被拒。 |
| B6-R1-2 | resolved | CODE_READING_PROGRESS 第 179 行新增“B6 实施状态”，说明前述“待实施”条目保留为当时记录；本轮修订包已列出该文件。 |
| B6-R1-3 | resolved | SCHEMA_REVIEW 第 30 行写明来源空字符串/纯空白的映射由各来源 adapter 按来源语义决定并记录，契约拒绝空白值。 |
| B6-R1-4 | resolved | (1) 见 B6-R1-1 的新测试；(2) `tests/test_data_schema.py:648-649` 注释与断言一致（`actual_close_at` 早于计划关闭），第 650、653-656 行另覆盖原文字段可空与空白被拒。 |
| B6-R1-5 | out-of-scope | 不阻塞收敛，交 Reporter，留 PR5/PR6。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B6-R2-1 | suggestion | `docs/pr1/SCHEMA_REVIEW.md:30`；`src/data_schema/schema_registry.json`（`source_open_time_text`/`source_close_time_text` 描述） | 字段写“按原样保存”，但 `str?` 只能保存非空白文本：来源原值为空白时整行规范化失败，为数字（如 epoch 秒）时无法“原样”存为文本（mock 拒绝）。SCHEMA_REVIEW 关于空字符串由 adapter 决定的说明紧随 `description`/`settlement_rules`，未明确是否也适用于这两个原文字段，数字原值如何转为文本也未说明。行为不静默、不阻塞本块。 | 在 SCHEMA_REVIEW 中明确该 adapter 映射说明同样适用于未分类时间原文，并说明非字符串原值（是否按来源 JSON 文本表示保存）由来源 adapter 决定并记录；可留给 PR5/PR6 首个真实 adapter 时一并处理。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B6-R2-1 | | |

- Round result：`converged`。B6-R1-1 至 B6-R1-4 已解决；B6-R1-5、B6-R2-1 交 Reporter。B6 验收（描述、结算条件、计划/实际时间及未分类原文、outcome 说明可空、按市场区分 outcome 身份、未知结算时间不编造）已由代码、测试和文档核实。未验证真实来源字段映射、ID 唯一范围、跨行主键唯一性和旧版本迁移。此结论仅适用于 B6，不代表整个 PR 已通过 Validator。

## Block B5a · API 版本可选 · Round 1 · 2026-11-13

- 目标：负责人决定（`docs/pr1/CODE_READING_PROGRESS.md:178` 第 ② 条，B5-R1-6 的后续）——adapter 可不声明 API 版本（`None`）；声明时必须为非空字符串；无 API 版本的 Bronze 记录可被同样无 API 版本的 adapter 规范化到 Silver；与有版本 adapter 之间互不误路由。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本块文件 `src/adapters/base.py`、`tests/test_adapter_contract.py`（未跟踪）、`agent/PROJECT.md`（§6 第 115 行、§8 第 150 行）、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪，第 30 行末尾）、`docs/pr1/CODE_READING_PROGRESS.md`。磁盘内容与修订包一致：`AdapterMetadata.api_version: str | None`（`base.py:175-176`），`api_version`/`protocol_version` 共用“非空字符串或 None”校验（`base.py:217-220`），`api_protocol_version` 对 None 显示 `none`（`base.py:180-181`），路由仍为 `(venue, api_version, protocol_version)` 三元组相等（`base.py:290-293`）；`test_empty_metadata_rejected` 参数中已无 `api_version`；新增两项测试位于 `tests/test_adapter_contract.py:694-719`。其他 PR1 工作区改动不在本块范围。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；`uv run pytest tests/test_adapter_contract.py -k 'metadata or version or routing or wrong_venue or api' -q` → 33 passed、60 deselected；`uv run pytest tests/test_adapter_contract.py -q` → 93 passed；`uv run pytest tests/ -v` → 448 passed、5 warnings。临时脚本（`PYTHONPATH=. uv run python <scratchpad>/probe_b5a.py`，不写仓库）实测：无 API 版本 adapter 对 `api_version=None` 的 trade、book 事件均可规范化；收到 `"1"` 或字面 `"none"` 时 `AdapterRoutingError`；`api_version=None, protocol_version="p2"` 的 adapter 只接受同样三元组；`venue=None` 的记录仍被路由拒绝；metadata 中 `api_version` 为 `""`、`b"1"`、`0` 及 `protocol_version=""` 均报 `ValueError`；Bronze 契约拒绝 `api_version` 为 `""`/`" "`。全仓 grep `api_version`、`API/protocol`、`protocol version`、`API 版本`：代码与测试中除 mock 声明 `"1"`、测试外壳默认 `"1"` 外，无其他假设 API 版本必填的逻辑；`api_protocol_version` 只在测试中使用。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B5-R1-6 | resolved | 负责人决定见 `CODE_READING_PROGRESS.md:178` ②；`base.py:175-176` 允许 None，`test_adapter_without_api_version_normalizes_matching_records_only`（`tests/test_adapter_contract.py:707-719`）断言无版本 adapter 规范化无版本记录、拒绝有版本记录，且有版本的 mock 拒绝无版本记录；临时脚本补充确认 trade、book 事件同样可规范化。 |
| B5-R1-4 | resolved | 负责人确认见 `CODE_READING_PROGRESS.md:178` ①；`agent/PROJECT.md:115` 已列入 `api_version`、`protocol_version`、`raw_payload / raw_bytes`，与 registry `bronze.raw` 字段一致（`run_id`、`record_index` 为存储主键，未列入外壳概念列表）。 |
| B6-R2-1 | resolved | `docs/pr1/SCHEMA_REVIEW.md:30` 末尾写明空白映射说明同样适用于 `source_open_time_text`、`source_close_time_text`，非字符串原值（如 epoch 数字）如何保存由来源 adapter 决定并记录，原始值保留在 Bronze。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B5a-R1-1 | suggestion | `docs/pr1/CODE_READING_PROGRESS.md:177`、`178` | 第 177 行仍写“B5-R1-6（无 API 版本的 venue 记录目前无法进入 Silver，留待来源设计）”，第 178 行 ② 仍为“作为 B5a 在 B6 审查结束后实施”的将来时；工作区尚无 B5a 实施状态条目（修订包所称“记录条目”目前仅见第 180 行“随 B5a 修订复核”）。与 B6-R1-2 情况相同，不阻塞本轮。 | 收敛后参照第 179 行追加“B5a 实施状态”条目（实施内容、review 结果、未验证项），说明第 177、178 行为当时记录。 |
| B5a-R1-2 | suggestion | `docs/adr/ADR-001-v1-architecture.md:19`；`docs/adr/ADR-002-pr1-foundation.md:39-45`；`CHANGELOG.md:9` | ADR-001 仍写“Require versioned venue adapters to declare … API/protocol versions”，ADR-001 已注明由 ADR-002 补充，但 ADR-002 的 Adapter 决定和 CHANGELOG 均未提到 API 版本可为 none。`agent/PROJECT.md` §8 作为唯一事实来源已更新，因此不构成冲突；但只读 ADR 的人会以为 API 版本必填。（`agent/PROJECT.md:33` 关于 Polymarket 需带 API/协议版本的描述仍适用于该来源，无需修改。） | 在 ADR-002 “Adapter 与日志”决定中补一句：来源没有或不适用 API/协议版本时声明为 None，不编造，路由按三元组精确相等；CHANGELOG 可在 adapter 条目中顺带说明。 |
| B5a-R1-3 | suggestion | `src/adapters/base.py:180-181` | `api_protocol_version` 用 `or 'none'` 渲染，`api_version=None` 与字面 `api_version="none"` 均显示为 `api=none`（临时脚本实测），两者路由时却互不匹配。当前该属性仅在测试中使用，无实际影响；若将来写入日志、运行记录或 manifest 作为 adapter 身份，会产生歧义。 | 只作显示用途时在 docstring 说明；若用于记录身份，改为可区分的表示（如 `api=<none>` 或结构化字段），或直接记录原三元组。 |
| B5a-R1-4 | out-of-scope | `src/adapters/base.py:290-293`（三元组精确相等路由） | 按设计，一个 adapter 实例只能接受一种 `api_version`（含 None）。同一来源若同时存在无版本历史归档与有版本实时接口，需要分别声明 adapter 或实例；`venue=None` 的非 venue 来源记录也仍不能被任何 adapter 规范化（`AdapterMetadata.venue` 必填）。两者都是已明确的设计取舍，行为显式报错不静默。 | 交 Reporter，在 PR5/PR6 真实来源 adapter 设计时决定多版本/无版本来源的 adapter 组织方式及非 venue 来源的规范化路径。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B5a-R1-1 | fixed（采纳） | CODE_READING_PROGRESS 新增 “B5a · API 版本可选” 条目，并说明 B5 条目的旧表述已不成立。随 B7 修订复核。 |
| B5a-R1-2 | fixed（采纳） | ADR-002 “Adapter 与日志” 决定补充无版本声明 `None` 与三元组精确路由；CHANGELOG 同步。ADR-001 保留原文（ADR-002 补充它）。随 B7 修订复核。 |
| B5a-R1-3 | fixed（采纳） | `api_protocol_version` 改用 `repr`，`None` 显示为 `api=None`，字面 `"none"` 显示为 `api='none'`；测试断言两者不同。随 B7 修订复核。 |
| B5a-R1-4 | deferred（out-of-scope） | 交 Reporter，PR5/PR6 设计真实来源 adapter 时决定。 |

- Round result：`converged`。B5a 验收已由代码、测试和临时实测核实：adapter 可声明 `api_version=None`；声明时非空字符串，空串、空白和非字符串被拒；无 API 版本的 Bronze 记录可被无版本 adapter 规范化到 Silver（market、trade、book 事件）；有版本与无版本 adapter 之间互不误路由。B5-R1-4、B5-R1-6、B6-R2-1 已解决；B5a-R1-1 至 B5a-R1-3（suggestion）、B5a-R1-4（out-of-scope）交 Reporter。B7（每日数据时间边界）及以后内容不在本块审查范围。未验证真实来源的 API 版本语义及多版本来源的 adapter 组织。此结论仅适用于 B5a，不代表整个 PR 已通过 Validator。

## Block B7 · 每日时间边界与后续限制 · Round 1 · 2026-11-13

- 目标：`docs/pr1/PLAN.md:21` B7 —— 当日数据的可用时间不能早于该 UTC 日开始；不假设日内汇总必须等到当天结束；其他质量问题明确记录为后续 PR 处理（`CODE_READING_PROGRESS.md:169-175` “阅读发现与后续处理”第 3 条实施，第 2、4、5、6 条记录）。另随本轮复核 B5a-R1-1 至 B5a-R1-3 的修复。
- Revision：`codex/pr1-architecture` @ `76f1795`，未提交工作区；本块文件 `src/data_schema/contracts.py`、`src/data_schema/schema_registry.json`、`tests/test_data_schema.py`（未跟踪）、`docs/SCHEMAS.md`、`docs/pr1/SCHEMA_REVIEW.md`（未跟踪）、`docs/pr1/PLAN.md`、`README.md`、`CHANGELOG.md`；B5a 修复文件 `src/adapters/base.py`、`tests/test_adapter_contract.py`（未跟踪）、`docs/adr/ADR-002-pr1-foundation.md`（未跟踪）、`docs/pr1/CODE_READING_PROGRESS.md`。磁盘内容与修订包一致：`day_start` 声明于 `contracts.py:52`、`77`，registry 自检 `contracts.py:194-197`，执行 `contracts.py:339-347`；registry `version` 为 `7.0.0`，`gold.market_daily` 规则末尾为 `{"type":"day_start","field":"as_of","day":"day"}`；两项新测试位于 `tests/test_data_schema.py:681-709`。修订包所称 SCHEMA_REVIEW “版本历史”实际为“关键选择”第 1 条（`SCHEMA_REVIEW.md:56`）中的版本说明，没有单独的版本历史段，不影响内容。
- Reviewer 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；`uv run pytest tests/test_data_schema.py -k 'day_start or daily' -q` → 7 passed、64 deselected；`uv run pytest tests/test_data_schema.py -q` → 71 passed；`uv run pytest tests/test_adapter_contract.py -q` → 93 passed；`uv run pytest tests/ -v` → 453 passed、5 warnings。临时脚本（`PYTHONPATH=. uv run python <scratchpad>/probe_b7.py`，Python 3.9.6，不写仓库）实测：registry 中 `field` 改为 `market_id`、`day` 改为 `as_of`、删除 `day` 的 `iso_date` 规则均报 “day_start needs a UTC datetime and an iso_date day field”；删 `day` 键或加多余键报 “malformed day_start rule”；`day` 指向不存在字段报 “rule references unknown field”；把 `day_start` 移到 `iso_date` 之前仍通过自检（不依赖顺序）。记录级：`as_of` 比 `2024-01-02` 零点早 1 微秒被拒；`day` 为 `"20240102"`、`"2024-1-2"`、`"2024-01-02T00:00"` 均以 “must be an ISO calendar date” 拒绝，`None`、整数分别以必填和类型错误拒绝；`+08:00` 的等价时间被严格 UTC 检查拒绝；直接调用 `_check_rule` 时无法解析的 `day` 抛 `ContractError`。版本一致性：`git grep --untracked` 检索 `x.0.0` 与 `v<n>`，`schema_registry.json`、`docs/SCHEMAS.md:1`、`:8`、`SCHEMA_REVIEW.md:3`、`:21`、`:56`、`README.md:74`、`CHANGELOG.md:17` 均为 `7.0.0`/v7；其余 `3.0.0`、`4.0.0`、`6.0.0` 出现在 `CODE_READING_PROGRESS.md` 的当时阅读记录（110、138、143、160、179 行）或版本历史说明中，属历史记录，非残留错误；`ADR-001:41` 的 “version 2” 是 ADR-001 当时决定，已由 ADR-002 补充。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B5a-R1-1 | resolved | `CODE_READING_PROGRESS.md:181` 新增 “新工作流 B5a · API 版本可选” 条目，写明 B5 条目中“无 API 版本的 venue 记录目前无法进入 Silver”已不成立，并列出 B5a-R1-4 后续。 |
| B5a-R1-2 | resolved | `ADR-002-pr1-foundation.md` “Adapter 与日志”决定（第 43 行）补充：无或不适用 API/协议版本时声明 `None` 不编造，按 `(venue, api_version, protocol_version)` 精确相等路由且先于内容解析；`CHANGELOG.md:9` 同步。ADR-001 保留原文、由 ADR-002 补充，可接受。 |
| B5a-R1-3 | resolved | `src/adapters/base.py:180-182` 改为 `f"api={self.api_version!r}; protocol={self.protocol_version!r}"` 并加注释；`tests/test_adapter_contract.py:712-713` 断言 `None` 显示为 `api=None`、字面 `"none"` 显示为 `api='none'`。全仓该属性仍只在测试中使用。`tests/test_adapter_contract.py` 93 passed。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B7-R1-1 | suggestion | `docs/pr1/CODE_READING_PROGRESS.md:169-175`、`181` 之后 | “阅读发现与后续处理”第 3 条仍为将来时（“本 PR 增加最小时间边界及测试”），工作区没有 B7 实施状态条目；第 2、4、5、6 条也未指向现已集中记录这些限制的 `SCHEMA_REVIEW.md` “关键选择”第 7 条。与 B5a-R1-1、B6-R1-2 情况相同，不阻塞。另 `SCHEMA_REVIEW.md:15` “日期。 `day_start`” 中句号后多一个空格（排版小问题）。 | 收敛后参照第 179、181 行追加 “B7 实施状态” 条目：第 3 条已实施（契约 `7.0.0`），第 2、4、5、6 条记录于 SCHEMA_REVIEW 第 7 条，原文保留为当时记录。 |
| B7-R1-2 | suggestion | `src/data_schema/contracts.py:347` | 错误信息插入的是规则中的字段名 `rule['day']` 而非日期值，实际输出 `gold.market_daily.as_of must not be before the start of UTC day day`（临时脚本实测），读起来像重复词，也不显示被拒的具体日期，排查 quarantine 记录时信息不足。 | 改为同时给出字段名与值，例如 `... before the start of UTC day {day} ({rule['day']})`；同步测试的 `match`。 |
| B7-R1-3 | suggestion | `tests/test_data_schema.py:690-691`、`708`；`src/data_schema/contracts.py:342-345` | ① `test_daily_as_of_not_before_utc_day_start` 中非法日期 `2024-13-01` 实际由排在前面的 `iso_date` 规则拒绝（同样含 “ISO calendar date”），因此 `day_start` 自身的解析失败分支（342-345）没有被直接覆盖；② `test_day_start_rule_declaration_is_checked` 用不带 `match` 的 `pytest.raises(ValueError)`，若将来因其他原因（例如版本规则变化）报错也会通过。临时脚本确认当前 4 种变体都是预期原因报错，因此只是测试强度问题。 | ① 直接对 `_check_rule` 或对去掉 `iso_date` 前置顺序的临时 registry 测试解析失败分支，并用能区分两处来源的 `match`（如含 `day_start` 字样或字段名）；② 为 4 种变体分别加 `match`（`day_start needs` / `malformed day_start rule`）。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B7-R1-1 | fixed（采纳） | CODE_READING_PROGRESS 新增 B7 条目并指向 SCHEMA_REVIEW 第 7 条；SCHEMA_REVIEW 多余空格已删。交 Validator 复核。 |
| B7-R1-2 | fixed（采纳） | 错误信息改为 `... start of UTC day 2024-01-02 (day)`，测试 `match` 同步。交 Validator 复核。 |
| B7-R1-3 | fixed（采纳） | 直接调用 `_check_rule` 测试 `day_start` 对无法解析日期（非法字符串、整数）的拒绝；声明自检 4 种变体分别加 `match`。交 Validator 复核。 |

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 453 passed、5 warnings；`git diff --check` 通过。

- Round result：`converged`。B7 验收已由代码、测试和临时实测核实：`gold.market_daily.as_of` 早于 `day` 的 UTC 零点（含早 1 微秒）被拒，等于零点、日内及数日后均通过，不要求当日结束；规则以通用 JSON 类型 `day_start` 声明，执行器未硬编码数据集或字段名，registry 自检拒绝错误类型、缺少 `iso_date` 和畸形声明；契约主版本升至 `7.0.0`，所有现行文档版本一致；`CODE_READING_PROGRESS` 第 2、4、5、6 条后续限制已在 `SCHEMA_REVIEW.md` “关键选择”第 7 条明确记录为未实现并指明对应后续 PR。B5a-R1-1 至 B5a-R1-3 已解决。B7-R1-1 至 B7-R1-3（suggestion）交 Reporter。未实现：日内汇总完整性、覆盖规则、质量门禁、旧版本迁移。此结论仅适用于 B7，不代表整个 PR 已通过 Validator。

## Validator · PR1 最终验证 · Round 1 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，完整未提交工作区（30 个已修改文件 + 11 个未跟踪文件，含 `src/`、`tests/`、`scripts/`、`docs/`、`agent/`、`README.md`、`CHANGELOG.md`、`pyproject.toml`、`uv.lock`）。Validator 与 Analyst、各块 Reviewer 为不同上下文；只读审查，唯一写操作为本节。
- Validator 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/ -q` 为 453 passed、5 warnings（均来自旧 analysis 测试及 websockets 弃用）；`git diff --check` 通过（不覆盖未跟踪文件；另查未跟踪文件，仅 `docs/adr/ADR-002-pr1-foundation.md` 第 3–4 行为 Markdown 硬换行的两个尾随空格）。Analyst 自报的四项结果均复现。
- 过程说明：Validator 误以 `--help` 调用 `scripts/generate_schema_docs.py`（脚本不解析参数，直接重写 `docs/SCHEMAS.md`）。重写前后 `test_schema_document_matches_code_registry` 均通过、`git diff --stat docs/SCHEMAS.md` 不变（284+/312−），内容未变，仅 mtime 更新。
- 临时探测（scratchpad 及 pytest 外的临时目录，未触碰真实 `DATA_ROOT`/`.env`）：decimal 精度边界、零数量成交、市场时间同时填写分类与未分类原文、错误路由且 `raw_payload` 非法 JSON、写锁并发、recovery 中异常文件。

### B7 收敛后采纳的 suggestion 复核

| ID | Status | Evidence |
| --- | --- | --- |
| B7-R1-1 | resolved | `CODE_READING_PROGRESS.md:182` 新增 B7 实施状态条目，指向 SCHEMA_REVIEW 第 7 条。 |
| B7-R1-2 | resolved | `contracts.py:347` 错误信息含日期值与字段名；`test_daily_as_of_not_before_utc_day_start` 以 `2024-01-02 \(day\)` 匹配。 |
| B7-R1-3 | resolved | 测试直接调用 `_check_rule` 覆盖非法字符串与整数日期（`TypeError` 分支）；声明自检 4 种变体分别带 `match`。 |

### 抽查已 resolved 的发现

B1-R1-2/B1-R2-1/B1-R3-1（`validation.py:59-84` 只用固定消息和已声明顶层字段）、B2-R1-1（`layout.py:72-83` 已存在目录仍同步父目录）、B2-R1-2（`layout.py:199-205`）、B3-R1-2（`contracts.py:299` 捕获 `RecursionError`）、B3-R1-3（`contracts.py:451`）、B5-R1-5（`contracts.py:482` 精确 `bytes`）、B6-R1-1（registry 新增两个原文字段）、B5a（`base.py:175-176,218-221`）均在最终代码中成立。

### Findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| V1-1 | should-fix | `scripts/generate_schema_docs.py:30`；`docs/SCHEMAS.md` `gold.market_daily.day` 行 | 生成器用硬编码键列表 `("field","left","right","result","when","reason","required","start")` 关联规则与字段，漏了 B7 新增 `day_start` 的 `day` 键；生成表中 `day` 行只列 `iso_date`，未列 `day_start`。SCHEMA_REVIEW 第 3 行声称表格列出“适用的每条规则”。同步测试只比较“生成结果 = 文件”，因此生成器自身的遗漏不会被发现。这是跨块问题：B4 生成器与 B7 新规则的关联逻辑重复且已漂移。 | 生成器改用 `contracts._RULE_FIELDS[rule["type"]]` 取引用字段；增加测试：每条规则出现在其引用的每个字段行中；重新生成 SCHEMAS.md。 |
| V1-2 | should-fix | `src/adapters/base.py:286-294`；`CHANGELOG.md:9`；`docs/adr/ADR-002-pr1-foundation.md:43` | CHANGELOG 与 ADR-002 称路由“在解析原始内容之前”检查，但 `_payload` 先执行 `validate_record("bronze.raw")`，其中会对 `raw_payload` 做 JSON 解析。实测：`venue="other"` 且 `raw_payload="{not json"` 时抛 `NormalizationError("silver.trades: raw_payload must contain valid JSON text…")`，而非 `AdapterRoutingError`，误路由会被记成本 adapter 数据集的数据错误。`CODE_READING_PROGRESS.md:177` 写的“外壳校验 → 路由”顺序与代码一致，但对外文档不一致；`test_routing_is_checked_before_content_and_time` 未覆盖非法 `raw_payload` 文本。 | 二选一并补测试：①在外壳校验前先检查三元组身份（需先确认外壳是映射且含这三个键）；或②修正 CHANGELOG/ADR-002 为“外壳契约校验（含 `raw_payload` JSON 语法）之后、解码 `raw_bytes`、时间检查和严格解析之前”。 |
| V1-3 | should-fix | `src/data_io/layout.py:86-101`（`LOCK_NB`）、`344-357`；`tests/test_writer_recovery.py:50`；`README.md:57`；ADR-002 第 11 行 | 写锁是非阻塞的：另一协作写入方持锁时立即抛 `Writer lock is held by another process`（同进程也报 “another process”），不会等待。`DataLayout.create` 在持锁期间遍历全部六层（含未来可能很大的 `imports/` 解压内容）并对 recovery 中所有 payload 计算 SHA-256，规模增大后持锁时间变长，并发写入方随之失败。不会静默丢数据，但文档只写“协调”，测试名 `test_recovery_waits_for_lock…` 断言的却是立即失败。 | 文档写明 fail-fast 语义和初始化扫描成本；测试改名；是否改为带超时的阻塞锁、是否限制扫描范围，交负责人（见 owner-question）。 |
| V1-4 | suggestion | `src/data_schema/schema_registry.json` `silver.markets` | `source_open_time_text` 描述为“来源已明确区分或未提供时为空”，但契约允许同一行同时填 `scheduled_open_at` 和 `source_open_time_text`（实测通过），该说明未被执行，也未声明由 adapter 负责。 | 增加行级规则，或在描述/SCHEMA_REVIEW 中写明由 adapter 保证。 |
| V1-5 | suggestion | `src/cli.py:13-21`；`agent/AGENTS.md` 硬规则 10 | 硬规则 10 要求任务启动时记录有效的非敏感配置值及其来源（默认或覆盖）。PR1 没有数据任务；`check` 包在 `pipeline_logging` 中，但生产路径不输出任何日志；CHANGELOG 删除了原先“未来任务记录有效设置”的说明，也没有记录推迟到哪个 PR。 | 在 `check` 中输出一条 INFO 事件，列出有效值及来源；或在 PLAN/CHANGELOG 中写明由首个数据任务 PR 实现。 |
| V1-6 | suggestion | `src/adapters/base.py:356-360` | adapter 返回无效盘口数据集时抛普通 `ValueError`；其他“adapter 输出与外壳不一致”的情况抛 `AdapterOutputError`，分类不一致。 | 改用 `AdapterOutputError`（它是 `ValueError` 子类，现有断言仍兼容）。 |
| V1-7 | owner-question | `docs/pr1/PLAN.md` 第 9、10 行 | 原 PR1 计划第 9 块“旧代码逐项迁移清单”仍为“待核对”。本轮 B1–B7 未包含它。 | 负责人确认：该清单是否为 PR1 合并前的必需交付，还是移到 PR3/后续 PR。 |
| V1-8 | owner-question | `src/data_io/layout.py:95` | 承接 V1-3：协作写入方遇锁应立即失败（当前），还是带超时等待？初始化扫描每次覆盖全部层并重新哈希 recovery，是否接受，还是限定为 Bronze/Silver/Gold 等可能产生 partial 的层？ | 负责人决定后由 Analyst 实施或记录。 |

### Simplification（与正确性发现分开）

| ID | Severity | 位置 | 建议 | 依据 / 失去的行为 / 保护测试 / 风险 |
| --- | --- | --- | --- | --- |
| V1-S1 | simplification | `src/data_io/layout.py:461-464` | 删除 `except Exception: raise`，把注释移到 `try` 上方。 | 纯死代码，行为不变；`test_writer_preserves_temporary_file_on_publish_failure`、`test_full_fsync_io_error_preserves_partial` 保护；无风险。 |
| V1-S2 | simplification | `src/data_io/layout.py:185-188`；`tests/test_writer_recovery.py:403` | `recovery_path` 和 `completion_check` 改为必填，删除 “legacy sidecar” 分支及其测试。 | HEAD 没有 recovery 实现，旧格式只存在于未发布的工作区迭代中。失去：接受缺这两个键的说明。其他损坏说明测试保留。风险：若负责人真实 `DATA_ROOT` 已有早期迭代写出的说明，初始化会报错，需先确认。 |
| V1-S3 | simplification | `src/adapters/base.py:179-182`；`tests/test_adapter_contract.py:712-713` | 删除 `api_protocol_version` 属性。 | 只有测试使用；PROJECT §8 要求声明版本，已由 `api_version`/`protocol_version` 字段满足。失去：一个显示字符串。若计划写入运行记录，宜在该 PR 用结构化字段。风险低。 |
| V1-S4 | simplification / owner-question | `src/adapters/base.py:61-71,93-97` | 不再用 `gc.get_referents` 识别可信的 `MappingProxyType`，所有代理都走“原引用 + `evidence_is_snapshot=False`”路径。 | 依据：Bronze 外壳由未来调度器构造，通常为 dict；`gc.get_referents` 依赖 CPython，B3 已记录其他实现未测。失去：只读代理输入可拿到独立副本。保护测试：`test_readonly_mapping_failure_preserves_bronze_evidence`、`test_nested_readonly_mapping_in_invalid_envelope_retains_evidence` 需改为断言引用路径。它属于负责人 B3 决定“能复制时交出独立副本”的适用范围，故作为负责人问题，不直接建议删除。 |
| V1-S5 | simplification | `scripts/generate_schema_docs.py:28-31` | 与 V1-1 合并：复用 `_RULE_FIELDS`，消除第二份规则字段映射。 | 修正 V1-1 的同时去掉重复逻辑；保护测试为生成器同步测试加 V1-1 的新测试。 |
| V1-S6 | simplification | `src/adapters/mock.py:61-83` | `metadata` 每次访问都重建并重新校验，可改为类级常量或缓存。 | 行为不变；现有元数据测试保护。收益小。 |
| V1-S7 | owner-question | `src/adapters/base.py:231-232` | `validation_rules` 只能等于 `(SCHEMA_VERSION,)`，不提供额外信息。 | PROJECT §8 要求声明 validation rules。是保留占位、赋予实际含义（例如适用的质量规则版本），还是由 `SCHEMA_VERSION` 隐含，由负责人决定。 |
| V1-S8 | owner-question | `src/cli.py:17-18`；`src/logging_config.py` | `check` 外层的 `pipeline_logging` 在生产路径无日志可输出。 | 负责人 §4.6 决定在 CLI 入口按 `log_level` 配置日志，因此不建议删除；可与 V1-5 一并处理，让该上下文实际输出有效配置。 |

审视后建议保留：`_check_macos_volume` 的逐段软链接解析（只用 `realpath` 会放过 `/Volumes/X → /`，见 `test_macos_volume_symlink_to_system_root_is_rejected`）；`_validate_recovery_metadata` 主体；`load_environment` 区分不存在与悬空软链接；三个单字段默认值/目录模型（确保在读取文件前校验并拒绝各文件未知键）；`ConfigModel` 的四个公开入口包装（B1 负责人决定）。

### 未验证项

真实交易所 API 与来源字段映射；真实外接盘、嵌套挂载、断电和 `F_FULLFSYNC`；大规模 `DATA_ROOT` 下初始化扫描耗时；多进程真实并发；Python 3.10+ 下 `date.fromisoformat` 宽松格式与规则顺序的交互（当前环境为 3.9，`iso_date` 规则兜底）；`gc.get_referents` 在非 CPython 的行为；依赖重新安装（`UV_NO_SYNC=1`）；`uv.lock` 与 pydantic 解析结果仅读 diff，未重新 `uv lock` 验证。

### 结论

`changes required`。没有发现 must-fix 或数据损坏风险；V1-1、V1-2、V1-3 为 should-fix（文档与代码或生成文档与 registry 不一致、并发语义未说明）。修复后经 Reviewer 循环和 Reporter 报告，再由 Validator 复查。V1-7、V1-8、V1-S4、V1-S7、V1-S8 需负责人决定。本结论不表示批准合并。

### Analyst response（Validator Round 1 → B8，2026-11-13）

负责人决定（2026-11-13）：V1-7 迁移清单移至 PR3；V1-8 写锁保持立即失败、只写清语义，超时等待与缩小扫描留 PR2；V1-5/V1-S8 在 PR1 的 `check` 中实现启动配置日志；同意 V1-S2、V1-S4、V1-S7。

| ID | Action | 处理及检查 |
| --- | --- | --- |
| V1-1 / V1-S5 | fixed | `contracts.RULE_FIELDS`（由 `_RULE_FIELDS` 改名公开）供生成器复用，删除生成器内手写键列表；重新生成后 `gold.market_daily.day` 行列出 `day_start`。新增 `test_generated_schema_tables_list_every_rule_on_each_referenced_field`。生成器拒绝任何命令行参数且不写文件（`test_schema_generator_rejects_arguments_without_writing`），避免 Validator 遇到的误写。 |
| V1-2 | fixed | `_payload` 在外壳契约校验前比较身份（仅当三项均为 `str` 或 `None`）；形式非法的身份由外壳契约拒绝。路由测试增加 `raw_payload="{not json"`、`record_index=-1`；新增 `test_malformed_identity_is_an_envelope_error_not_a_routing_error`。CHANGELOG、ADR-002 改为“外壳校验和解析之前”。 |
| V1-3 / V1-8 | fixed（文档，按负责人决定） | README、ADR-002、CHANGELOG 写明锁占用立即失败（同进程亦然）、数据不变、由调用方重试，及初始化持锁扫描成本；测试改名 `test_held_lock_fails_immediately_and_preserves_partial`。 |
| V1-4 | fixed（文档） | SCHEMA_REVIEW 写明契约不交叉检查计划/实际时间与原文字段，由 adapter 保证；同一来源可能同时提供已分类与未分类时间，故不加行级互斥规则。 |
| V1-5 / V1-S8 | fixed（负责人决定） | `PipelineConfig.load()` 记录各字段来源（私有属性），`effective_settings()` 返回生效值、来源和值的 SHA-256；`check` 以 `config.effective` 事件输出；`JsonFormatter` 支持 `details`。更新 `src/config/README.md`、`README_FOR_DEVELOPER.md`、CHANGELOG。测试：`test_check_logs_effective_settings_sources_and_hash`（含非相关 secret 不泄露）、`test_effective_settings_hash_depends_on_values_not_sources`，并更新日志级别测试。 |
| V1-6 | fixed | 无效盘口数据集改抛 `AdapterOutputError`；测试同步。 |
| V1-7 | deferred（负责人决定） | PLAN.md 第 9 块标为移至 PR3。 |
| V1-S1 | fixed | 删除 `_write_locked` 中仅 `raise` 的 `try/except` 并去缩进；行为不变。 |
| V1-S2 | fixed（负责人同意） | recovery 说明的 `recovery_path`、`completion_check` 改为必填；重建说明也写 `completion_check`；原兼容测试改为 `test_recovery_metadata_requires_path_and_completion_check`（缺任一字段报 `Invalid recovery metadata` 且不改证据）。 |
| V1-S3 | fixed | 删除仅测试使用的 `api_protocol_version` 及其断言。 |
| V1-S4 | fixed（负责人同意） | 删除 `gc.get_referents` 判断与代理复制分支，`_copy_raw_record` 只复制精确 `dict` 及内置值；只读代理（顶层或嵌套）一律保留原引用并标记非快照。两条旧测试合并为 `test_readonly_mapping_evidence_is_original_reference_not_snapshot`。 |
| V1-S6 | not adopted | 收益很小，保持现状。 |
| V1-S7 | fixed（负责人同意） | 删除 `AdapterMetadata.validation_rules`；PROJECT.md §8、ADR-002 改为校验规则来自共享契约；测试同步。 |

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 468 passed、5 warnings；`git diff --check` 通过；临时 `DATA_ROOT` 下 `uv run python -m src check` 输出 `config.effective` JSON 日志。

## Block B8 · Validator 发现修复 · Round 1 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，worktree, uncommitted（含未跟踪文件）。B8 文件：`src/config/models/pipeline.py`、`src/cli.py`、`src/logging_config.py`、`src/config/README.md`、`src/config/README_FOR_DEVELOPER.md`、`src/data_schema/contracts.py`、`scripts/generate_schema_docs.py`、`docs/SCHEMAS.md`、`src/adapters/base.py`、`src/adapters/mock.py`、`src/data_io/layout.py`、`tests/test_cli_logging.py`、`tests/test_data_schema.py`、`tests/test_adapter_contract.py`、`tests/test_pipeline_foundation.py`、`tests/test_writer_recovery.py`、`agent/PROJECT.md` §8、`docs/adr/ADR-002-pr1-foundation.md`、`README.md`、`CHANGELOG.md`、`docs/pr1/PLAN.md`、`docs/pr1/SCHEMA_REVIEW.md`、`docs/pr1/CODE_READING_PROGRESS.md`；顺带核对 `agent/VALIDATOR.md`、`agent/AGENTS.md` 角色表。磁盘内容与修订包一致。Reviewer 为独立上下文，只读审查，唯一写操作为本节。
- Checks run by Reviewer（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过（未跟踪文件另查：仅 ADR-002 第 3 行 Markdown 硬换行尾随空格，沿用 Validator 记录）；定向 `uv run pytest tests/test_cli_logging.py tests/test_config.py tests/test_adapter_contract.py tests/test_data_schema.py tests/test_writer_recovery.py tests/test_pipeline_foundation.py -q` → 347 passed；完整 `uv run pytest tests/ -q` → 468 passed、5 warnings；`uv run pytest tests/ -v` → 468 passed、5 warnings。
- 临时探测（scratchpad 脚本，`PYTHONPATH=.`；只用 `tempfile` 目录和显式 `environ`，未读取 `.env`、未运行生成脚本写文件）：①在 Python 中调用 `regenerate()` 与 `docs/SCHEMAS.md` 比较 → 一致，`gold.market_daily.day` 行列出 `iso_date` 与 `day_start`；`RULE_FIELDS` 与 `_RULE_KEYS` 类型集合一致且字段键均为必填键子集。② `PipelineConfig`：`load()` 结果与同值重构对象 `==` 为 False、`effective_settings()["sha256"]` 相同；`model_copy`/`deepcopy`/`pickle` 保留来源；`model_dump`/`repr` 不含来源。③ adapter：合法外壳以 `MappingProxyType` 传入 → `NormalizationError("Cannot copy Bronze evidence…")`；同一极大数 `raw_payload` 以 dict 传入 → cause 为 `ContractError`，以只读代理传入 → cause 为 `TypeError`（复制失败）；误路由且含不可复制值、非映射输入、`str` 子类 venue → 均为 `NormalizationError` 而非 `AdapterRoutingError`。
- 残留引用：`rg _RULE_FIELDS|validation_rules|api_protocol_version`（排除本日志）仅命中 `CODE_READING_PROGRESS.md` 第 181、393、404 行的历史记录，B8 条目（第 183 行）已说明删除，可接受；代码与测试无残留。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| V1-1 | resolved | `generate_schema_docs.py:16,31` 改用 `contracts.RULE_FIELDS`（`contracts.py:31-55`，与校验器第 143-151 行共用）；`regenerate()` 结果与 `docs/SCHEMAS.md` 一致，`day` 行含 `day_start`；`test_generated_schema_tables_list_every_rule_on_each_referenced_field`（`test_data_schema.py:728`）逐规则逐字段检查。生成器带参数时退出且不写文件（`test_schema_generator_rejects_arguments_without_writing`，`ROOT` 指向 tmp）。 |
| V1-2 | resolved | `base.py:257-266` 在 `validate_record("bronze.raw")` 前比较身份（三项均为 `str`/`None` 时）；`test_routing_is_checked_before_content_and_time` 增加 `{not json`、`record_index=-1`；`test_malformed_identity_is_an_envelope_error_not_a_routing_error` 覆盖 `venue=1`、`api_version=b"1"`。路由仍在证据复制之后，见 B8-R1-4（suggestion）。 |
| V1-3 | resolved | `README.md:57`、`ADR-002:11`、`CHANGELOG.md:10` 写明立即失败（同进程亦然）、数据不变、调用方重试及初始化扫描成本；测试更名为 `test_held_lock_fails_immediately_and_preserves_partial`（`test_writer_recovery.py:50`），断言锁占用时 partial 仍在、释放后才迁入 recovery。 |
| V1-4 | resolved | `SCHEMA_REVIEW.md:30` 末句写明契约不交叉检查、由 adapter 保证。 |
| V1-5 / V1-S8 | resolved | `cli.py:17-23` 在 `check_configured_root()` 前以 INFO 输出 `config.effective`；`pipeline.py:149-174` 记录来源与值哈希；`logging_config.py:25-26` 输出 `details`。`test_check_logs_effective_settings_sources_and_hash` 断言无关 secret 不出现、字段集合仅四个；两份 config README 同步更新（规则 11），规则 12 的“来源和 hash”当前部分满足，run record 明确留 PR2。来源覆盖与相等语义见 B8-R1-5、B8-R1-6（suggestion）。 |
| V1-6 | resolved | `base.py:338` 抛 `AdapterOutputError`；`test_adapter_contract.py:268-271` 断言类型且非 `NormalizationError`。 |
| V1-7 | resolved（deferred by owner） | `PLAN.md:37` 标为移至 PR3 并注明负责人决定。 |
| V1-8 | resolved（owner decision） | 保持 `LOCK_NB`（`layout.py:95`），仅文档化；超时与扫描范围留 PR2，见 V1-3 证据。 |
| V1-S1 | resolved | `layout.py:402-470` 不再有仅 `raise` 的 `except`；`test_writer_preserves_temporary_file_on_publish_failure` 等仍通过。 |
| V1-S2 | resolved | `layout.py:184-188` 两键必填；重建说明（第 277-278 行）也写入；`test_recovery_metadata_requires_path_and_completion_check`（第 404 行）断言报错且 payload 与 sidecar 均未改动。 |
| V1-S3 | resolved | 代码与测试无 `api_protocol_version`。 |
| V1-S4 | not resolved | 代码按负责人同意删除了 `gc` 判断，但带来未披露的行为损失和一条失效测试，见 B8-R1-2、B8-R1-3。 |
| V1-S5 | resolved | 同 V1-1。 |
| V1-S6 | not adopted（accepted） | simplification 级别，不阻塞；交 Reporter。 |
| V1-S7 | resolved | `AdapterMetadata`（`base.py:145-156`）无 `validation_rules`；`PROJECT.md` §8、`ADR-002:43` 同步。但 `README.md:78` 字段数未同步，见 B8-R1-1。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B8-R1-1 | should-fix | `README.md:78`、`README.md:80` | 两处对外文档与 B8 后代码不一致：①第 78 行仍写 “ten metadata fields”，删除 `validation_rules` 后 `AdapterMetadata` 为 9 个字段（`base.py:147-156`）；②第 80 行仍写 “Read-only mapping proxies are copied only when their underlying mapping can be confirmed as a built-in dictionary”，S4 已删除该判断，`_copy_raw_record`（`base.py:67-68`）对所有非精确 `dict` 一律拒绝。 | 改为 9 个字段；第 80 行改为“只读映射代理一律不复制，保留原引用并标记 `evidence_is_snapshot=False`”，并与 B8-R1-3 的说明一致。 |
| B8-R1-2 | should-fix | `tests/test_adapter_contract.py:504-511`（`test_extreme_json_number_becomes_normalization_error_with_evidence`） | 该测试把外壳包成 `MappingProxyType` 传入。S4 后只读代理在 `_snapshot_or_error` 即失败，异常来自证据复制（cause `TypeError`，实测），不再走到极大 JSON 数解析；断言 `raw_record["raw_payload"] == …` 因 `raw_record` 就是代理本身而恒真。adapter 层“极大数字 → 带证据的 `NormalizationError`”失败路径因此不再被覆盖（`test_data_schema.py:174` 只测契约层）。这违反 `VALIDATOR.md` 第 7 项“简化不得削弱失败路径覆盖”。 | 改为传入 dict，断言 `isinstance(caught.value.__cause__, ContractError)`、`evidence_is_snapshot is True`；如需保留代理场景，另起测试断言复制失败。顺带检查其他以代理输入、只断言 `NormalizationError` 的测试是否同样被短路。 |
| B8-R1-3 | should-fix | `src/adapters/base.py:60-68,123-129,298`；`CHANGELOG.md:9`；`REVIEW_LOG.md` V1-S4 行 | S4 实际损失大于 Validator/Analyst 所述：此前可信只读代理包装的**合法** Bronze 外壳可被复制并规范化；现在任何 `MappingProxyType` 外壳（即使内容完全合法）都抛 `NormalizationError("Cannot copy Bronze evidence")`，会被当成数据错误送往 quarantine，而不是成功规范化。V1-S4 的“失去”一栏只写“只读代理输入可拿到独立副本”；CHANGELOG 只写“作为原引用证据保留”；无测试固定此行为（`test_readonly_mapping_evidence_is_original_reference_not_snapshot` 的 top_level 用例本身带重复键，非法）。负责人同意的是证据路径，未必知道合法输入也会被拒。 | 在 README/CHANGELOG/ADR-002 写明“规范化输入须为普通 `dict`；只读代理等其他映射即使内容合法也作为不可复制证据报错”；增加合法代理外壳被拒、且 `raw_record is` 原对象的测试；经 Reporter 告知负责人此行为损失（若不接受，再讨论调用方先 `dict()` 化等方案）。 |
| B8-R1-4 | suggestion | `src/adapters/base.py:257-266,298-299`；`ADR-002:43`；`CHANGELOG.md:9` | 路由比较位于证据复制之后。误路由外壳若含不可复制值（自定义类型、只读代理、`str` 子类身份），抛 `NormalizationError` 而非 `AdapterRoutingError`（实测），即 V1-2 所述“误路由记成本数据集数据错误”在该边缘情况仍存在。文档“在外壳校验和解析之前”字面正确，但未提复制在前。正常 Bronze 行为普通 dict，影响小。 | 文档补一句“先复制证据，再路由”；或在复制前对精确 `dict` 输入先做身份比较。 |
| B8-R1-5 | suggestion | `src/config/models/pipeline.py:109,149` | pydantic v2 的 `__eq__` 比较私有属性：值完全相同的 `load()` 对象与重构对象（来源 `direct`）`==` 为 False，而 `hash()` 与 `effective_settings()["sha256"]` 相同；`_sources` 是可变 dict，冻结模型下仍可被改写。当前无代码比较配置，非缺陷，但与“哈希只看值”的设计意图不一致，后续任务若比较配置会意外。 | 在 `README_FOR_DEVELOPER.md` 写明相等语义包含来源，或将 `_sources` 存为只读映射/在比较时排除；可加一条测试固定所选语义。 |
| B8-R1-6 | suggestion | `tests/test_cli_logging.py:46-75` | 来源标签只测了 `environment:DATA_ROOT`、`environment:DATA_MIN_FREE_GIB`、`default:runtime.json`、`default:src/config/defaults`、`environment:PIPELINE_LOG_LEVEL`、`direct`；`argument:config_dir`、`environment:PIPELINE_CONFIG_DIR`、`default:storage.json` 三个分支（`pipeline.py:151-157`）未断言。 | 参数化补齐三种来源（`config_dir` 指向 tmp 下复制的默认 JSON）。 |
| B8-R1-7 | suggestion | `src/config/models/pipeline.py:161-174`；`src/config/developing.md`（`serialization.py` 职责）；`README_FOR_DEVELOPER.md:32` | `developing.md` 把“脱敏稳定 JSON、config hash”分配给未来的 `serialization.py`，当前哈希实现在模型方法中。按规则 10 现在不建新文件是合理的，但 PR2 加 run record 时可能出现两套哈希实现。 | 在 `README_FOR_DEVELOPER.md` 注明 PR2 引入 `serialization.py` 时迁移并复用此哈希（或说明保留在模型的理由）。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B8-R1-1 | fixed | README 改为 nine metadata fields；只读代理说明改为一律不复制、合法代理也被拒并保留原引用，并写明先复制证据再路由。 |
| B8-R1-2 | fixed | 极大 JSON 数字测试改用普通 dict，断言原因为 `ContractError`、`evidence_is_snapshot is True`。其他代理输入测试（只读证据测试、deque 内代理、伪造映射）本意即测试不可复制路径，未被短路。 |
| B8-R1-3 | fixed（并报告负责人） | README、CHANGELOG、ADR-002 写明规范化输入须为普通 `dict`，合法只读代理外壳也会被拒为 `Cannot copy Bronze evidence` 并保留原引用；新增 `test_valid_readonly_envelope_is_rejected_and_kept_by_reference`（普通 dict 成功、代理被拒）。此行为损失由 Reporter 告知负责人。 |
| B8-R1-4 | fixed（文档，采纳） | README、ADR-002 写明“先复制证据，再路由”及其后果；不改代码以免在复制前读取不可信映射。 |
| B8-R1-5 | fixed（采纳） | `_sources` 改为只读 `MappingProxyType`；README_FOR_DEVELOPER 写明 `==` 包含来源、比较生效值用 sha256。 |
| B8-R1-6 | fixed（采纳） | 新增参数化测试 `test_effective_settings_record_config_dir_and_default_sources` 覆盖 `argument:config_dir`、`environment:PIPELINE_CONFIG_DIR`、默认目录及 `default:storage.json`。 |
| B8-R1-7 | fixed（文档，采纳） | README_FOR_DEVELOPER 注明 PR2 引入 `serialization.py` 时迁移并复用该哈希。 |

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 473 passed、5 warnings；`git diff --check` 通过。

- Round result: `changes requested`（B8-R1-1、B8-R1-2、B8-R1-3 为 should-fix；其余为 suggestion，不阻塞）。

## Block B8 · Validator 发现修复 · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，worktree, uncommitted。本轮改动：`README.md`、`CHANGELOG.md`、`docs/adr/ADR-002-pr1-foundation.md`、`src/config/models/pipeline.py`、`src/config/README_FOR_DEVELOPER.md`、`tests/test_adapter_contract.py`、`tests/test_cli_logging.py`；与 Analyst response 一致。Reviewer 为独立上下文，只读审查，唯一写操作为本节。
- Checks run by Reviewer（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；定向 `uv run pytest tests/test_cli_logging.py tests/test_adapter_contract.py -q` → 115 passed；完整 `uv run pytest tests/ -v` → 473 passed、5 warnings。
- 临时探测（scratchpad，`PYTHONPATH=.`，tempfile 目录与显式 `environ`，未读 `.env`）：对 `PipelineConfig.load()` 结果执行 `model_copy()`、`copy.copy` 成功；`model_copy(deep=True)`、`copy.deepcopy`、`pickle.dumps` 均抛 `TypeError: cannot pickle 'mappingproxy' object`。Round 1 同一探测脚本（`_sources` 为 dict 时）三者均成功。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B8-R1-1 | resolved | `README.md:78` 为 “nine metadata fields”，与 `AdapterMetadata` 9 个字段一致；`README.md:80` 改为只读代理一律不复制、合法代理也被拒并保留原引用。 |
| B8-R1-2 | resolved | `test_adapter_contract.py:505-513` 改用普通 dict，断言 `__cause__` 为 `ContractError`、`evidence_is_snapshot is True`。其余代理输入测试（只读证据、deque 内代理、伪造映射）本意即测不可复制路径，复核同意。 |
| B8-R1-3 | resolved | `README.md:80`、`CHANGELOG.md:9`、`ADR-002:43` 写明规范化输入须为普通 `dict`；`test_valid_readonly_envelope_is_rejected_and_kept_by_reference`（第 727-753 行）先证明同一 dict 规范化成功，再断言代理被拒、`raw_record is record`、非快照，trade 与 book 两条路径均覆盖。负责人告知由 Reporter 执行。 |
| B8-R1-4 | resolved | `README.md:80`、`CHANGELOG.md:9`、`ADR-002:43` 写明先复制证据再路由及其后果；不改代码的理由（避免复制前读取不可信映射）合理。 |
| B8-R1-5 | resolved（引入新问题） | `pipeline.py:110,150` 改为只读 `MappingProxyType`；`README_FOR_DEVELOPER.md:32` 写明 `==` 含来源、比较用 sha256。但该修改破坏了深拷贝与 pickle，见 B8-R2-1。 |
| B8-R1-6 | resolved | `test_effective_settings_record_config_dir_and_default_sources`（`test_cli_logging.py:107-124`）覆盖 `argument:config_dir`、`environment:PIPELINE_CONFIG_DIR`、默认目录与 `default:storage.json`。 |
| B8-R1-7 | resolved | `README_FOR_DEVELOPER.md:32` 注明 PR2 引入 `serialization.py` 时迁移并复用哈希。 |

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B8-R2-1 | should-fix | `src/config/models/pipeline.py:110,150` | B8-R1-5 的修复把 `_sources` 设为 `MappingProxyType`，而 `mappingproxy` 不可 pickle/deepcopy：`load()` 得到的 `PipelineConfig` 现在 `pickle.dumps`、`copy.deepcopy`、`model_copy(deep=True)` 均抛 `TypeError`（实测；Round 1 时三者都成功）。配置是不可变、准备在任务间传递的共享对象；macOS 默认 `spawn` 多进程、未来 `ExecutionConfig` 并发都需要 pickle 配置，届时会以与配置无关的错误失败。现有测试未覆盖，故绿灯未发现。 | 改用可 pickle 的只读表示，例如 `_sources` 存 `tuple[tuple[str, str], ...]` 或普通 dict，对外经属性/`effective_settings()` 只返回副本或代理；加测试断言 `load()` 结果可 `pickle` 往返、`deepcopy`，且来源与 sha256 保持不变。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B8-R2-1 | fixed | `_sources` 改为不可变、可 pickle 的 `(field, source)` 二元组 tuple，`effective_settings()` 转为 dict 查询；删除 `MappingProxyType` 导入。新增 `test_loaded_config_survives_pickle_and_deepcopy_with_sources`（pickle 往返、`copy.deepcopy`、`model_copy(deep=True)` 后来源、sha256 与相等性不变）。README_FOR_DEVELOPER 同步。 |

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 474 passed、5 warnings；`git diff --check` 通过。

- Round result: `changes requested`（B8-R2-1 为 should-fix）。

## Block B8 · Validator 发现修复 · Round 3 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，worktree, uncommitted。本轮改动：`src/config/models/pipeline.py`、`tests/test_cli_logging.py`、`src/config/README_FOR_DEVELOPER.md`；与 Analyst response 一致。Reviewer 为独立上下文，只读审查，唯一写操作为本节。
- Checks run by Reviewer（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；定向 `uv run pytest tests/test_cli_logging.py -q` → 12 passed；完整 `uv run pytest tests/ -v` → 474 passed、5 warnings。
- 临时探测（scratchpad `p4.py`，`PYTHONPATH=.`，tempfile 目录与显式 `environ`，未读 `.env`）：`load()` 结果的 `model_copy()`、`model_copy(deep=True)`、`copy.copy`、`copy.deepcopy`、`pickle` 往返均成功且来源不变。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| B8-R2-1 | resolved | `pipeline.py:110` `_sources` 为 `tuple[tuple[str, str], ...]`（默认 `()`），第 160 行由 dict 转元组，第 170 行查询时转 dict；无 `MappingProxyType` 残留。元组不可变且可 pickle（探测通过）。`test_loaded_config_survives_pickle_and_deepcopy_with_sources`（`test_cli_logging.py:127-135`）对三种克隆断言 `effective_settings()` 与 `==` 不变。`README_FOR_DEVELOPER.md:32` 同步说明。 |
| B8-R1-1 … B8-R1-7 | resolved | Round 2 已复核；本轮改动未触及相关文件，仍成立。 |

### New findings

无。审阅新 diff：来源顺序固定（字段登记顺序）且仅用于查表，不影响 sha256；`direct` 回退语义不变；无 secret 进入日志的新路径。

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |

- Round result: `converged`（B8 全部 must-fix/should-fix 已解决；Round 1 suggestion B8-R1-4…7 均已采纳。待 Reporter 报告——含 B8-R1-3 合法只读代理被拒的行为损失须告知负责人——后交 Validator 复查）。

## Validator · PR1 最终验证 · Round 2 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，完整未提交工作区（30 个已修改文件 + 11 个未跟踪文件，文件集合与 Round 1 相同）。本轮复查 Round 1 各发现在 B8 中的修复，以及 B8 是否引入新的跨块问题。只读审查，唯一写操作为本节；未运行生成脚本写文件，未读取 `.env`。
- Validator 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/ -q` 为 474 passed、5 warnings；`git diff --check` 通过。Analyst 自报的四项结果均复现。在 Python 中调用 `regenerate()` 与 `docs/SCHEMAS.md` 比较，结果一致；`gold.market_daily.day` 行同时列出 `iso_date` 和 `day_start`。
- 临时探测（scratchpad `r2.py`；tempfile 目录加显式 `environ`）：
  - 误路由外壳带非法 `raw_payload`、`record_index=-1`、无效字节或 `"[]"` 时，均抛 `AdapterRoutingError`；`venue=1` 抛 `NormalizationError`（外壳契约错误）。
  - 合法的普通 dict 外壳能规范化；同一内容包成 `MappingProxyType` 时，被拒为 `Cannot copy Bronze evidence`，`evidence_is_snapshot=False`。
  - `PipelineConfig.load()` 的结果经 pickle 往返后，来源、sha256 和 `==` 都不变。
  - `check` 输出一条 `config.effective` 事件，含 4 个字段的来源；环境中不相关的 secret 没有出现在输出中。`PIPELINE_LOG_LEVEL=warning` 时不输出该事件，这与 README 的说明一致。
- 残留引用：`src/`、`tests/`、`scripts/`、README、CHANGELOG、ADR、`agent/`、SCHEMAS、SCHEMA_REVIEW、PLAN、FOUNDATION_RULES 中，都没有 `validation_rules`、`api_protocol_version`、`_RULE_FIELDS`、`get_referents`、“ten metadata”的残留。

### Round 1 发现复查

| ID | Status | Evidence |
| --- | --- | --- |
| V1-1 / V1-S5 | resolved | `generate_schema_docs.py:16,31` 复用 `contracts.RULE_FIELDS`，已删除手写键列表；`test_generated_schema_tables_list_every_rule_on_each_referenced_field`（`test_data_schema.py:727`）逐条规则检查。生成器带参数时直接退出、不写文件（第 49-50 行；`test_data_schema.py:747`）。 |
| V1-2 | resolved | `base.py` `_payload` 在外壳校验前比较身份（三项均为 `str`/`None` 时）；实测见上。CHANGELOG:9、ADR-002:43 已写明身份字段形式非法时的处理，以及“先复制证据再路由”的边界。`test_malformed_identity_is_an_envelope_error_not_a_routing_error`（`test_adapter_contract.py:719`）。 |
| V1-3 / V1-8 | resolved（按负责人决定） | README:57、ADR-002、CHANGELOG:10 写明锁被占用时立即失败；测试已改名为 `test_held_lock_fails_immediately_and_preserves_partial`。等待超时和扫描范围留 PR2。 |
| V1-4 | resolved | SCHEMA_REVIEW 写明由 adapter 保证。 |
| V1-5 / V1-S8 | resolved（按负责人决定） | `cli.py:18-23`；`pipeline.py` `effective_settings()`；`logging_config.py:25-26`；两份 config README 同步更新。实测见上。 |
| V1-6 | resolved | 无效盘口数据集抛 `AdapterOutputError`。 |
| V1-7 | resolved（负责人决定移至 PR3） | `PLAN.md:37`。 |
| V1-S1 | resolved | `_write_locked` 中已没有仅 `raise` 的 `except`。 |
| V1-S2 | resolved（负责人同意） | `layout.py` 中 `recovery_path` 与 `completion_check` 改为必填，重建的说明也写入这两项；`test_recovery_metadata_requires_path_and_completion_check`（`test_writer_recovery.py:404`）。 |
| V1-S3 | resolved | 代码和测试中都没有残留。 |
| V1-S4 | resolved（负责人同意；行为损失已文档化） | `_copy_raw_record` 只复制精确的 `dict`。合法的只读代理外壳也会被拒，这一点已写入 README:80、CHANGELOG:9、ADR-002:43，并有测试 `test_valid_readonly_envelope_is_rejected_and_kept_by_reference`（`test_adapter_contract.py:728`）。“负责人已获告知”依据的是 coordinator 消息，Validator 未直接核实。 |
| V1-S6 | not adopted | 是 simplification，不阻塞。 |
| V1-S7 | resolved（负责人同意） | `AdapterMetadata` 共 9 个字段；`PROJECT.md` §8、ADR-002 和 README 字段数都已同步。 |
| B8-R1-1…B8-R2-1 | resolved | 抽查 B8-R1-2（极大数字测试改用 dict，原因断言为 `ContractError`）和 B8-R2-1（`_sources` 是二元组 tuple，可 pickle），均成立。 |

### New findings

| ID | Severity | 位置 | 问题 | 建议 |
| --- | --- | --- | --- | --- |
| V2-1 | suggestion | `src/cli.py:19-22`；`agent/AGENTS.md` 硬规则 10 | `config.effective` 按 INFO 级别输出；`PIPELINE_LOG_LEVEL` 为 WARNING 及以上时不会记录（README 已说明）。硬规则 10 要求任务启动时记录，且没有设条件。`check` 不是数据任务，所以当前不构成违规；首个数据任务实现时需决定该事件是否忽略日志级别。 | 留给 PR2 的 run record 实现时决定，或在 developing.md 规则 12 注明。 |
| V2-2 | suggestion | `src/config/models/pipeline.py`（`sources`） | 来源标签 `environment:*` 不区分进程环境和 `.env`。硬规则 10 只要求区分默认值和覆盖值，当前已满足；但排查“哪台机器的 `.env` 生效”时信息不足。 | 可选：后续区分 `process-environment:` / `env-file:`。 |

### Simplification（B8 新增或改动代码）

| ID | Severity | 位置 | 建议 | 依据 / 失去的行为 / 保护测试 / 风险 |
| --- | --- | --- | --- | --- |
| V2-S1 | simplification | `src/adapters/base.py` `_payload` 中的 `isinstance(raw, Mapping)` | `_payload` 只接收 `_copy_raw_record` 返回的精确 `dict` 快照，这个判断恒为真，可删除。 | 不会失去任何行为；路由相关测试保护；无风险。 |

审视后建议保留：`effective_settings()`（负责人决定）、`JsonFormatter` 的 `details`（只有一个使用方，但这是通用日志字段，代码很少）、生成器的参数拒绝（防止误写，有测试）、`_sources` 的 tuple 表示（为支持 pickle 所必需）。B8 删除的代码（S1–S4、S7）没有削弱失败路径或“无副作用”的覆盖：B8-R1-2 已恢复 adapter 层极大数字的失败路径测试。

### 未验证项

与 Round 1 相同：真实交易所及字段映射；外接盘、嵌套挂载、断电与 `F_FULLFSYNC`；大规模 `DATA_ROOT` 下的初始化扫描耗时与真实多进程并发；Python ≥ 3.10 下日期解析的宽松格式；依赖重新安装与重新 `uv lock`。负责人是否已收到 V1-S4 行为损失的告知，只依据 coordinator 消息。

### 结论

`ready for owner review`。Round 1 的 should-fix 均已在代码、测试和文档中核实修复，负责人决定的事项已落实；本轮没有 must-fix 或 should-fix，只有 V2-1、V2-2 两条 suggestion 和 V2-S1 一条 simplification，均不阻塞。本结论不表示批准合并；合并由负责人决定。

## Block B9 · 只读映射可规范化 · Round 1 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，worktree, uncommitted（41 个已修改/未跟踪条目）。B9 文件：`src/adapters/base.py`、`tests/test_adapter_contract.py`、`README.md`、`CHANGELOG.md`、`docs/adr/ADR-002-pr1-foundation.md`、`docs/pr1/CODE_READING_PROGRESS.md`。磁盘内容与修订包一致：`base.py:6` 导入 `gc`，`_require_trusted_mapping`（第 61-71 行）与 `_copy_raw_record`（第 74-115 行）恢复；两条只读证据测试（第 360、374 行）恢复；`test_valid_readonly_envelope_normalizes_like_a_dict`（第 735 行）替代被拒测试；`test_readonly_mapping_evidence_is_original_reference_not_snapshot` 已不存在。Reviewer 为独立上下文，只读审查，唯一写操作为本节；未运行生成脚本，未读取 `.env`。
- Checks run by Reviewer（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` → All checks passed；`uv run ruff format --check .` → 84 files already formatted；`git diff --check` → 通过；定向 `uv run pytest tests/test_adapter_contract.py -q` → 104 passed；完整 `uv run pytest tests/ -v` → 474 passed、5 warnings。
- 临时探测（scratchpad `b9.py`、`b9b.py`，`PYTHONPATH=.`，Python 3.9.6）：
  - 顶层合法代理：`normalize_trade(MappingProxyType(raw)) == normalize_trade(raw)`，盘口路径同样相等。
  - 嵌套代理：`_copy_raw_record(P({"x": P({"k": [1, P(...)]})}))` 各层均为 `dict`；代理自引用环与同一代理被两处引用时，副本分别保持环与共享身份。
  - 代理包装 `ForgedMapping`（伪造 `__getitem__`）、代理套代理、代理包装 `OrderedDict`：均为 `NormalizationError("Cannot copy Bronze evidence")`，`evidence_is_snapshot=False`，`raw_record is` 原代理。
  - 误路由代理 → `AdapterRoutingError`；`record_index=-1` 的代理 → cause `ContractError`、快照为 `dict`；代理内含 `object()` → 非快照、原引用、`evidence_copy_error_type="TypeError"`。
  - 代理底层 dict 含 `str` 子类键（自定义 `__hash__`）：`_copy_raw_record(proxy)` 调用该 `__hash__` 2 次后才拒绝；同一 dict 直接传入为 0 次；`proxy.copy()` 为 0 次。见 B9-R1-1。

### Previous findings

| ID | Status | Evidence |
| --- | --- | --- |
| V1-S4 / B8-R1-3 | superseded（负责人决定 2026-11-13 撤回 V1-S4） | 合法只读代理不再被拒：`base.py:64-70` 经 `gc.get_referents` 确认单一 referent 为精确 `dict` 后信任；`test_valid_readonly_envelope_normalizes_like_a_dict` 覆盖成交与盘口两条路径。B8-R1-3 要求的“合法代理被拒”文档已按新决定改写，见下。 |
| B3-L2-R2-2 | resolved（恢复后仍成立） | 包装自定义映射的代理仍在访问前拒绝：`test_untrusted_top_level_mapping_cannot_forge_provenance[readonly=True]`（第 469-484 行）断言原引用、非快照、底层 `run_id` 未变；探测结果同上。 |
| B8-R1-2 | resolved（未回退） | `test_extreme_json_number_becomes_normalization_error_with_evidence`（第 505 行起）仍用普通 dict 并断言 `ContractError` 与快照。 |

### 核对结果

- 失败路径测试仍在：路由（`test_routing_is_checked_before_content_and_time`、`test_malformed_identity_is_an_envelope_error_not_a_routing_error`）、契约错误（`test_readonly_mapping_failure_preserves_bronze_evidence`、`test_nested_readonly_mapping_in_invalid_envelope_retains_evidence`、`test_non_string_envelope_key_retains_evidence`）、不可复制值（`test_failed_evidence_copy_keeps_original_record_reference` 三种 kind、`test_untrusted_copy_hooks_cannot_forge_or_claim_independent_evidence`）。证据独立性：两条只读证据测试在异常后修改原 dict / 嵌套 dict，断言证据不变。
- 文档：`README.md:80`、`CHANGELOG.md:9`、`ADR-002:43` 均改为“底层确认为普通 dict 的只读代理按 dict 规范化，其他映射走原引用”；`rg` 检查 README、CHANGELOG、`docs/`（除本日志）、`agent/`、`src/`，未见“合法代理被拒”的现行说法。`CODE_READING_PROGRESS.md:184`（B8 收敛条目）与本日志 B8/Validator Round 2 的旧表述属历史记录，第 186 行已记录撤回，可接受。`SCHEMA_REVIEW.md`、`PLAN.md`、`docs/README.md` 无相关描述。

### New findings

| ID | Severity | Location | Finding | Suggested direction |
| --- | --- | --- | --- | --- |
| B9-R1-1 | suggestion | `src/adapters/base.py:82` | 顶层为可信代理时 `record = dict(raw)` 走通用映射合并路径（`keys()` + 逐键 `__getitem__` + 重新哈希），会在键类型校验（第 92-109 行）之前调用底层 dict 中 `str` 子类键的自定义 `__hash__`/`__eq__`（实测 2 次）；普通 dict 输入不会（0 次）。随后该键仍被拒，走原引用、非快照路径，所以不能伪造溯源，只是让不可信代码在校验前运行一次。 | 已确认 referent 为精确 `dict` 后，改用 `raw.copy()`（委托底层 `dict.copy()`，实测 0 次），与普通 dict 路径一致；可加一条测试断言该钩子未被调用。 |
| B9-R1-2 | suggestion | `README.md:80`、`docs/adr/ADR-002-pr1-foundation.md:43` | 修订包把“信任判断依赖 CPython `gc.get_referents`”列为已知限制，但对外文档未写。在其他实现上 `get_referents` 可能返回空列表，合法代理会退回原引用路径并报 `Cannot copy Bronze evidence`（安全但功能退化）；`pyproject.toml` 只约束 `requires-python >= 3.9`，未限定实现。 | 在 README 或 ADR-002 加一句：判断依赖 CPython，其他实现上只读代理按不可验证映射处理（fail closed）。 |
| B9-R1-3 | suggestion | `tests/test_adapter_contract.py:360-384` | 两条只读证据测试断言了内容独立，但未断言规范化后的类型：`raw_record == raw` 对代理与 dict 都成立；嵌套测试未断言 `evidence_is_snapshot is True`。若将来退回“代理按原样保存”的实现，外层断言仍可能通过。 | 补 `type(caught.value.raw_record) is dict`、嵌套层 `type(...) is dict`，嵌套测试补 `evidence_is_snapshot is True`。 |

### Analyst response

| ID | Action (fixed / disputed / deferred-to-owner) | Detail and checks |
| --- | --- | --- |
| B9-R1-1 | fixed（采纳） | `_copy_raw_record` 在信任确认后用 `raw.copy()` 代替 `dict(raw)`，不再在键类型检查前触发键的自定义 `__hash__`；新增 `test_trusted_proxy_copy_runs_no_key_hooks_before_rejecting_untrusted_keys`（钩子调用 0 次、证据为原引用非快照）。交 Validator 复核。 |
| B9-R1-2 | fixed（采纳） | README、ADR-002 写明信任判断依赖 CPython `gc.get_referents`，其他实现上合法代理安全退回原引用路径、无法规范化。 |
| B9-R1-3 | fixed（采纳） | 两条只读证据测试补充 `type(...) is dict`（含嵌套层）和 `evidence_is_snapshot is True` 断言。 |

- Analyst 检查（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 84 files already formatted；`uv run pytest tests/ -q` 475 passed、5 warnings；`git diff --check` 通过。

- Round result: `converged`（无 must-fix/should-fix；B9-R1-1…3 为 suggestion，交 Reporter。待 Reporter 报告后交 Validator 复查 V1-S4 的撤回）。

## Validator · PR1 最终验证 · Round 3 · 2026-11-13

- Revision：`codex/pr1-architecture` @ `76f1795`，完整未提交工作区（41 个已修改或未跟踪条目）。本轮复查：负责人撤回 V1-S4 后的 B9，以及 Analyst 在 B9 收敛后采纳、未经 Reviewer 复核的 B9-R1-1、B9-R1-2、B9-R1-3。只读审查，唯一写操作为本节；未运行生成脚本，未读取 `.env`。
- Validator 独立检查（均设置 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 为 84 files already formatted；`uv run pytest tests/ -q` 为 475 passed、5 warnings；`git diff --check` 通过。Analyst 自报的四项结果均复现。
- 临时探测（scratchpad `r3.py`、`r3b.py`，Python 3.9 / CPython）：
  - 合法代理与普通 dict 结果相同：`normalize_trade(MappingProxyType(raw)) == normalize_trade(raw)`。
  - 复制独立：`_copy_raw_record(MappingProxyType(src))` 返回 `dict`，之后修改 `src` 不影响副本。
  - 不可信代理不能伪造溯源：代理包装伪造 `run_id` 的自定义 Mapping、dict 子类、`OrderedDict`，以及代理套代理，都抛 `NormalizationError("Cannot copy Bronze evidence")`，`evidence_is_snapshot=False`，`raw_record is` 原代理，均未产出 Silver 行。
  - 键钩子：顶层 dict 和顶层可信代理中含 `str` 子类键（自定义 `__hash__`/`__eq__`）时，规范化期间钩子调用均为 0 次，走原引用、非快照路径；嵌套可信代理中的同类键也是 0 次。
  - 路由：误路由的代理外壳抛 `AdapterRoutingError`。

### 复查结果

| ID | Status | Evidence |
| --- | --- | --- |
| V1-S4 撤回 / B9 | resolved | `base.py` 恢复 `_require_trusted_mapping`：只有当 `gc.get_referents` 显示单一 referent 且为精确 `dict` 时才信任。嵌套代理以 memo 预置副本，结果各层均为 `dict`。实测见上。 |
| B9-R1-1 | resolved | 信任确认后改用 `raw.copy()`，钩子调用 0 次（实测）；`test_trusted_proxy_copy_runs_no_key_hooks_before_rejecting_untrusted_keys` 断言 `calls == []`、原引用、非快照。 |
| B9-R1-2 | resolved | README:80、ADR-002:43 写明依赖 CPython `gc.get_referents`；在其他实现上，合法代理会退回原引用路径（fail closed）。 |
| B9-R1-3 | resolved | `test_readonly_mapping_failure_preserves_bronze_evidence`、`test_nested_readonly_mapping_in_invalid_envelope_retains_evidence` 补充了 `type(...) is dict`（含嵌套层）和 `evidence_is_snapshot is True`，并保留“修改原对象后证据不变”的断言。 |
| 失败路径覆盖 | 完整 | 现有测试覆盖：路由（含非法内容与身份）、契约错误、不可复制值（deque 内代理、深列表、不可复制对象）、复制钩子伪造、不可信顶层映射（dict / 代理两种形态）、极大数字（普通 dict）、合法代理与 dict 等价（成交与盘口两条路径）。 |
| 文档一致性 | 一致 | README:80、CHANGELOG:9、ADR-002:43、`CODE_READING_PROGRESS.md:186` 均为“底层是普通 dict 的只读代理按 dict 规范化，其他映射保留原引用”。B8、Round 2 的旧表述只保留在历史记录中，第 186 行已记录撤回。 |
| 跨块 | 无新问题 | 只改动 `_copy_raw_record`、`_require_trusted_mapping` 和测试；路由、外壳契约、溯源校验、config、写入层均未受影响。 |

### New findings

无 must-fix、should-fix 或 suggestion。

### Simplification / owner-question（负责人确认的行为，只列问题）

| ID | Severity | 位置 | 问题 |
| --- | --- | --- | --- |
| V3-Q1 | owner-question | `src/adapters/base.py` `_require_trusted_mapping`、`_copy_raw_record` 中的代理分支 | 恢复的代理信任路径约 25 行，依赖 CPython 的 `gc.get_referents`，并且依赖 `dict.copy()` 不重新哈希键（同为 CPython 实现细节，已有测试固定）。这是负责人确认的行为，因此不建议删除。如果未来调度器始终从 Parquet 或 JSON 构造普通 `dict`，代理支持的实际收益有限；保留与否请负责人在 PR2 调度器设计时再确认。 |
| V2-S1 | simplification（沿用） | `src/adapters/base.py` `_payload` | `isinstance(raw, Mapping)` 仍恒为真（输入总是复制后的 dict），可删除，没有行为损失。 |

### 未验证项

非 CPython 实现（PyPy 等）下的实际行为（只有文档说明会 fail closed，未实测）；其余与 Round 1、Round 2 相同：真实交易所、外接盘与断电、大规模扫描与并发、Python ≥ 3.10 的日期解析、依赖重新安装。

### 结论

`ready for owner review`。V1-S4 的撤回和 B9 的三条 suggestion 均已核实，没有引入新的跨块问题。本结论不表示批准合并；合并由负责人决定。
