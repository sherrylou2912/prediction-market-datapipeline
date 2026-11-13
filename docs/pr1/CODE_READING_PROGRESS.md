# PR1 代码阅读进度与待办

按文件逐个讨论；“已阅”表示负责人已讨论并确认阅读进度，不代表代码已通过独立审查或批准合并。文件之后发生变化时，应重新确认变化部分。

本文件结构：

1. 阅读状态
2. Analyst 实施清单（按依赖顺序）
3. 实施中需要负责人确认的事项
4. 待办详情（PR1 实施）
5. 未来设计要求（不在 PR1 实施）

## 1. 阅读状态

PR1 改动的代码和文档已全部读完（2026-11-09）。

阅读结束后按负责人要求整理了 Markdown 文档结构（2026-11-09）：本文件从 `inprocessfile/` 移到 `docs/pr1/`；`docs/PR1_FOUNDATION_RULES.md` → `docs/pr1/FOUNDATION_RULES.md`；`planner/PR1_PLAN.md` → `docs/pr1/PLAN.md`；`docs/ADR-001-v1-architecture.md` → `docs/adr/`；`docs/ANALYSIS.md` → `docs/legacy/`；旧验收报告 `inprocessfile/PR1_Architecture_Review.md` 归档到 `docs/pr1/archive/ARCHITECTURE_REVIEW_2026-10-14.md`；新增文档索引 `docs/README.md`；四个角色文件中重复的确认关口改为引用 `agent/AGENTS.md`。下表和下文中的行号均指阅读时的版本。

| 文件 | 状态 | 日期 | 阅读范围和结论 |
| --- | --- | --- | --- |
| `src/__main__.py` | 已阅；待 Analyst 修改 | 2026-11-04 | 已讨论 `python -m src` 入口、调用 `src.cli.main()` 和进程退出。阅读后新增的注释和空行导致 lint 失败，见 §4.13。 |
| `src/cli.py` | 已阅；待 Analyst 修改 | 2026-11-04 | 已讨论 `check` 命令和未来统一入口，见 §4.5；阅读后新增的注释和空行导致 lint 失败，见 §4.13。 |
| `src/config/__init__.py` | 已阅 | 2026-11-04 | 已讨论配置模块的公共入口，以及 `ConfigError`、`PipelineConfig` 和内部辅助函数的区别。 |
| `src/config/errors.py` | 已阅 | 2026-11-08 | 已讨论 `ConfigError` 的继承关系、主动抛出与捕获，以及异常和日志的区别。 |
| `src/config/loader.py` | 已阅；待 Analyst 修改和补测试 | 2026-11-09 | 已讨论 `PipelineConfig.load` 的调用流程、`load_environment` 的文件选择与覆盖优先级、`load_json_setting` 的四层检查及现有间接测试；运行相关 10 个测试均通过。决定：`.env` 只存放敏感信息和机器级全局设置，每台机器使用同一个文件，任务参数放在配置 JSON，因此不增加 `--env-file` 或指定 `.env` 路径的环境变量。见 §4.1、§4.2。 |
| `src/config/models/pipeline.py` | 已阅；待 Analyst 修改和补测试 | 2026-11-09 | 已讨论字段来源与优先级、`load()` 流程、`__post_init__` 统一校验、三个 `_parse_*` 辅助函数，以及 preflight（`_nearest_existing_directory`、`check_configured_root`、`validate_for_read`、`validate_for_write`）和对应测试；相关 32 个测试均通过。决定：改用 pydantic，删除 `from_env()`，写检查失败时清理新建目录。见 §4.1–§4.4。 |
| `src/config/models/__init__.py` | 已阅 | 2026-11-09 | 只导出 `PipelineConfig`；导出链为 `src/config/__init__.py` → `models/__init__.py` → `models/pipeline.py`。新增 model 时在此导出，外部需要时再加入 `src/config/__init__.py`。 |
| `src/config/README.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 与当前代码一致；L27 漏写 `config_dir` 参数优先级。需随 pydantic、环境覆盖范围、写检查清理等决定更新，见 §4.1。 |
| `src/config/README_FOR_DEVELOPER.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 与当前代码一致；L35 “loader 只读取”与当前 `load_json_setting` 不符。需随 pydantic 和环境覆盖范围更新，见 §4.1。 |
| `src/config/developing.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 目标结构、配置流和 12 条强制规则；讲解见 Claude Doc《Config 整体设计讲解》。需在“强制规则”中补充 pydantic 和环境覆盖范围，见 §4.1。 |
| `src/data_io/__init__.py` | 已阅 | 2026-11-09 | 只有包说明文字，无导出、无逻辑。 |
| `src/data_io/layout.py` | 已阅；待 Analyst 修改和补测试 | 2026-11-09 | 已讨论 `WriterRole` 与 6 个层级、`DataLayout.create`、`writer`、`ScopedWriter.write_new` 的 8 步流程（越界检查、软链接防护、临时文件 + `fsync` + `os.link` 不覆盖发布），以及断电和 `fsync` 语义；相关 12 个测试均通过。决定：外接硬盘支持、父目录 `fsync`、统一异常、新增 `recovery/` 区保留冲突和 partial 数据、使用锁文件。见 §4.7。 |
| `src/data_schema/`（`contracts.py`、`schema_registry.json`、`__init__.py`） | 已阅；待 Analyst 修改和补测试 | 2026-11-09 | 已讨论 registry 的 13 个数据集与 6 种字段类型、`get_contract`、`arrow_schema`、`validate_record` 的四步校验，以及直接测试和通过 mock adapter 的间接覆盖；按 schema/contract/adapter 筛选的 29 个测试均通过。决定：行级硬规则放进 contract、跨行跨文件规则留给 PR4；schema、范围规则和行内规则全部用 JSON 声明；`get_contract` 不暴露全局字典；UTC 严格要求 `timezone.utc`；registry 自检；新增 `gold.market_1m`；point-in-time 改用可用时间、检查分两层。见 §4.8。 |
| `src/adapters/`（`base.py`、`mock.py`、`__init__.py`） | 已阅；待 Analyst 修改和补测试 | 2026-11-09 | 已讨论 `Page`、`AdapterMetadata` 的 8 项声明、`VenueAdapter` 的抽象方法、mock 的读取与规范化链路，以及直接和间接测试；`-k adapter` 筛选的 9 个测试均通过。决定（全部在 PR1 实施）：统一规范化错误、溯源信息来自 Bronze 外壳、盘口事件标明数据集、补齐 Silver 规范化方法、加强声明校验、基类统一检查时间范围、mock 支持分页。见 §4.9。 |
| CLI 测试（`tests/test_pipeline_foundation.py` L611、L636）与 `tests/conftest.py` | 已阅；待 Analyst 修改和补测试 | 2026-11-09 | L611 直接测试 `check` 不探测写入、不创建目录；L636 用新进程测试 `python -m src check`；`-k "cli or entry_point"` 筛选的 3 个测试均通过。`conftest.py` 不在 PR1 改动中，只服务旧 analysis 测试。决定：L636 显式设置全部 pipeline 变量；按 `log_level` 配置结构化日志；未知命令返回退出码。见 §4.2、§4.5、§4.6。 |
| `docs/SCHEMAS.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 已讨论四部分结构、L397 测试如何保证文档与 registry 一致（单独运行 1 passed），并逐条对照 `contracts.py`。决定：JSON 为唯一事实来源，文档由脚本生成；修正过时文字；每个字段加 `description`；N 和窗口长度作为数据参数单独存放；存储格式标注为计划。见 §4.10。 |
| `docs/pr1/FOUNDATION_RULES.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 已对照 9 节规则与现有代码。决定：point-in-time 改用可用时间、检查分两层；PR1 补 `gold.market_1m` contract；Bronze 路径包含接收身份；更新过时文字；更新 `docs/pr1/PLAN.md` 状态。见 §4.11、§4.15。 |
| `docs/adr/ADR-001-v1-architecture.md`（阅读时位于 `docs/`） | 已阅；待 Analyst 修改 | 2026-11-09 | 已讨论背景、6 条决定、理由和后果，并与代码、PROJECT.md 对照（引用章节、PR2 账本、duckdb 依赖、先查空间再建目录均一致）。决定：新建 ADR 目录，保留 ADR-001 原文，新建 ADR-002；日志采用结构化格式。见 §4.12。 |
| `README.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 已按 README 实际运行安装、测试、lint 和格式检查（pytest 189 passed；ruff check 7 个错误、ruff format 需重排），并与代码、默认值、依赖核对。决定：保留两条中文笔记并修成正式注释；按各项决定同步更新 README；补全启动错误表；改写上游联系方式。见 §4.13。 |
| `CHANGELOG.md` | 已阅；待 Analyst 修改 | 2026-11-09 | 已逐条对照代码。决定：全部待办实施后，按最终结果重写 `Unreleased`；改正 “directory permissions” 和 “threat model” 的不准确措辞。见 §4.14。 |

## 2. Analyst 实施清单（按依赖顺序）

负责人于 2026-11-09 授权连续实施清单，无需逐块等待确认；实施时记录变更与决策，完成后由负责人重新 review。按依赖关系安排工作，每块更新受影响的测试和文档；交付前运行 `uv run ruff check .`、`uv run ruff format --check .`、`uv run pytest tests/ -v`。

**第 0 块：恢复检查通过**

- [x] 修复 lint 和格式，保留两条中文笔记（§4.13 第 1 条）。

**第 1 块：配置**（其他块依赖它的 pydantic 写法、`validation.py` 和日志）

- [x] 新增 pydantic 依赖；`PipelineConfig` 改用 pydantic，建立 `src/config/validation.py`，`ValidationError` 统一转为 `ConfigError`（§4.1）。
- [x] loader 收窄为通用 JSON 对象读取，字段和类型校验移入 model（§4.1）。
- [x] 删除 `from_env()`（§4.4）。
- [x] 写检查失败时只清理本次新建的目录（§4.3）。
- [x] 补齐配置加载与 preflight 测试 1–7（§4.2）。
- [x] 更新 `src/config/` 三份文档（§4.1 “文档”）。

**第 2 块：CLI 与日志**

- [x] 按 `log_level` 配置结构化 JSON 日志（§4.6）。
- [x] `src/cli.py` 改为统一命令入口；未知命令返回退出码（§4.5）。
- [x] 修改 L636 测试的环境隔离，补 CLI 测试 8–9（§4.2）。

**第 3 块：写入层**（依赖第 2 块的日志）

- [x] 统一异常为 `WriteBoundaryError`；发布后父目录 `fsync`（§4.7 第 2、3 条）。
- [x] 外接硬盘：硬链接检测、“卷未挂载”报错（§4.7 第 1 条）。
- [x] `recovery/` 区、锁文件、冲突与残留 partial 处理；Bronze 路径包含接收身份（§4.7 第 4 条）。
- [x] 补充 layout 测试（§4.7 第 4、5 条）。

**第 4 块：数据契约**

- [x] 设计规则的 JSON 声明格式，把 schema、范围规则、行内规则迁入 JSON；`contracts.py` 只读取并执行（§4.8 第 2 条）。
- [x] 每个字段加 `description`；registry 自检（§4.8 第 5 条、§4.10 第 3 条）。
- [x] `get_contract()` 只读；UTC 严格要求 `timezone.utc`（§4.8 第 3、4 条）。
- [x] 新增行级硬规则（§4.8 第 1 条）。
- [x] point-in-time 改用 `max_feature_available_at`，第一层检查（§4.8 第 7 条）。
- [x] 新增 `gold.market_1m` contract（§4.8 第 6 条）。
- [x] 按版本政策处理 `schema_version`（§4.10 第 2 条 L8）。
- [x] `docs/SCHEMAS.md` 改为脚本生成，修改 L397 测试（§4.10）。
- [x] 补齐 data_schema 测试（§4.8 测试要求）。

**第 5 块：adapter**（依赖第 3 块的 Bronze 路径设计和第 4 块的契约）

- [x] 实施“API 数据 → `bronze.raw` → 规范化”的溯源方案，具体选择记录在下方，待负责人复核（§4.9 第 2 条）。
- [x] 统一规范化错误；盘口事件标明数据集；补齐 4 个 Silver 规范化方法（§4.9 第 1、3、4 条）。
- [x] 加强 `AdapterMetadata` 校验；基类统一检查时间范围；mock 支持分页（§4.9 第 5–7 条）。
- [x] 补齐 adapter 测试（§4.9 测试要求）。

**第 6 块：项目文档收尾**（依赖前面所有块的最终结果）

- [x] `agent/PROJECT.md`：§5 增加 `recovery/`，§8 更新 adapter 接口列表（§4.7、§4.9）。
- [x] `docs/pr1/FOUNDATION_RULES.md` 7 处修改（§4.11）。
- [x] 建立 `docs/adr/` 并移入 ADR-001（2026-11-09 文档整理时完成）。
- [x] ADR-001 开头注明由 ADR-002 补充；新建 ADR-002，并登记到 `docs/README.md`（§4.12）。
- [x] `README.md` 同步更新、补全启动错误表、改写上游联系方式，并与 `src/config/README.md` 去重（§4.13 第 2–5 条）。
- [x] 更新 `docs/pr1/PLAN.md` 状态（§4.15）。
- [x] 最后重写 `CHANGELOG.md`（§4.14）。

**第 7 块：讲解与验证**

- [x] 编写 [schema 与规则逐项复审指南](SCHEMA_REVIEW.md)，供负责人 review 时逐项讲解（§4.8 第 2 条）。
- [x] Validator 独立审查当前工作区并复核发现的问题；结论为可交负责人复核，不代表批准合并或生产运行。

### 实施记录（2026-11-09，供负责人复核）

- 配置采用 pydantic 2；环境整数只接受 ASCII 十进制数字（允许首尾空白），重复 JSON 和 `.env` 键报错，显式 `environ` 不引用真实进程环境。写预检拒绝不支持硬链接的卷；macOS 上 `/Volumes/<卷名>` 必须存在、不是软链接且为挂载点，并检查路径大小写与软链接别名。卷内更深的软链接可能指向其他卷；卷格式尚未实测，未增加替代发布方式。
- 写入使用单机协作锁，Bronze 路径中的 `receipt_id` 标识一次接收；同一身份同一目标的相同字节是重试，冲突和中断 partial 保存在 recovery。发布同步文件和父目录；macOS 若明确不支持 `F_FULLFSYNC` 则警告并退回 `fsync`，实际硬件断电行为仍需验证。
- 契约版本为 `3.0.0`。规则变化均升级版本；兼容新增升级次版本，不兼容变更升级主版本。状态取 `pending/open/closed/settled/cancelled/unknown`，盘口方向取 `bid/ask`，taker 方向取 `buy/sell`；标签可用时间严格晚于观察时间。分钟盘口档位以 JSON 字符串映射正整数序号到十进制字符串，Arrow 存为 string；字段、每条规则及边界见 [复审指南](SCHEMA_REVIEW.md)。
- 采集返回来源记录；未来调度器先包装、校验、保存 Bronze 外壳，之后调用规范化。adapter 根据外壳的 venue 与 API/协议版本检查路由，从外壳取得 run ID、记录序号和系统接收时间；规范化错误保留外壳，代码错误和错误路由分别上报。盘口方法返回数据集名和行。能力集合及主键与 `AdapterMetadata` 一致；时间范围使用严格 UTC 的 `[start, end)`，不允许起止相等。mock 游标绑定查询范围和方法。
- 检查（使用 `UV_CACHE_DIR=/private/tmp/prediction-market-uv-cache`）：`uv run --locked ruff check .`、`uv run --locked ruff format --check .` 均通过；`uv run --locked pytest tests/ -v` 为 299 passed、5 warnings；`git diff --check` 通过。独立 Validator 重跑三项命令得到相同结果，并复核了契约、写入恢复、adapter 和配置的已发现问题。
- 真实交易所、外接卷、断电恢复、PostgreSQL 账本、manifest 与 checkpoint 的原子一致性、训练和回测阶段的第二层 point-in-time 检查均未在 PR1 实现或实测。原 [PR1 计划](PLAN.md)的旧代码逐项迁移清单仍待核对，不属于本代码阅读清单的本次修复范围。

### 实施后复审记录（2026-11-11）

- 第 0 块已核对并向负责人报告；负责人于 2026-11-11 确认按清单顺序继续：两处中文笔记保留并整理格式，清除空白问题，测试文件中的函数签名已按格式调整。`src/cli.py` 的行为变更留第 2 块复审；未发现本块需要决定的问题。
- 本次使用现有环境运行（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：`uv run ruff check .` 通过；`uv run ruff format --check .` 显示 84 个文件格式正确；`uv run pytest tests/ -v` 为 299 passed、5 warnings。首次使用默认缓存运行三项命令均因沙箱不允许访问缓存而失败，改用临时缓存后通过；未验证依赖重新安装。
- 第 1 块已对照清单和代码、测试、文档；以下待办尚未修改代码。`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_config.py -q`：33 passed；同环境下 `uv run pytest tests/test_config.py tests/test_pipeline_foundation.py -k 'config or environment or preflight or root or write_check or volume' -q`：63 passed、46 deselected。使用 `DATA_ROOT=/private/tmp` 运行 `uv run python -m src check` 成功。
  1. **待办（负责人确认，2026-11-11；尚未实施）**：`src/config/validation.py` 的 `ConfigError` 保留 pydantic 异常链；实际以非敏感示例验证，普通错误消息不含输入，但完整 traceback 包含输入。当前 CLI 只打印普通错误消息；调用方记录完整堆栈时存在泄露误传敏感值的风险。保留可读字段和错误原因，对完整异常输出脱敏，并补充完整堆栈测试。
  2. **待办（负责人确认，2026-11-11；尚未实施）**：`tests/test_config.py::test_missing_volume_fails_before_disk_probe` 预期 macOS 专有检查但未模拟 macOS。实际模拟 Linux 并阻断磁盘探测，观察到到达磁盘探测而非报未挂载。在该测试中显式模拟 macOS，验证未挂载时不探测磁盘；不因此改变生产代码的平台行为。
  3. **待办（负责人确认，2026-11-11；尚未实施）**：`src/config/README_FOR_DEVELOPER.md` 将 `load()` 描述为“不探测磁盘”易误解：它读取 JSON 和可能的 `.env`，只是不会检查容量或试写。将该句改为明确说明不会检查容量、试写或创建目录。
- 负责人于 2026-11-11 确认上述三项记录为待办，并同意继续第 2 块 CLI 与日志复审。
- 第 2 块已对照清单、代码、测试和 ADR；以下待办尚未修改代码。`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_cli_logging.py tests/test_pipeline_foundation.py -k 'cli or entry_point or logging' -q`：7 passed、73 deselected。实际在 `check_configured_root` 测试替身中发 DEBUG 日志：配置 INFO 时无该日志，配置 DEBUG 时出现 JSON 日志。
  1. **待办（负责人确认，2026-11-11；尚未实施）**：子进程入口测试覆盖四个 pipeline 环境变量，但会先解析本机 `.env`。在临时隔离的包副本中设置重复的无关 `.env` 键并显式覆盖四个变量，实际命令返回 2；未满足 §4.2 第 8 条中测试不受本机 `.env` 影响的目标。隔离测试的默认环境文件并补充该场景测试，保持正常运行读取本机 `.env` 的行为。
  2. **待办（负责人确认，2026-11-11；尚未实施）**：`JsonFormatter` 无显式 `event` 时退回 logger 名。实际触发相同写入重试，得到 `event=src.data_io.layout`；其他该模块日志也未声明事件名，因此无法仅凭 event 区分重试和恢复等动作。为实际日志动作提供稳定、可区分的事件名并测试；补充 CLI 从配置传入级别的自动化联动测试。
  3. **待办（负责人确认，2026-11-11；尚未实施）**：§4.5 要求非执行性的未来命令接入示例；`src/cli.py` 目前只有泛化注释，没有展示命令与任务函数如何对应。增加简短示例注释，不创建未来命令或空模块。
- 负责人于 2026-11-11 确认第 2 块上述三项记录为待办，并同意继续第 3 块写入层复审。
- 第 3 块已对照 §4.7、代码、测试与文档；以下发现待负责人决定，尚未修改代码。本次 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_writer_recovery.py -q`：9 passed；同环境下运行 `uv run pytest tests/test_writer_recovery.py tests/test_pipeline_foundation.py -k 'writer or layout or scoped or recovery' -q`：21 passed、64 deselected。以下均在临时目录中验证，没有模拟真实断电或测试真实外接盘。
  1. `receipt_id` 只需出现在 Bronze 路径的任意目录段；实际用同一路径 `bronze/receipt-A/receipt-B/record` 和两个不同接收身份写入相同字节，两次均成功但只产生一份文件，与 FOUNDATION_RULES §3 每次接收均留证的要求不一致。建议规定身份的固定路径位置并校验，补充此反例及独立接收测试；具体路径约定待负责人决定。
  2. 写预检新建 `DATA_ROOT` 和祖先目录时没有同步其各自的父目录。实际跟踪预检及后续布局和文件写入：根目录内部被同步，但新建根目录和祖先的父目录未被同步。断电可能丢失目录项；建议补齐父目录同步及调用顺序/失败路径测试，真实设备行为另验。
  3. 恢复遗留 partial 时计算 checksum 并同步目录，但没有对该文件本身执行同步。实际按 inode 跟踪 `_sync_file`：partial 被恢复，但其 inode 未被同步；若原写入在文件同步前中断，后续断电存在持久性风险。建议恢复发布前同步文件并测试同步失败时证据保留。
  4. 故障注入：恢复说明 JSON 发布后、payload rename 前失败，partial 保留；再次恢复后有两份 JSON、仅一份 bin，留下未标记的孤立说明。建议明确未完成状态或可核对方式，保留证据并测试该中断窗口。
  5. 目标路径含 NUL 字符时，实际先写出 partial，再抛原始 `ValueError`；建议创建 partial 前拒绝该路径，统一报告 `WriteBoundaryError` 并测试无写入副作用。
- **第 3 块待办（负责人确认，2026-11-11；尚未实施）**：上述 1–5 项均同意实施。① Bronze 接收身份固定为文件直接父目录，校验传入身份与该目录一致，并补充同一路径包含两个身份及独立接收测试；同步更新 README 和 FOUNDATION_RULES 中的路径约定。② 新建 `DATA_ROOT` 及祖先目录时同步各自父目录，测试同步顺序和失败。③ 恢复遗留 partial 发布前同步文件，测试同步失败时证据保留。④ 为仅有说明但未成功移动数据的恢复记录提供明确状态或可核对方式，保留证据并测试中断窗口。⑤ 写入前拒绝包含 NUL 的目标路径，以 `WriteBoundaryError` 报错并测试无文件副作用。负责人同意继续第 4 块数据契约复审。
- 第 4 块先复审契约执行机制，数据集字段和规则仍需按 Bronze、Silver、Gold 逐项讲解。`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_data_schema.py -q`：27 passed；同环境运行 `uv run pytest tests/test_data_schema.py tests/test_pipeline_foundation.py -k 'schema or contract or training or gold or silver or bronze' -q`：49 passed、54 deselected。以下发现待负责人决定，尚未修改代码：
  1. `_check_rule` 的 `difference` 直接使用调用方的 Decimal context。实际以 bid=0.1234567890、ask=0.8765432109、spread=0.75 验证，精度 28 时拒绝，精度 2 时错误接受；建议进行与调用环境无关的精确差值校验并测低精度与异常陷阱。
  2. registry 使用普通 `json.loads`，实际在临时文本中重复声明顶层 version 为 3.0.0 和 9.9.9，自检通过且后者覆盖前者；当前文件未发现重复。建议加载时拒绝任意层重复键并测试。
  3. 实际从 registry 的内存副本删除 bronze.raw 的 version 规则，`validate_registry` 仍通过；当前 14 个数据集都有 version 规则。建议自检防止版本规则遗漏，并保持执行器不硬编码数据集或字段名的设计；待负责人决定具体实现。
  4. 实际将 `silver.markets.title` 设置为无法 UTF-8 编码的孤立 Unicode 代理码点：`validate_record` 接受，但转为 Arrow 字符串时抛出 `UnicodeEncodeError`。建议在契约边界拒绝无法编码的字符串并补测试；Bronze 原始证据保留方式须单独考虑。
  5. Python 实际验证 `timezone(timedelta(0)) is timezone.utc`；无法按此前想法仅凭对象区分二者构造方式。现实现按 tzinfo 对象身份严格接受 timezone.utc 并拒绝 ZoneInfo UTC/伦敦冬季，待负责人确认此限制。
- **第 4 块执行机制待办（负责人确认，2026-11-11；尚未实施）**：① 使用不受调用方 Decimal 精度和异常设置影响的精确差值检查，补充低精度及异常设置测试。② registry 加载时拒绝任意层重复 JSON 键并补测试。③ 自检防止数据集遗漏版本校验，保持执行器不硬编码具体数据集名，并补测试。④ 在需要作为 Arrow 字符串保存的字段边界拒绝无法 UTF-8 编码的值并补测试；Bronze 原始证据的保留方式在 Bronze 复审时单独讨论。⑤ 接受 `tzinfo is timezone.utc` 对象身份规则及 `timezone(timedelta(0))` 与其不可区分的语言限制；在文档保留说明并以测试验证。负责人同意继续逐项复审 Bronze 数据集。
- Bronze `bronze.raw` 已进行代码、测试和文档初核，尚未向负责人逐字段讲解及确认设计：HEAD 的 v2 与工作区 v3 对照显示，14 个字段的类型、可空性及 `(run_id, record_index)` 主键不变；本次新增字段说明、规则 JSON 声明和严格 UTC，并将共用版本升级至 3.0.0。本次指定 6 项 Bronze/adapter 测试（含参数化）为 7 passed；相关名称筛选为 10 passed、122 deselected。实际验证 `venue=None`、`api_version=None` 和非法原始 JSON 均被契约拒绝，重复键 JSON 被接受；当前只保留在 mock 规范化异常中的证据不等于已经落盘或进入 quarantine。需对照 PROJECT.md §6、§8 继续讨论非 venue 来源、不适用 API 版本和无法解析的原始字节如何持久保留；目前无真实 collector 或调度器，不声称已有数据丢失。`ingested_at` 早于 `received_at` 也被接受，时间异常的处理策略待讨论。
- 负责人于 2026-11-11 指示先审核并修复目前已确认的待办，再由独立 Validator 审查并记录发现，之后修复一轮，再继续逐项阅读；Bronze 上述尚未确认的设计选择暂保留为开放事项。
- **首轮 Analyst 实施记录（2026-11-11）**：上文标注“尚未实施”的第 1–4 块已确认事项现均已完成初次修改，待独立 Validator 复核；原记录保留当时的决定和证据，不表示当前状态。配置/CLI 的定向测试为 73 passed、45 deselected；写入层为 25 passed、64 deselected；契约/adapter 为 144 passed。统一检查使用 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`：`uv run ruff check .` 通过，`uv run ruff format --check .` 显示 84 files already formatted，`uv run pytest tests/ -v` 为 320 passed、5 warnings；`git diff --check` 通过。真实外接盘、硬件断电、真实 venue 和 Bronze 采集流程仍未实测。
- **本轮独立 Validator 发现（2026-11-11；第二轮修复前）**：三名 Validator 均重跑 Ruff 检查、格式检查及完整测试，分别观察到通过、84 个文件格式正确、320 passed/5 warnings；并复跑各自定向测试。结论 `changes required`。以下为实际复现或对照的发现：
  1. 大小写不敏感卷上，`receipt_id=A` 与 `a` 指向同一文件且相同字节被当作重试，丢失独立接收证据；真实 macOS 临时卷实测。
  2. DATA_ROOT 内存在嵌套挂载时，partial 可能与 recovery 跨卷，rename 返回 EXDEV；故障注入后数据仍在原 partial，但后续初始化恢复持续失败；未实测真实嵌套挂载。
  3. 现有恢复 payload 的 JSON 说明损坏时，初始化仅检查其存在，静默视为配对；实际将说明写为无效 JSON 后复现。
  4. 默认 `.env` 是目录时被静默忽略；Pydantic `model_validate`、`model_validate_json` 和嵌套 model 可绕开首轮异常转换，完整异常堆栈包含输入。均已用非敏感临时数据复现。
  5. adapter 子类可改写传入 Bronze 外壳并让溯源校验对照被改写值；普通和盘口路径均有风险。只读 Mapping 外壳遇错误时 `deepcopy` 抛 TypeError，统一错误与原始证据丢失。均已用 mock 实测。
  6. 极端 JSON 小数指数可抛未包装的 `decimal.InvalidOperation`，绕过 `ContractError` 和 adapter 的 `NormalizationError`；已实测。
  7. `gold.market_1m` 明确零覆盖仍接受盘口值和价差，且接受大于 1 的概率价差；`gold.market_1s` 双侧报价缺失时接受 mid，且接受与报价平均值不符的 mid；已实测。未知覆盖 `None` 与零不能混同。
  8. `silver.outcomes.label` 与 `gold.training_datasets.label` 的说明互相混淆；Silver 三个事件时间、daily 成交量与笔数的说明和必填类型矛盾。来源事件时间缺失、daily 成交缺失语义须遵守 FOUNDATION_RULES §5，不能编造时间或把未知填零。
  9. 开放设计：Bronze 非 venue、非 JSON/无效字节如何在解析前持久留证尚未决定；当前没有真实采集和持久化任务，不能声称已有数据丢失。此项须保留供负责人后续逐项复审，不自行确定架构。
- **新工作流配置块 B1（2026-11-13）**：首次循环第三轮因 Pydantic 内置错误消息可能包含输入而升级负责人；负责人同意固定安全错误消息后，第二循环经两轮独立 Reviewer 审查已收敛。复现、修复和检查结果见 [REVIEW_LOG.md](REVIEW_LOG.md)。其他 Validator 发现的工作区变更尚未按本工作流逐块审查，Bronze 开放设计仍待确认。
- **新工作流写入层 B2（2026-11-13）**：针对上述 Validator 发现 1–3 的既有实现进行审查，第一轮发现目录同步失败重试和 partial 说明字段校验问题，修复后第二轮独立 Reviewer 审查收敛。具体变更、测试及限制见 [REVIEW_LOG.md](REVIEW_LOG.md)；其他块及 Bronze 开放设计仍待处理。
- **新工作流 Adapter B3（2026-11-13）**：首次循环发现某些无效 Python 对象无法生成独立证据副本，负责人同意无法复制时保留原对象并明确标记；第二循环经三轮独立 Reviewer 审查后收敛。具体变更、检查与限制见 [REVIEW_LOG.md](REVIEW_LOG.md)。
- **新工作流数据契约 B4（2026-11-13）**：负责人确认一秒盘口可保留而未知滚动成交量留空；针对精度和单行矛盾实施修复，契约版本由工作区未发布的 `3.0.0` 提升至 `4.0.0`。两轮独立 Reviewer 审查后收敛；具体变更、测试及未实现的计算和迁移见 [REVIEW_LOG.md](REVIEW_LOG.md)。Bronze 非 venue、无效字节留证设计仍待负责人逐项复审。
- **Bronze 契约逐项复审（2026-11-13，进行中）**：工作区版本 `4.0.0`；对照 `agent/PROJECT.md` §3、§5–6、`FOUNDATION_RULES.md` §3、当前 `bronze.raw`、mock adapter 和测试。实际运行 `uv run pytest tests/test_data_schema.py tests/test_pipeline_foundation.py tests/test_adapter_contract.py -k 'bronze or provenance or readonly or envelope or normalization_failures or duplicate_source' -q`（`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1`）：24 passed、171 deselected。临时内存示例验证：`venue=None`、`api_version=None`、二进制 `raw_payload` 和非法 JSON 均被拒绝；合法 JSON `null` 以及 `ingested_at` 早于 `received_at` 均被契约接受。当前 mock 规范化要求 JSON 对象，且没有真实采集、原始字节持久化或完整 quarantine 流程。非交易所来源字段、原始字节保存以及时间异常的策略尚待负责人讨论，本记录不表示已决定或已实施。
- **Bronze 来源及原始内容决定（负责人确认，2026-11-13；待实施和后续设计）**：`source` 保持必填；没有交易所时 `venue` 可空，没有或不知道 API 版本时 `api_version` 可空，不编造信息。按照来源需要保留原始文件或字节及登记信息；具体保留完整响应还是逐条消息，由各来源设计时决定。解析失败保留证据并记录原因；当前尚未实现原始字节自动持久化或完整隔离流程。以上为方向和待办，不表示已确定字段结构或已修改代码。需评估契约版本、数据路径、清单与测试，并与 `agent/PROJECT.md`、`FOUNDATION_RULES.md`、`docs/SCHEMAS.md`、adapter 边界保持一致。
- **Bronze 时间异常处理方向（负责人确认，2026-11-13；待实施和后续设计）**：时间缺失时留空，不以其他时间冒充；时间顺序异常时保留原始数据和记录下来的时间，不自动改写，记录问题并先检查受影响记录，正常记录可继续处理。来源事件时间晚于接收时间可能与来源时间含义或时钟偏差有关，具体判断与容许偏差按来源研究，不预设统一秒数；检查后如需修复或带 caveat 使用，须遵循人工审核规则。具体字段可空性、检查和记录方式、审核流程、配置和测试待设计；当前契约仍接受 `ingested_at < received_at`，相关质量检查和隔离流程尚未实现。
- **Silver 市场契约初核（2026-11-13，进行中；待负责人讨论）**：当前 `silver.markets` 11 字段，主键为 `(venue, market_id, observed_at)`，mock 从 Bronze 接收时间填充 `observed_at`。`open_at <= close_at` 两者有值时执行，允许相等；状态限制六种。对照 `FOUNDATION_RULES.md` §3，当前契约没有市场描述和结算条件字段；`open_at`、`close_at` 的说明没有区分计划时间与实际时间。内存示例验证：开放与关闭相等、关闭时间晚于观察时间可通过；关闭早于开放和增加未声明 `description` 字段被拒；`unknown` 状态通过。`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_data_schema.py tests/test_adapter_contract.py tests/test_pipeline_foundation.py -k 'market_time or market_states or normalize_market or new_normalizers or market_crossed or normaliz' -q`：21 passed、174 deselected。以上为当前行为与发现，尚未决定或实施修改；是否增加字段及时间语义须与负责人讨论。
- **Silver 市场契约决定（负责人确认，2026-11-13；待实施）**：增加可空的市场描述和结算条件字段，来源未提供时留空；分别保存来源公布的计划开放/关闭时间与有可靠证据的实际开放/关闭时间。来源没有说明时间属于计划还是实际时保留来源原文，不猜测字段含义。具体字段名、历史版本和来源映射在实施方案中明确；更新数据契约、mock adapter、相关文档和测试，按规则处理 schema 版本。以上是阅读中确认的待办，尚未修改代码，也未验证真实来源。
- **Silver outcome 契约初核（2026-11-13；待实施）**：当前 `silver.outcomes` 8 个字段，主键为 `(venue, outcome_id, observed_at)`，虽有必填 `market_id` 但不属于主键。项目要求保留来源提供的 outcome 说明；当前只有非空显示名称 `label`，没有单独说明字段。内存示例验证：空名称、空市场 ID、空 outcome ID、负的 Bronze 记录序号及额外未声明的 `description` 都被拒绝。`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_adapter_contract.py tests/test_pipeline_foundation.py tests/test_data_schema.py -k 'outcome or new_normalizers or provenance or silver_missing' -q`：17 passed、178 deselected；其中 outcome 成功转换及缺少 label 失败为直接测试，溯源和可空时间等筛选结果包括其他数据集。尚未验证真实交易所 outcome ID 是否在整个交易所唯一；跨行主键唯一性未由本行契约检查。后续选择见下一条，未修改代码。
- **Silver outcome 后续待办（agent 自主决定，2026-11-13；待实施）**：依据 `FOUNDATION_RULES.md` §3，增加可空的来源 outcome 说明，不替来源编造内容；主键加入已有必填 `market_id`，避免同一来源的不同市场重用相同 outcome ID、且观察时间相同时发生身份冲突。临时示例中两行可单行校验通过，但现有主键相同；加入市场 ID 后可区分。该示例是模拟，不代表真实交易所一定重用 ID；各来源真实 ID 的范围、全局唯一性及跨市场一致性仍需在相应 adapter PR 核实，不能凭名称猜测或因此忽略来源要求。需要更新契约版本、mock、文档及身份冲突和可空说明测试；当前未修改代码。该决定由 agent 根据负责人授权和已有规则作出，不表示负责人逐项确认。
- **Silver 成交契约初核（2026-11-13；阅读进行中）**：当前 `silver.trades` 12 个字段，以 `(venue, trade_id)` 标识；`outcome_id`、`event_time` 和 `taker_side` 可空，价格范围为 0–1、数量不小于零。内存示例实测：缺 outcome、来源事件时间和主动方可通过，数量为零可通过，缺数量或价格大于 1 会拒绝。mock 的成交转换当前将 outcome 固定设空，不代表真实来源一定缺失。`UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_data_schema.py tests/test_adapter_contract.py tests/test_pipeline_foundation.py -k 'trade or normalization_failures or provenance or silver_missing' -q`：18 passed、177 deselected，其中筛选包含其他数据集的间接测试。成交 ID 的真实唯一范围、零数量是否可能及数据单位需在对应来源 adapter 中核实；缺失 outcome 对下游产品的影响须在质量和产品规则中处理，不能猜测。当前没有据此修改成交契约。
- **剩余 Silver / Gold 契约阅读（2026-11-13；未修改契约代码）**：逐项对照 `schema_registry.json`、`SCHEMAS.md`、`SCHEMA_REVIEW.md`、`FOUNDATION_RULES.md` 和对应测试，覆盖 `silver.events`、`silver.market_states`、`silver.book_snapshots`、`silver.book_deltas`、`silver.settlements`、`gold.market_daily`、`gold.market_1s`、`gold.liquidity_features`、`gold.training_datasets`、`gold.market_1m`。实际运行 `UV_CACHE_DIR=/private/tmp/pr1-review-uv-cache UV_NO_SYNC=1 uv run pytest tests/test_data_schema.py tests/test_pipeline_foundation.py tests/test_adapter_contract.py -k 'schema or contract or market or trade or outcome or book or settlement or event or training or gold or silver or bronze' -q`：153 passed、42 deselected。测试涵盖单行字段/规则及 mock 转换，不证明真实来源、跨行唯一、盘口重建或 Gold 产出流程；字段逐项及规则见 `SCHEMA_REVIEW.md`。
- **阅读发现与后续处理（agent 自主决定，2026-11-13；待实施或后续 PR）**：
  1. 当前 `silver.settlements.settled_at` 必填；实际输入 `None` 被拒。按负责人时间缺失不编造的方向，允许保留未知结算时间，但依赖结算时刻的质量检查和研究不得把未知当作已确认时间。需在本 PR 补契约/adapter/文档及空值测试，实际时间规则按来源核实。
  2. 当前 `gold.training_datasets` 接受标签有值但 `label_available_at=None`（已实测）。保留未知时间，不编造；不能把无法确认标签何时可用的记录自动当作可训练数据，须在未来质量门禁/训练构建中检查或经过明确记录的批准假设。当前没有这道门禁，不能声称已实现；需在 PR4 质量规则及后续训练/回测任务说明中引用并测试。
  3. `gold.market_daily` 实测接受 `day=2024-01-02`、`as_of=2024-01-01 00:00 UTC`。同一日的成交汇总不应早于该 UTC 日开始；本 PR 增加最小时间边界及测试。不把“日已结束”作为默认要求，是否允许日内部分汇总及完整性由后续产品与覆盖规则明确。
  4. `silver.market_states` 的买卖报价没有 outcome 标识；`gold.liquidity_features.depth_top_n` 没说明买侧、卖侧还是合计，均已核对字段和内存示例。不得默认报价对应 Yes 或深度含义；真实来源映射与产品口径留待对应 adapter / 特征设计，未确定前不可把它们当作已核实的 outcome 级指标。需补来源级测试和说明；不凭 mock 声称真实来源行为。
  5. `silver.book_snapshots` 对每档结构、范围和精度有行级检查，但实测买价 0.9、卖价 0.1 的盘口仍可通过；跨档排序、重复档位、序列缺口和真实来源的交叉盘口语义也未验证。PR4/PR7 须依据来源规则检查、保留证据并将异常送审核，不能声称本行契约已保证盘口完整；不可无依据将所有来源的一种盘口状态一律判定为错误。
  6. `gold.market_1s` 的 `update_count` 必填而数据不完整时的含义未定义；`gap` / `recovery` 的来源证据与完整性也未由行级契约证明。PR7 数据记录和产品设计须明确如何区分未知、确认为零和已知缺口，且不得把缺失数据冒充无更新；相关记录和质量检查目前均未实现。
- **后续实施约束**：上述 agent 自主决定依据既有负责人授权和项目规则，不表示负责人逐项确认。阅读阶段不修改代码；PR1 已确认项整理为待办后由 Analyst 实施并经 Reviewer 复核。需按契约版本政策更新版本、生成字段文档并同步 mock/测试；真实来源 ID、时钟、精度例外、跨行质量检查及 manifest/隔离/聚合仍由相应后续 PR 验证，不编造或提前声称实现。
- **新工作流 Bronze B5（2026-11-13）**：实施 Bronze 来源、原始内容及时间异常决定：`venue`、`api_version` 可空，新增 `raw_bytes`，与 `raw_payload` 恰好填一个，契约版本升至 `5.0.0`；`VenueAdapter` 规范化边界按“外壳校验 → 路由 → 时间异常 → 解码与严格解析”的顺序处理，写入时间早于接收时间时不输出 Silver，并保留证据。Round 1 发现路由检查晚于内容解析、空身份缺回归测试和文档执行位置不准确，修复后 Round 2 独立 Reviewer 审查收敛。交负责人：B5-R1-4（`agent/PROJECT.md` §6 原始记录字段列表缺 `raw_bytes`、`api_version`、`protocol_version`，修改须负责人确认）；B5-R1-6（无 API 版本的 venue 记录目前无法进入 Silver，留待来源设计）。B5-R2-1 的 bytes 子类测试已随 B6 修订补上。原始字节落盘、quarantine 流程、真实来源和旧版本迁移均未实现或验证。详见 [REVIEW_LOG.md](REVIEW_LOG.md)。
- **负责人决定（2026-11-13，B5 报告后）**：① 同意补全 `agent/PROJECT.md` §6 原始记录外壳字段列表（加入 `api_version`、`protocol_version`、`raw_payload / raw_bytes`），已修改。② API 版本改为可选：adapter 可以不声明 API 版本，以便无 API 版本的来源记录可路由并规范化到 Silver；作为 B5a 在 B6 审查结束后实施并经独立 Reviewer 审查。
- **B6 实施状态（2026-11-13）**：上文“Silver 市场契约决定”、“Silver outcome 后续待办”及“阅读发现与后续处理”第 1 条（结算时间可空）已在 B6 实施（契约 `6.0.0`），原文中“待实施/尚未修改代码”保留为当时记录。B6 Round 1 的 B6-R1-1 指出“保留来源原文”被 agent 解释为仅留在 Bronze；经询问，负责人确认在 Silver 新增 `source_open_time_text`、`source_close_time_text` 按原样保存未分类时间原文，四个计划/实际时间仍留空。
- **新工作流 Silver B6（2026-11-13）**：两轮独立 Reviewer 审查后收敛（契约 `6.0.0`）。交负责人/后续：B6-R1-5 无时间结算的回填方式留 PR5/PR6；B6-R2-1 未分类时间原文遇空字符串或非字符串原值时的映射由来源 adapter 决定，已在 SCHEMA_REVIEW 补充说明（随 B5a 修订复核）。详见 [REVIEW_LOG.md](REVIEW_LOG.md)。
- **新工作流 B5a · API 版本可选（2026-11-13）**：实施负责人决定 ②：`AdapterMetadata.api_version` 可为 `None`，声明时须为非空字符串；无 API 版本的 Bronze 记录可由同样无版本的 adapter 规范化到 Silver，有/无版本之间互不误路由；B5 条目中“无 API 版本的 venue 记录目前无法进入 Silver”已不再成立。独立 Reviewer 一轮收敛；三条 suggestion（本条目、ADR-002/CHANGELOG 说明、`api_protocol_version` 区分 `None` 与字面 `"none"`）已采纳，随 B7 修订复核。交后续（B5a-R1-4，PR5/PR6）：一个 adapter 只接受一种 API 版本，同一来源多版本需分别建 adapter；`venue=None` 记录仍无 adapter 可规范化，均明确报错不静默丢弃。
- **新工作流 B7（2026-11-13）**：上文“阅读发现与后续处理”第 3 条已实施：新增通用 `day_start` 规则，`gold.market_daily.as_of` 不得早于 `day` 的 UTC 零点，不要求当日已结束，契约升至 `7.0.0`。第 2、4、5、6 条作为后续限制记录在 [SCHEMA_REVIEW.md](SCHEMA_REVIEW.md) “关键选择”第 7 条（未实现）。独立 Reviewer 一轮收敛；三条 suggestion（本条目、错误信息包含被拒日期值、直接测试 `day_start` 日期解析分支并为声明自检加 `match`）已采纳，交最终 Validator 复核。
- **最终 Validator Round 1 与 B8（2026-11-13）**：Validator 结论 `changes required`（3 条 should-fix，无 must-fix），并按新增的“必要性与简化”审查提出简化建议。负责人决定：迁移清单移至 PR3；写锁保持立即失败并写清语义，超时与扫描范围留 PR2；在 PR1 的 `check` 中实现启动配置日志（硬规则 10）；同意删除 recovery 旧格式兼容、`gc` 可信性判断和 adapter 的 `validation_rules` 声明。上述修复作为 B8 实施，待独立 Reviewer 循环后交 Validator 复查。详见 [REVIEW_LOG.md](REVIEW_LOG.md)。
- **B8 收敛（2026-11-13）**：独立 Reviewer 三轮后收敛（474 passed）。Round 1 发现 S4 实际影响大于原描述（合法只读代理外壳也无法规范化，规范化输入须为普通 `dict`），已写入 README/CHANGELOG/ADR-002 并加测试，已告知负责人；Round 2 发现来源记录用只读映射导致配置无法 pickle/深拷贝，改为元组并加测试。待最终 Validator 复查。
- **最终 Validator Round 2（2026-11-13）**：结论 `ready for owner review`（不代表批准合并）；Round 1 全部发现已复核解决，无 must-fix/should-fix。遗留不阻塞项：V2-1 `config.effective` 在 WARNING 以上级别不输出，首个数据任务（PR2）决定是否无视日志级别；V2-2 `environment:*` 来源不区分进程环境与 `.env`；V2-S1 `_payload` 中恒真的 `isinstance(raw, Mapping)` 可删。合并由负责人决定。
- **负责人决定与 B9（2026-11-13，Validator Round 2 之后）**：负责人希望合法的只读映射可以规范化，撤回 V1-S4。恢复 B3 已审查的做法：只读映射代理的底层经 `gc.get_referents` 确认为普通 `dict` 时信任并复制（结果为 dict，可规范化），其他映射保留原引用并标为非快照。恢复两条只读证据测试，新增 `test_valid_readonly_envelope_normalizes_like_a_dict`；README、CHANGELOG、ADR-002 同步。待独立 Reviewer 与 Validator 复查。
- **B9 收敛与最终 Validator Round 3（2026-11-13）**：B9 独立 Reviewer 一轮收敛，三条 suggestion 已采纳（`raw.copy()` 避免检查前运行键钩子、文档注明依赖 CPython、测试断言证据为 dict 快照）。Validator Round 3 结论 `ready for owner review`（475 passed），不代表批准合并。留给 PR2 调度器设计时请负责人再确认：V3-Q1 是否仍需支持只读代理输入；V2-S1 `_payload` 中恒真的 `isinstance` 可删。

## 3. 实施中需要负责人确认的事项

以下事项需要在实施记录中写明最终选择，供负责人重新 review。负责人于 2026-11-09 授权先实施，不必逐项暂停确认；其中环境变量整数接受十进制数字字符串，拒绝 `"4_000"` 和 `"+4"`。

| 事项 | 所在块 | 详情 |
| --- | --- | --- |
| 外接硬盘的文件系统格式；不支持硬链接时是否需要替代的“不覆盖”发布方式 | 第 3 块 | §4.7 第 1 条 |
| 环境变量字符串转整数的规则，是否拒绝 `"4_000"`、`"+4"` | 第 1 块 | §4.1 实施注意 |
| `side`、`taker_side`、`status` 的合法取值 | 第 4 块 | §4.8 第 1 条 |
| `label_available_at` 等于 `observation_time` 是否合法 | 第 4 块 | §4.8 第 1 条 |
| JSON 规则格式表达不了的规则如何处理 | 第 4 块 | §4.8 第 2 条 |
| 规则变化是否需要提升 `schema_version` | 第 4 块 | §4.10 第 2 条 |
| `gold.market_1m` 中 dictionary 字段在 Parquet 中的类型 | 第 4 块 | §4.8 第 6 条 |
| 溯源方案：Bronze 外壳由谁包装、`normalize_*` 的输入形式 | 第 5 块 | §4.9 第 2 条 |
| `capabilities` 的可选值集合；`start` 等于 `end` 是否合法 | 第 5 块 | §4.9 第 5、6 条 |

## 4. 待办详情（PR1 实施）

以下为阅读后交给 Analyst 的待办；已完成的事项以第 2 节的状态为准。

### 4.1 配置：预期字段、pydantic 与 `validation.py`

- 为配置文件保留独立于配置值的预期字段定义，使程序能够知道每类配置允许或要求哪些键及其校验规则；相同类型的多份配置应能共用定义，不要求每份配置重复保存规则。当前 `load_json_setting` 只支持单键文件，未来多字段配置的具体实现结合现有设计确定。
- 将配置格式定义放在哪里、如何增加或修改预期字段及其校验规则，记录在合适的配置开发 Markdown 文档中，并明确要求开发者和 agent 每次编写或修改相关配置代码前阅读该文档。
- `load_json_setting` 当前同时负责读取和单键/类型校验，与 `src/config/developing.md` 中 “loader 不承担业务验证” 的边界不一致。修改时将 loader 收窄为通用 JSON 对象读取（只处理 I/O 和 JSON 错误），字段集合与类型校验移入对应 model，并保留现有的严格类型检查（如拒绝 bool 冒充 int）及其测试。

**负责人决定（2026-11-09，阅读 `src/config/models/pipeline.py` 时）**

设计讲解见 Claude Doc《Config 整体设计讲解》：https://claude.ai/artifact/QPvg9kL4a71jb2TUuQRk9R

1. **字段声明使用 pydantic**：model 用 pydantic 声明字段、类型和校验规则，由它完成类型校验和报错。需要在 `pyproject.toml` / `uv.lock` 中新增依赖。
2. **只有共享环境可被环境变量覆盖**：`DATA_MIN_FREE_GIB`、`PIPELINE_LOG_LEVEL` 等覆盖只适用于 `PipelineConfig`；venue、quality、execution、task 等参数只来自 JSON 和 CLI，不读环境变量。
3. **PR1 现在就切换到新机制**：`storage.json`、`runtime.json` 改为由 loader 读成 dict、再交给 pydantic 版 `PipelineConfig` 校验，使 PR1 成为后续 model 的样板；`load_json_setting` 相应收窄或替换为通用 JSON 对象读取。
4. **`.env` 的定位**：保存所有敏感信息（API key、私钥、数据库连接等）和机器级全局设置（如 `DATA_ROOT`），对整个 package 全局生效；任务参数不放在 `.env`。

**实施注意**（阅读时发现，供 Analyst 结合实际代码确定）：

- **异常边界**：pydantic 抛 `ValidationError`，CLI 和测试目前依赖 `ConfigError` 及其消息。需要在 model 边界统一转成 `ConfigError`，并保留可读的字段名，例如 `DATA_ROOT`、`PIPELINE_CONFIG_DIR`。
- **严格类型与环境字符串**：JSON 中应继续拒绝 `true` 冒充 int（strict），但环境变量的值总是字符串（如 `"4"`），需要明确从字符串转换的规则。同时决定是否拒绝 `int()` 目前会接受的 `"4_000"`、`"+4"`。
- **不可变与修改路径**：现有测试使用 `dataclasses.replace` 并要求修改时重新校验。pydantic 的 `model_copy(update=...)` 默认**不重新校验**，需要选定替代方式（例如重新构造），并更新 `test_direct_config_and_replace_reject_invalid_fields`。
- **构造时不访问磁盘**：pydantic 校验器中同样不得访问或修改磁盘，现有测试 `test_direct_config_validates_and_normalizes_without_filesystem_probes` 的约束保持不变。
- **共享校验工具 `src/config/validation.py`（负责人决定在 PR1 建立）**：
    - 职责是校验**合法性**，不只是类型。PR1 中放入可复用的、带取值约束的 pydantic 字段类型：不含 NUL 的绝对路径、非负整数、五种日志级别之一。以后多个 model 共用的合法性检查（例如时间窗口结束晚于开始）也放在这里。
    - 在此统一将 pydantic `ValidationError` 转为 `ConfigError`，保留可读的字段名。
    - 不放这里的内容：只属于单个 model 的字段关系，写在该 model 的 validator 中；跨配置的合法性（job 引用的 profile 是否存在、quality policy 是否显式选择），由 resolver 或 task model 负责；真实环境（目录、权限、空间），由 preflight 负责；数据行的合法性，由 `src/data_schema/` 负责。
    - 不使用 `common.py` 这类含义不清的名字；同步修改 developing.md 目标结构中的 `models/common.py`，并在 `README_FOR_DEVELOPER.md` 中说明上述分工。

**文档**：按 developing.md 规则 11，同时更新 `src/config/README.md`、`README_FOR_DEVELOPER.md`，以及 developing.md 中 models 的说明。具体位置：

- 改用 pydantic：`README.md` L33；`README_FOR_DEVELOPER.md` L20-29（`dataclasses.replace()`、`__post_init__` 的描述）和 L40（“dataclass”一词）；`developing.md` “强制规则”写明 model 用 pydantic 声明。
- 只有共享环境可被环境变量覆盖：`README.md` L29 优先级说明、`README_FOR_DEVELOPER.md` “职责边界”、`developing.md` “强制规则”写明该规则只适用于 `PipelineConfig`。
- 写检查失败时清理新建目录：`README.md` L54-63 写任务部分补充失败行为。
- `README.md` L27 补充 `load(config_dir=...)` 参数优先级最高（参数 > `PIPELINE_CONFIG_DIR` > 默认目录）。
- 删除 `from_env()`：三份文档均未提及，无需修改。

### 4.2 配置加载、preflight 与 CLI 的测试

1. 默认 `.env` 不存在：隔离进程环境并将默认文件指向不存在的路径，验证 `load_environment(None, None)` 不报错，仍返回进程环境中的设置。
2. 无值的键：在显式环境文件中包含没有 `=` 的键和正常赋值的键，验证前者不进入结果、后者保留；同时区分 `KEY=` 的空字符串与没有值的键。
3. `.env` 读取失败：显式环境文件为非 UTF-8 内容或不可读时，验证抛出 `ConfigError("Cannot read environment file ...")`。
4. `load_json_setting` 的格式边界：顶层不是对象（如 `[1]`、`2`）、缺少期望键（如 `{}`）、文件非 UTF-8 时均抛出 `ConfigError`。按 §4.1 重构 loader 后，这些测试用于确认重构后行为不变。
5. `~` 展开（`PipelineConfig.load`）：将主目录指向临时目录（如 monkeypatch `HOME`），传入 `DATA_ROOT=~/<路径>` 和 `PIPELINE_CONFIG_DIR=~/<路径>`，验证两者均展开为该临时目录下的绝对路径。python-dotenv 不展开 `~`，`.env` 中这样写依赖 `expanduser()`；改用 pydantic 时须保留此行为。
6. `validate_for_write` 未覆盖的失败分支：`shutil.disk_usage` 抛 `OSError` 时报 `Cannot check free disk space`；`mkdir` 失败（如父目录无写权限）时报 `DATA_ROOT is not writable`；`mkdir` 后路径不是目录时报 `DATA_ROOT is not writable`。
7. `DATA_ROOT` 为软链接：`check_configured_root`、`validate_for_read`、`validate_for_write` 返回解析后的真实路径。
8. 修改 `test_module_entry_point_runs_in_a_new_process`（L636），让结果与本机 `.env` 和终端环境变量无关：子进程环境中显式设置全部 4 个 pipeline 变量（`DATA_ROOT`、`DATA_MIN_FREE_GIB`，以及 `PIPELINE_CONFIG_DIR=""`、`PIPELINE_LOG_LEVEL=""` 以退回默认值）。阅读时验证：在子进程环境中加入 `PIPELINE_LOG_LEVEL=nonsense`，同一命令返回 2。可另加一个用例，在环境中放入非法的 `PIPELINE_LOG_LEVEL`，确认测试显式设置的值会覆盖它。只影响测试，正常运行时每台机器仍读取自己的 `.env`。
9. CLI `check` 未覆盖的分支：
    - 命令名写错时返回退出码，而不是抛出 `SystemExit`，与 §4.5 一起实施；
    - `check` 过程中出现 `OSError`（例如 monkeypatch 让 `check_configured_root` 抛出 `OSError`）时，返回 2 并在 stderr 输出 `pipeline startup failed`。

### 4.3 写检查失败时清理新建目录

- 现状：`validate_for_write()` 先 `mkdir(parents=True)` 再试写临时文件；试写失败（如只读挂载）时，本次新建的空目录留在磁盘上。
- 负责人决定（2026-11-09）：写检查失败时，只清理**本次调用新建**的目录（从最深一层往上删除，直到第一个原本就存在的祖先），不得删除原本已存在的目录或任何文件。
- 需新增测试：模拟试写失败后，验证新建的多层目录被移除、原本存在的祖先目录保留；目录原本已存在时，失败后目录仍保留。

### 4.4 删除 `PipelineConfig.from_env()`

- `from_env(environ)` 只是 `load(environ=environ)` 的别名；`environ` 为 None 时仍会读 `.env` 和 JSON 默认值，名字容易误解。源码中没有调用方，只有测试使用。
- 负责人决定删除（2026-11-09）。删除后将测试中的 `PipelineConfig.from_env(...)` 改为 `PipelineConfig.load(environ=...)`，并同步更新 `src/config/README.md` 和 `README_FOR_DEVELOPER.md` 中的相关说明。

### 4.5 统一 CLI 入口

- 将 `src/cli.py` 定位为类似 `app.py` 的统一命令入口：识别命令，并将任务交给相应的执行函数；调整只描述配置检查的文件说明。
- 当前只实现并保留 `check` 的行为；在 `src/cli.py` 中留下一个简短、非执行性的示例，说明未来如何接入其他命令及其任务函数。示例不是可运行的命令，不实现未来任务，也不预建空模块。
- 保持 `check` 无写入副作用，更新受影响的测试和文档；入口函数命名及具体分发方式结合现有代码确定，重大设计选择先与负责人讨论。
- `src/__main__.py` 保留现有入口。
- 命令名写错时，`main` 目前由 argparse 抛出 `SystemExit(2)`，不返回 `int`（2026-11-09 实际验证 `main(["bogus"])`）。统一入口后，`main` 对未知命令也返回退出码，不直接结束进程；补测试（负责人确认）。

### 4.6 按 `log_level` 配置结构化日志

- 现状：`PipelineConfig.log_level` 被读取和校验，但 PR1 的 `src` 代码（不含旧 analysis、indexers、common）中没有任何地方配置或使用 logging，违反 developing.md 第 10 条。
- 负责人选择保留该字段并真正使用（2026-11-09）：在 CLI 入口按 `log_level` 配置 logging；§4.7 中“内容相同的冲突视为成功并记一条日志”等后续日志统一走这里。
- **结构化格式（负责人确认）**：按 ADR-001 L16 “structured logs” 的要求，每行一个 JSON 对象，至少包含时间（UTC）、级别、事件名和消息；有运行时带上 `run_id`，以便与 run record 关联。不记录密钥和敏感信息。
- 测试：设置不同 `log_level` 时，日志级别实际生效（例如 DEBUG 消息在 INFO 级别下不输出）；每行日志都是合法 JSON 并包含约定字段；密钥类环境变量不会出现在日志中。

### 4.7 `src/data_io/layout.py`

1. **外接硬盘支持**：负责人的 `DATA_ROOT` 位于外接硬盘（文件系统格式待确认；阅读时未挂载，`.env` 中 `DATA_ROOT` 为空）。`write_new` 依赖 `os.link`，exFAT/FAT32 等不支持硬链接的格式会导致所有写入失败。要求：
    - 写任务 preflight 检测 `DATA_ROOT` 是否支持硬链接，不支持时给出明确报错；结合负责人确认的格式，决定是否需要替代的“不覆盖”发布方式，重大设计先与负责人讨论。
    - 外接硬盘未挂载时（如 `/Volumes/<盘名>` 不存在）给出明确的“卷未挂载”报错。当前行为：空间检查落到系统盘的 `/Volumes`，随后 `mkdir` 因 `/Volumes` 属 root 而失败，报 “not enough space” 或 “not writable”，容易误导。
2. **发布后对父目录 `fsync`**：当前只对文件内容 `fsync`，`os.link` 之后没有对父目录 `fsync`，断电后文件名可能丢失，而 checkpoint 可能已经前进。要求发布后对父目录 `fsync`；评估 macOS 下普通 `fsync` 不保证刷出硬盘自身缓存的问题（`F_FULLFSYNC`），外接硬盘尤其相关。
3. **统一异常类型**：`DataLayout.create` 在 root 不存在时抛 `FileNotFoundError`，已有同名普通文件时抛 `FileExistsError`（已实际验证），L37 “不是目录”的检查对普通文件实际走不到。要求统一转为 `WriteBoundaryError`，消息说明原因。
4. **冲突数据和残留 partial 文件不得丢弃（负责人要求）**：
    - 现状：`write_new` 因目标已存在而拒绝时，`finally` 删除临时文件，新数据被丢弃。进程崩溃或断电时 `finally` 不执行，`.partial-*` 残留在层级目录中，没有任何清理或识别机制。
    - 负责人要求：拒绝替换时仍然抛出错误，但新数据必须保留在安全的位置；残留的 partial 文件不能直接丢弃（盘中增量数据，尤其是无法回补的 orderbook delta，丢失后无法恢复）。
    - **已确认方案**：
        - **recovery 区**：新增 `DATA_ROOT/recovery/`，结构为 `recovery/conflicts/<层>/<原路径>/<时间戳>-<随机>.bin` 和 `recovery/partials/<层>/<原路径>/<时间戳>-<随机>.bin`，每份数据旁边放一个同名 `.json` 说明。recovery 区与数据在同一文件系统，移动数据用改名或硬链接，不跨盘复制；只进不删，由人工审核处理。需同步修改 `agent/PROJECT.md` §5 数据布局。
        - **replace 冲突**：
            - 内容与已有文件**逐字节相同**：视为成功，不另存副本，返回已有路径，并记录一条日志。
            - 与 `docs/pr1/FOUNDATION_RULES.md` §3 L32“同样的数据收到多次，每次接收证据都保留”的关系（负责人确认）：Bronze 路径必须包含本次接收的身份（例如 `run_id`），保证两次独立接收永远不会写到同一路径；“逐字节相同视为成功”只适用于同一次写入的重试。两份文档中都写明这一点。
            - 内容不同：已落盘的临时文件不删除，移到 `recovery/conflicts/...`；说明 JSON 记录原目标路径、时间、新旧两份数据的 checksum 和大小、原因；然后抛出 `WriteBoundaryError`，错误信息包含 recovery 路径。
        - **残留 partial**：
            - 永不自动删除。写任务开始前扫描各层 `.partial-*`，移到 `recovery/partials/...`，说明 JSON 记录原位置、大小、修改时间、checksum，并标记“完整性未知”。
            - 用**锁文件**判断没有其他进程正在写：只有拿到锁后才扫描和移动，写入期间持有锁，具体实现交给 Analyst。
        - **读取方与 checkpoint**：所有读取方忽略 `.partial-*` 和 `recovery/`；recovery 中的数据不能让 checkpoint 前进。
        - **需新增测试**：
            - 相同内容的冲突返回成功、不产生副本，并记录日志；
            - 两次独立接收相同内容时，各自产生一个文件；
            - 不同内容的冲突抛错，数据和说明 JSON 出现在 recovery 区，旧文件不变；
            - 残留 partial 在持锁时被移入 recovery 区并带有说明；
            - 未拿到锁时不移动 partial；
            - 发布失败（如 `os.link` 抛错）时，数据进入 recovery 而不是被删除。
5. **补充测试**：payload 不是 bytes → `TypeError`；路径只有一段（如 `"bronze"`）→ `WriteBoundaryError`；`create` 之后层级目录被替换为软链接 → `write_new` 拒绝；`create` 时 root 不存在、层级位置已有普通文件 → 统一后的 `WriteBoundaryError`；发布后父目录被 `fsync`（可用 monkeypatch 观察调用）。

### 4.8 `src/data_schema/`

阅读时实际验证：`best_bid=0.9`、`best_ask=0.1` 的 `silver.market_states` 行能通过校验；`Europe/London` 1 月的时间能通过 UTC 检查；修改 `get_contract()` 的返回值会改动全局 `SCHEMA_REGISTRY`。

1. **规则分两类（负责人确认）**：
    - **行级硬规则**：只看一行数据就能判断的规则，放进 `validate_record`，违反即拒绝。本次需补充：
        - `silver.market_states`、`gold.market_1s`：`best_bid` 和 `best_ask` 都有值时，`best_bid <= best_ask`；
        - `gold.market_1s`：`spread` 与 `best_ask - best_bid` 一致，`gold.liquidity_features` 视其字段是否足够判断再定；
        - `silver.markets`：`open_at` 和 `close_at` 都有值时，`open_at <= close_at`；
        - `gold.training_datasets`：`label_available_at` 有值时，`observation_time` 在前，`label_available_at` 在后（负责人确认）；两者相等是否允许，Analyst 实施时向负责人确认；
        - `side`、`taker_side`、`status` 的合法取值（目前文档未定义取值集合；由 Analyst 提议取值，负责人确认后再写入）；
        - `silver.book_snapshots` 的 `bids`、`asks` 每一档的结构（例如价格和数量字段、类型、范围）。
    - **跨行、跨文件规则**（缺口、重复、序列号连续性、跨表一致性、异常值等）不放在 contract，留给 PR4 的 validation 模块（§5.3）。
2. **所有规则都用 JSON 声明（负责人确认）**：数据 schema、取值范围规则和行内规则全部声明在 `schema_registry.json` 中；如果单个文件过大，也可以拆成 `src/data_schema/` 同目录下的多个 JSON 文件（例如 schema 一个、规则一个），由 Analyst 选择并说明理由。
    - 需迁移的内容：
        - `contracts.py` L28-68 三张表里的范围规则；
        - 特殊规则，即整秒对齐和 ISO 日期；
        - 现有的 point-in-time 规则；
        - 第 1 条新增的行内规则，包括 bid ≤ ask、spread、时间先后、枚举取值和 `bids`/`asks` 档位结构。
    - `contracts.py` 只负责读取声明并执行，不再硬编码任何数据集或字段名。删除 L25-27 的过渡注释。
    - 规则的声明格式需要足够表达范围、枚举、字段比较和条件，例如“两者都有值时才比较”。不能表达的规则要先列出来，交负责人决定。
    - 变更后同步 `docs/SCHEMAS.md`（§4.10），评估是否需要提升 `schema_version`。
    - **下一次 review 时，Reporter 需要逐项讲解这些 JSON 的具体内容**：每个数据集的字段、主键、每条范围规则和行内规则的含义，以及规则格式本身怎么读。
3. **`get_contract()` 不暴露可变的全局 registry**：返回只读视图或深拷贝，`SCHEMA_REGISTRY` 本身也不应被外部修改。
4. **UTC 判断改为严格（负责人确认）**：`utc_datetime` 只接受 `tzinfo` 为 `timezone.utc` 的时间。偏移量为 0 的其他时区，例如冬令时的 `Europe/London`、`timezone(timedelta(0))`，以及 `ZoneInfo("UTC")`，一律拒绝。错误信息需说明“必须使用 `timezone.utc`”。
5. **registry 自检**：加载 registry 时检查其自身一致性，例如主键字段都在 `fields` 中、主键字段不可为空、类型名都在支持的 6 种之内、每个字段都有非空 `description`；不一致时在 import 时直接报错。L167-169 的主键非空检查在自检保证后可删除或保留为防御代码，二选一并说明理由。
6. **新增 `gold.market_1m` contract（负责人确认）**：registry 目前只有 `gold.market_1s` 和 `gold.market_daily`，没有 PR1 的第一份研究产品“1 分钟 Gold”；`docs/pr1/PLAN.md` 第 7 块“定义 1 分钟 Gold 契约”仍待执行。按 `docs/pr1/FOUNDATION_RULES.md` §5、§6 定义：
    - 成交：OHLC、成交份数、可可靠计算时的成交金额、成交笔数、VWAP；单位分别标明；同一时间多笔成交且顺序不明时，开盘或收盘价为空并记录原因；
    - 盘口：最佳买卖价、价差、买卖两侧每档价格、挂单份数和金额（以档位序号为键的 dictionary，两侧分开）、前 N 档汇总（N 来自特征参数，默认 5，见 §5.1）；
    - 按持续时间加权的分钟平均；实际观察档位数的时间加权平均和最少值；价差的共同覆盖时间；
    - 窗口按 UTC 整分钟、包含开始不包含结束；缺失为空，不填零；确认无成交时成交量为 0；
    - 覆盖列与 manifest 的关系；`source_manifest_ids`。
    - 只定义 contract（字段、类型、规则、`description`），不实现聚合。dictionary 字段在 Parquet 中的类型需要 Analyst 提方案（现有 6 种类型中只有 `json` 能表达）。
    - 测试：合法行通过、能转成 Arrow 表；窗口未对齐整分钟、价格超出 0 到 1、缺失被填为 0 等情况被拒绝（具体以最终规则为准）。
7. **point-in-time 改用可用时间，检查分两层（负责人确认）**：
    - 现状：`gold.training_datasets` 检查 `max_feature_event_time <= observation_time`，用的是事件时间而不是可用时间，也不考虑 `docs/pr1/FOUNDATION_RULES.md` §5 L60 的 information delay（默认 1 分钟）。阅读时实际验证：`max_feature_event_time == observation_time` 的行能通过；测试 L551 也把它当作合法。
    - 例子：10:00 决策、延迟 1 分钟时，事件时间 09:59:30 的成交（还在延迟内），以及事件时间 09:58:50、10:00:20 才收到的成交，按文档都不能用，但当前 contract 都放行。
    - 修改：
        - 字段 `max_feature_event_time` 改为 `max_feature_available_at`（所有输入中最晚的可用时间），`description` 写明“可用时间”的含义；
        - **第一层（contract，行内）**：`max_feature_available_at <= observation_time`；
        - **第二层（构建训练集、回测时）**：`max_feature_available_at <= observation_time - information_delay`。延迟是实验参数，放在 backtest/实验配置中（默认 1 分钟），并记录到 manifest 和 run record；延迟不作为列写进每一行。第二层的代码在训练集构建和回测的 PR 中实现，PR1 只在文档中写明分工。
        - 历史回补数据的可用时间无法直接得知，只能使用经负责人批准并记录的假设（`docs/pr1/FOUNDATION_RULES.md` §5 L59），不能把回补时的接收时间或事件时间当作已验证的可用时间。
        - 字段改名属于含义变化，按版本政策处理 `schema_version`；同步 `docs/SCHEMAS.md`（L13 的 point-in-time 说明）和 `docs/pr1/FOUNDATION_RULES.md` §5。
    - 测试：可用时间等于 `observation_time` 时通过第一层；晚于 `observation_time` 时被拒绝；修改 L530 `test_training_features_obey_point_in_time_contract` 中使用旧字段名的用例。

测试要求：

1. 上述每条新规则各有通过和拒绝的用例，包括 bid/ask 有一方为空时不触发比较。
2. 修改 `get_contract()` 的返回值后，全局 registry 和后续校验不受影响。
3. `Europe/London`（1 月）、`timezone(timedelta(0))`、`ZoneInfo("UTC")` 都被拒绝；`timezone.utc` 通过。
4. 规则声明本身：JSON 中引用不存在的数据集或字段、未知的规则类型、格式错误时，在加载时报错；`contracts.py` 中不再出现硬编码的数据集名或字段名（可用测试或代码检查确认）。
5. registry 自检：主键字段不存在、主键字段可为空、未知类型名、字段缺少 `description` 或为空字符串时报错。
6. 补齐目前没有测试的情况：
    - 缺字段；
    - `schema_version` 不匹配；
    - 必填字段为 `None`；
    - 空字符串、全空格字符串；
    - `bool` 冒充 `int`；
    - imbalance 超出 -1 到 1；
    - `market_daily.day` 不是合法 ISO 日期；
    - `features` 不是 JSON 对象；
    - `source_manifest_ids` 不是数组，或含空字符串。

### 4.9 `src/adapters/`（负责人确认全部在 PR1 实施）

阅读时实际验证：

- mock 的 `normalize_trade` 对价格 `"abc"` 报 `decimal.InvalidOperation`，对缺少 `price` 报 `KeyError`，对价格 `"1.5"` 报 `ContractError`；
- `AdapterMetadata` 接受 `primary_keys={"markets": ()}` 和 `rate_limits={"rps": True}`；`rate_limits={"rps": "10"}` 报 `TypeError`；`metadata.rate_limits` 构造后仍可被修改；
- `backfill_trades` 在 `start` 晚于 `end`、时间不带时区时仍返回数据。

1. **统一规范化错误**：新增 adapter 专用错误类型（例如 `NormalizationError`），携带数据集名、失败原因和原始记录（证据）。`normalize_*` 内部的 `KeyError`、`decimal.InvalidOperation`、`ContractError` 等都转换成这一种，并保留原始异常链。目的是让调度器能区分“数据坏了，进 quarantine”和“代码 bug”。
2. **溯源信息来自 Bronze 外壳（接口设计，PR1 定下来）**：
    - 明确“API 返回的数据 → 包装成 `bronze.raw` → 规范化”的完整链路，以及每一步由谁负责（adapter 还是调度器）；
    - `normalize_*` 的输入改为能拿到 Bronze 外壳的 `run_id` 和 `record_index`（例如直接接收 `bronze.raw` 行，或单独传入溯源参数），不再要求原始 payload 自带 `bronze_run_id` 和 `bronze_record_index`；
    - mock 的原始数据中删除这两个字段，改走新链路；
    - 方案在实施前列出交负责人确认。
3. **盘口事件明确返回的数据集**：`normalize_book_event` 的返回值要标明是 `silver.book_snapshots` 还是 `silver.book_deltas`（例如返回“数据集名 + 行”，或拆成两个方法）。mock 两种都要实现。
4. **补齐 Silver 数据集的规范化方法（负责人确认）**：为 `silver.settlements`、`silver.events`、`silver.outcomes`、`silver.market_states` 增加对应的 `normalize_*` 抽象方法，mock 全部实现，并都经过 `validate_record`。同步更新 `agent/PROJECT.md` §8 的接口列表、`base.py` 模块说明里的 “eight-operation” 描述，以及 L601 参数化测试的方法列表。
5. **加强 `AdapterMetadata` 校验**：
    - 内层也不能为空，例如 `primary_keys` 的每个键都要有字段；
    - `rate_limits` 的值必须是严格 `int`（拒绝 `bool` 和字符串）且大于 0，错误统一为同一种类型；
    - dict 字段改为只读（例如 `MappingProxyType`），保证 frozen 名副其实；
    - `capabilities` 使用固定的可选值集合，并与 adapter 实际提供的方法对应；
    - `validation_rules` 与 `SCHEMA_VERSION` 关联，不再是随意文字；
    - 约定 venue 不支持某项功能时的表示方式，例如调用对应方法时抛出专门的“不支持”错误，且与 `capabilities` 一致。
6. **时间范围参数统一检查**：在基类中统一检查 `start`、`end` 必须带 `timezone.utc`（与 §4.8 第 4 条一致），且 `start < end`（是否允许相等由 Analyst 提议）；各 adapter 不各自重写。注意项目使用 Python 3.9，`datetime.fromisoformat` 不接受 `Z` 结尾的时间，真实 adapter 解析时间时需要统一的工具函数。
7. **mock 支持分页（负责人确认现在做）**：mock 支持按页返回并给出 `next_cursor`，用来测试翻页与 cursor 流转；`start`、`end` 也要真正生效，用来过滤数据。

测试要求：

1. 规范化失败：缺字段、价格无法解析、违反 contract，都报统一的错误类型，错误中带数据集名和原始记录，并保留原始异常。
2. 溯源：规范化结果的 `bronze_run_id`、`bronze_record_index` 来自 Bronze 外壳；原始 payload 中没有这两个字段也能正常规范化。
3. 盘口事件：snapshot 和 delta 各自返回正确的数据集名，并能通过对应 contract 和 Arrow 表转换。
4. 新增的 4 个规范化方法各有通过和拒绝的用例；缺少任一新方法时无法实例化。
5. `AdapterMetadata`：8 项声明逐项为空时报错（目前只测了 `validation_rules`）；内层为空、`rate_limits` 为 `bool`、字符串、0、负数时报错；构造后 dict 字段不能修改；`capabilities` 含未知值时报错；不支持的功能被调用时抛出约定的错误。
6. 时间范围：`start` 晚于 `end`、不带时区、非 `timezone.utc` 时报错。
7. 分页：多页数据按 `next_cursor` 依次读完，最后一页 `next_cursor` 为 `None`，记录不重复不遗漏；`start`、`end` 过滤生效。
8. 补齐目前没有测试的情况：
    - 缺少 `metadata` 属性时无法实例化（加入 L601 的参数列表）；
    - `stream_market_data` 传入不相关的市场时不产出数据。

### 4.10 `docs/SCHEMAS.md`

1. **JSON 是唯一事实来源，文档自动生成（负责人选择选项 b）**：
    - `docs/SCHEMAS.md` 不再复制 registry 的 JSON，改为链接到 `src/data_schema/` 下的 JSON 文件；
    - 给人读的部分（每个数据集一张字段表：字段、类型、能否为空、是否主键、适用规则、字段说明）由脚本从 JSON 生成；
    - 手写的说明文字（存储与版本规则、校验边界）和生成的部分分开，生成部分用明确的起止标记包住，避免手工改动被覆盖；
    - L397 `test_schema_document_matches_code_registry` 改为：重新生成后与文档中的生成部分逐字相同，否则失败并提示运行生成脚本；保留 Arrow 字段名、可空性和版本元数据的检查。
    - 与 §4.8 第 2 条一起实施。
2. **修正过时或不准确的文字**：
    - L9：时间必须是 `timezone.utc`，`ZoneInfo("UTC")` 和其他零偏移时区一律拒绝；
    - L12：所有字符串字段（不只是主键）都不能为空字符串或全空格，与 `contracts.py` L123-125 一致；
    - L13：写清楚“只能使用 `as_of`、`observation_time` 之前已知的信息”目前只对 `gold.training_datasets` 有代码检查，其他 Gold 数据集只是约定；
    - L8：补充版本政策，说明**规则变化**（新增或收紧范围、枚举、行内规则）是否需要提升 `schema_version`。由 Analyst 提出方案，负责人确认后写入，并与 `docs/pr1/FOUNDATION_RULES.md` L18 写法一致；
    - L310-312：按“行级硬规则在 contract，跨行、跨文件检验在 PR4”重写校验边界；删除“以后应在 registry 中声明范围”的过时说法，改为描述现状。
3. **每个字段加 `description`**：在 JSON 中为每个字段写明含义、单位和计算方法（例如 `book_age_ms` 从何时开始算、`gap` 和 `recovery` 何时为 `true`、`imbalance` 和 `microprice` 的公式、`bids` 和 `asks` 每一档的结构、`side` 和 `status` 的取值）。生成的文档字段表中显示这些说明。
    - 依赖数据参数的定义（如 top-N 深度的 N、`rolling_volume` 的窗口长度）在 `description` 中只写“由特征参数决定”，不写具体数值（§5.1）。
4. **存储格式标注为计划**：L7 的 JSONL.zst、Parquet.zstd 标注为“计划，尚未实现”，在录制器 PR 中落实（§5.2）。

测试要求：修改 JSON 后不重新生成文档，L397 测试失败；重新生成后通过。

### 4.11 `docs/pr1/FOUNDATION_RULES.md`

1. L16：删除“直接构造的校验是后续工作，尚未实现”（`__post_init__` 已实现并有参数化测试）；按决定改写为 pydantic，并写明只有 `PipelineConfig` 可被环境变量覆盖、`.env` 存放敏感信息和机器级全局设置。
2. L59：时间必须是 `timezone.utc`，`ZoneInfo("UTC")` 和其他零偏移时区一律拒绝。
3. L18：版本政策与 §4.10 第 2 条（规则变化是否升 `schema_version`）合并处理，两份文档写法一致。
4. L32：补充“Bronze 路径包含接收身份；逐字节相同视为成功只适用于同一次写入的重试”（§4.7 第 4 条）。
5. L71：“N 默认 5”与 §5.1 对齐，写明 N 存放在特征参数中，默认值为 5。
6. §9 L106：更新“字段级契约、规则版本结构”等已部分确定的事项，链接到对应决定。
7. §5 L60：写明 point-in-time 检查分两层——contract 检查“可用时间 ≤ 观察时间”，构建训练集和回测时再检查“可用时间 ≤ 决策时间 − 延迟”；延迟放在实验配置中（§4.8 第 7 条）。

### 4.12 ADR 目录与 ADR-002

1. **新建 ADR 目录**：已完成（2026-11-09 文档整理时）。`docs/adr/ADR-001-v1-architecture.md` 已移入，`README.md`、`docs/README.md` 的引用已更新；ADR 的编号、标题和状态登记在 `docs/README.md`。
2. **保留 ADR-001 原文**：已接受的 ADR 不改写，只在开头状态处加一行“部分决定由 ADR-002 补充”，并链接过去。ADR-001 L14 只列出 bronze、silver、gold、quarantine；`recovery/` 在 ADR-002 中说明。
3. **新建 ADR-002**，记录本次代码阅读中做出的架构级决定，按主题分节，每节写清背景、决定、理由和后果：
    - 数据持久性：新增 `DATA_ROOT/recovery/`（冲突和残留 partial 不丢弃）、锁文件、父目录 `fsync`、外接硬盘支持；流式录制使用分段追加日志；
    - 数据契约：schema、范围规则和行内规则全部以 `src/data_schema/` 下的 JSON 为唯一来源，`docs/SCHEMAS.md` 由脚本生成；行级硬规则在 contract，跨行、跨文件检验在 PR4；时间严格要求 `timezone.utc`；
    - point-in-time：改用可用时间，检查分两层（contract 与训练集构建/回测），延迟放在实验配置中；
    - 配置：改用 pydantic；只有 `PipelineConfig` 可被环境变量覆盖；`.env` 存放敏感信息和机器级全局设置；数据参数（如 N、窗口长度）放在 `src/config/profiles/features/`，参数变化产生新 `data_version`；
    - adapter：统一规范化错误、溯源来自 Bronze 外壳、补齐 Silver 规范化方法；
    - 日志：结构化日志（§4.6）。
    - ADR-002 的内容以本文件中的决定为准；Analyst 实施时如有方案调整，ADR-002 写最终结果。

### 4.13 lint、格式与 `README.md`

阅读时按 README 实际运行：`uv sync --locked --group dev` 成功；`uv run pytest tests/ -v` 189 passed（5 条 warning 来自旧 analysis 测试的 matplotlib）；`uv run ruff check .` 7 个错误；`uv run ruff format --check .` 报告需要重新格式化。

1. **修复 lint 和格式**：
    - `src/__main__.py` L7-10、`src/cli.py` L33-36 的中文笔记**保留**（负责人确认），改成以 `# ` 开头的正式注释，去掉只有空格的空行和行尾空格（W291、W293）；必要时整理措辞（例如 `__main__.py` 中的 “src.cli chekc” 拼写）。
    - 运行 `uv run ruff format .`，包括 `tests/test_pipeline_foundation.py` L92 被折成多行的函数签名。
    - 修复后 `ruff check`、`ruff format --check`、`pytest` 全部通过。
2. **随各项决定同步更新 README**：
    - L39 “PR1 没有新增依赖” → 写明新增 pydantic（同时更新 `pyproject.toml` 和 `uv.lock`）；
    - L74 `PIPELINE_LOG_LEVEL` → 用于结构化日志；
    - L96、L98-105 → 增加 `recovery/` 区和锁文件说明；
    - L107 → 写入冲突的新行为（逐字节相同视为成功；不同则新数据进入 recovery 并报错）；
    - L111 → Gold 产品增加 `gold.market_1m`；文档由脚本从 JSON 生成；point-in-time 两层检查；
    - L113 → adapter 方法和声明的最新数量与内容；
    - ADR 链接已在文档整理时改为 `docs/adr/`，新增 ADR-002 后无需再改 README。
3. **补全启动错误表**（L82-92，负责人确认）：增加 `DATA_ROOT is not a directory`、`Cannot check free disk space`、`DATA_ROOT has no existing parent`、路径含 NUL 字符、`PIPELINE_LOG_LEVEL` 或 `DATA_MIN_FREE_GIB` 不合法，以及新增的“外接硬盘未挂载”错误；每项写明处理方法。错误信息以实施后的实际文本为准。
4. **改写上游联系方式**：保留 L146-160 的引用文献和 `LICENSE`；L162 改写为说明这些引用和数据集来自上游项目，不再以本仓库名义请读者联系上游作者。（文档整理时文档列表多了一行，这两处现为 L147-161、L163。）
5. **README 与配置文档去重（负责人确认记为待办，2026-11-09）**：`README.md` 的配置章节（配置项表、优先级、各入口的检查、启动错误表）与 `src/config/README.md` 大量重复。README 只保留快速上手（复制 `.env`、设置 `DATA_ROOT`、运行 `check`）和指向 `src/config/README.md` 的链接；详细配置说明以 `src/config/README.md` 为准。第 2、3 条中属于配置细节的更新（例如补全启动错误表）相应写进 `src/config/README.md`。

### 4.14 `CHANGELOG.md`

- 全部待办实施后，按最终结果**重写** `## Unreleased`（负责人确认）：按 Added / Changed 等分组，只写使用者看得到的变化，不写 PR 内部的逐次修复；统一语言和列表格式（目前 L5 为中文、其余为英文，L5 后多一个空行把列表断成两段）；补上 `python -m src check`、`arrow_schema` 等面向使用者的功能，以及本次阅读的所有决定（pydantic、recovery 区、`market_1m`、两层 point-in-time、ADR-002、结构化日志、adapter 接口变化、`schema_version` 变化等）。
- 改正不准确的措辞（负责人确认只改准确，不另写防护范围文档）：
    - L7 “directory permissions”：`ScopedWriter` 是程序层面的边界，不是操作系统权限隔离，改为 “scoped writer boundaries per data layer” 一类的准确说法；
    - L12 “document the scoped writer threat model”：仓库中相关内容只有 `src/data_io/layout.py` L54 的一行代码注释，改为准确描述。

### 4.15 更新 `docs/pr1/PLAN.md` 的状态

- 拆分表的状态与实际不符：第 3 块（layout）和第 8 块（adapter）已有代码，表中仍为“待执行”；第 2 块写“完整依赖测试待运行”，本次阅读已多次用 `uv run pytest` 实际运行通过。
- L37 “当前环境缺少 `uv`”已过时。
- 按本次代码阅读的结果更新每块的状态，并注明各块待 Analyst 修改的内容（链接到本文件对应章节）；第 7 块对应新增 `gold.market_1m` contract。

## 5. 未来设计要求（不在 PR1 实施）

进入对应 PR 时，在该 PR 的任务说明中引用这里的要求。

### 5.1 Gold 特征参数（负责人提出，2026-11-09）

- 负责人确认：top-N 深度的 N、`rolling_volume` 的窗口长度等是**数据相关的参数**，不写死在 schema 或代码中，需要有专门的存放位置。`docs/pr1/FOUNDATION_RULES.md` L71 规定 N 默认为 5。
- 存放位置（Reporter 建议，负责人已确认）：
    - **参数本身**放在 `src/config/profiles/features/`（例如 `market_1s_v1.json`），由对应的 pydantic 模型（例如 `src/config/models/features.py`）校验，Gold 构建任务的 job 配置引用这个 profile。这符合 `src/config/developing.md` 中 profiles“可复用配置零件”的定位。
    - **不放在 schema JSON 中**：schema 描述“数据长什么样”，同一个字段结构可以用不同参数计算；参数变化不改变字段结构。
    - **每份 Gold 数据都要能查到它用的参数**：解析后的参数随 run record 保存，并写入 Gold 文件的 manifest；参数变化时生成新的 `data_version`（对应 PROJECT.md §5 Gold 路径中的 `<data_version>`），不同参数的数据不混在同一版本中。
- 按 developing.md 第 10 条，PR1 不预建 `profiles/features/` 或对应模型；在实现 Gold 特征的 PR 中，有真实调用方时再创建。

### 5.2 流式录制使用分段追加日志（负责人确认，2026-11-09）

- `ScopedWriter.write_new(bytes)` 是“整个文件一次写完、原子发布”的模型，只适合批量回填。WebSocket 盘中录制若先缓存在内存再一次写出，断电时未写出的部分必然丢失。
- 要求：录制器 PR 采用分段追加日志。逐条追加到当前段文件，每条记录带长度或 checksum，并定期 `fsync`；段满后关闭并发布。崩溃或断电后逐条校验，恢复到最后一条完整记录，最多丢失最后一个 `fsync` 间隔内的数据。
- 段文件的发布、锁文件、recovery 区与 §4.7 的方案保持一致。
- Bronze 的存储格式：`docs/SCHEMAS.md` L7 写的 JSONL.zst 或 Parquet.zstd 目前没有任何代码实现，`pyproject.toml` 也没有 zstandard 依赖。PR1 中在文档里标注为“计划”（§4.10 第 4 条）；录制器 PR 确定段文件的具体格式和压缩方式，并与此处的分段追加日志设计对齐。

### 5.3 数据 validation 模块（负责人提出，2026-11-09）

`agent/PROJECT.md` §9.2 已将 PR4 规划为 “Validation, quarantine, quality reports”，§4 要求 Silver 之前有独立验证关口，并要求回测报告说明数据问题。负责人在此基础上明确要求，未来的数据 validation 模块包含以下部分：

1. **数据检验**：
    - **完整性**：时间覆盖与缺口、序列号缺口、重复、缺失字段、文件与 manifest 及 checksum 是否一致。
    - **合理性**：价格和数量范围、时间顺序、跨表一致性、异常值等。
    - 分工（负责人确认）：只看一行就能判断的硬规则放在 `src/data_schema` 的 contract 中；需要跨行、跨文件才能判断的检验放在本模块。
2. **数据质量报告**：自动生成，并**持久保存**。机器可读部分使用 JSON；按 PROJECT.md §6 的约定，同时默认生成人可读的 Markdown。报告关联数据集、时间范围、运行 ID 和所用规则版本。
3. **人工处理数据工具**：对 quarantine 和 `recovery/` 中的数据进行审核、修复、放行（附 caveat）或拒绝；每次操作都留下可追溯的记录，不静默改写原始数据。
4. **报告记录工具**：登记和查询历史质量报告及人工处理记录，例如某数据集、某时间段的最新报告，或某条 caveat 的来源。
5. **与回测衔接**：回测开始前，自动调取所用数据快照对应的质量报告；没有报告或报告已过期时，自动生成。回测报告中引用质量报告，并列出相关问题和 caveat。

- 进入 PR4 和回测相关 PR 时，同步更新 `agent/PROJECT.md` 的相关章节；更新 PROJECT.md 需先经负责人确认。
- 待明确的问题，留到 PR4 设计时讨论：
    - 报告“过期”的判断标准，例如数据或规则版本变化；
    - 报告保存在 `DATA_ROOT/manifests/` 下还是单独目录；
    - 人工处理工具的形式（CLI 还是其他）；
    - 质量政策与 `config/profiles/quality/` 的关系。

### 5.4 point-in-time 第二层检查（负责人确认，2026-11-09）

- 训练集构建和回测时检查 `max_feature_available_at <= observation_time - information_delay`；延迟默认 1 分钟，放在 backtest/实验配置中，并记录到 manifest 和 run record（第一层见 §4.8 第 7 条）。
- 历史回补数据的可用时间须使用经负责人批准并记录的假设。

### 5.5 旧 indexer 的 `.env` 设置（负责人确认，2026-11-09）

- `.env.example` 和本机 `.env` 中的 `POLYMARKET_START_BLOCK` 是旧 indexer 的任务参数，不是敏感信息，也不是机器级设置（`.env` 定位见 §4.1 第 4 条）。迁移旧 indexer 时移入对应的配置 JSON，并同步更新 `.env.example`。
