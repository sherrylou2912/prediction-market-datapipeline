# PR1 架构与配置验收报告：按文件逐项核查

日期：2026 年 10 月 14 日

读者：项目负责人
范围：仅 PR1。没有真实下载、真实 venue API、真实 backtest 入口或 PostgreSQL 表；何时开始 PR2 由项目负责人决定。

## 阅读方法与总体结论

下文固定按 **文件名 → 该文件包含的函数 → 函数做什么及何时调用 → 每个函数的测试** 排列。测试名均指向 [`tests/test_pipeline_foundation.py`](../tests/test_pipeline_foundation.py)。写明“间接覆盖”的地方，表示测试通过上层函数走到了它，并非单独调用该函数；这不能被理解为所有异常分支都已测完。

本次基础把配置、数据格式、写入边界和 venue 接口分别放在 `src/config/`、`src/data_schema/`、`src/data_io/`、`src/adapters/`。通用 `python -m src check` 只看配置和路径，不查空间、不试写、不建目录。将来的只读任务调用只读检查；将来的写入任务才调用空间和写入检查。PR1 提供这两种接口，尚无真实任务调用它们。

| 非函数文件 | 作用 |
| --- | --- |
| [`src/config/defaults/storage.json`](../src/config/defaults/storage.json) | 写入任务允许开始前要求的最小空闲空间，默认 200 GiB；只读任务不因空间低于该值而停止。 |
| [`src/config/defaults/runtime.json`](../src/config/defaults/runtime.json) | 默认日志级别 `INFO`；PR1 只读取和校验，还没有把日志级别接入实际日志输出。 |
| [`.env.example`](../.env.example) | 当前与预留环境变量的名称；没有真实密钥。本机 `.env` 受 Git 忽略。 |
| [`docs/SCHEMAS.md`](../docs/SCHEMAS.md) | 人读的 Bronze、Silver、Gold v2 数据契约；程序版位于 [`schema_registry.json`](../src/data_schema/schema_registry.json)。 |
| [`pyproject.toml`](../pyproject.toml) 与 [`uv.lock`](../uv.lock) | 前者列必需库名称及开发工具，后者锁定解析版本。本次没有增加依赖；详细安装步骤见 [`README.md`](../README.md)。 |

配置覆盖顺序为“进程环境变量 > 本机 `.env` > 两个 JSON 默认值”。`DATA_ROOT` 没有默认数据位置，必须由用户设置绝对路径。预留的 Kalshi、Polymarket 凭据和 `DATABASE_URL` 在 PR1 不被使用。

## 文件：[`src/config/settings.py`](../src/config/settings.py)

**文件职责：**把 JSON、`.env` 和当前进程环境中的设置合成一份非敏感配置，交给启动命令或未来任务。它不访问真实 venue，也不写数据。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `_read_json_settings` | `PipelineConfig.load` 读取 `storage.json` 或 `runtime.json` 时调用。像检查表格模板一样，只接受约定的单个键和正确类型。 | `test_config_files_reject_malformed_or_unexpected_values` 分别制造缺文件、损坏 JSON、布尔值冒充整数、额外键，确认报配置错误。非法日志级别由后续 `parse_log_level` 拒绝，不是本函数直接拒绝。 |
| `_read_environment` | 每次加载配置时调用。先读本机 `.env`，再用当前命令的环境变量覆盖同名设置。 | `test_split_config_files_and_environment_precedence` 给三层来源不同值，断言最终优先级；同时确认模拟密钥未进入 `PipelineConfig` 的文字表示。`test_config_files_reject_malformed_or_unexpected_values` 检查显式指定不存在的 `.env` 会报错。测试经 `load` 间接调用它。 |
| `PipelineConfig.load` | 启动命令或未来任务需要完整设置时调用。确定配置目录、合并覆盖值，再得到数据根目录、写入空间门槛和日志级别。 | `test_split_config_files_and_environment_precedence` 检查三级覆盖和 JSON 默认值；`test_config_directory_environment_override` 检查可切换绝对配置目录、拒绝相对配置目录；`test_config_files_reject_malformed_or_unexpected_values` 检查坏文件。 |
| `PipelineConfig.from_env` | 调用者只想用默认配置目录、从环境拿设置时调用；这是 `load` 的简化入口。 | `test_config_requires_absolute_data_root_and_reports_unwritable`、`test_config_checks_disk_space_and_environment_overrides`、`test_read_checks_do_not_probe_write_capacity_or_create_directories` 等直接使用此入口，再检查得到的配置及后续行为。 |
| `PipelineConfig.validate_for_read` | 将来的只读 backtest 在开始读已有数据之前调用。只要求数据目录存在、可读，不关心是否还有 200 GiB 空位。 | `test_read_checks_do_not_probe_write_capacity_or_create_directories` 把空间查询和试写替换为“调用就失败”，确认只读检查没有触碰它们；`test_read_check_requires_existing_readable_directory` 检查缺目录与读取被拒；磁盘不足和不可写模拟测试也确认读取可以继续。 |
| `PipelineConfig.validate_for_write` | 将来的采集或产品生成任务在写新文件之前调用。要求足够空闲空间、按需创建根目录，并真正试写。 | `test_config_checks_disk_space_and_environment_overrides` 模拟剩余 3 GiB、要求 4 GiB，确认阻止写入；`test_config_requires_absolute_data_root_and_reports_unwritable` 模拟试写被拒；`test_write_preflight_creates_root_before_layout` 确认可创建新根目录并接上六层布局。 |

## 文件：[`src/config/validation.py`](../src/config/validation.py)

**文件职责：**把原始设置变成合法值，并按任务性质检查数据路径。200 GiB 空间门槛只在写入前检查中使用。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `parse_data_root` | 加载 `DATA_ROOT` 时调用。拒绝空值和相对路径，避免把数据误写到当前工作目录。 | `test_config_requires_absolute_data_root_and_reports_unwritable` 分别断言未设置和相对路径报清晰错误；其他配置成功测试间接覆盖合法绝对路径。 |
| `parse_min_free_gib` | 加载空间门槛时调用。把文本变成非负整数，供未来写入任务使用。 | `test_config_checks_disk_space_and_environment_overrides` 验证文本 `4`、`0` 可以使用、负数被拒。JSON 中的布尔值在 `_read_json_settings` 就被拒，**当前没有单独测试直接传布尔值给本函数**。 |
| `parse_log_level` | 加载日志级别时调用。把 `debug` 统一成 `DEBUG`，只允许五个预设级别。 | `test_config_checks_disk_space_and_environment_overrides` 检查小写 `debug` 转成 `DEBUG`；`test_config_files_reject_malformed_or_unexpected_values` 检查 `TRACE` 被拒。 |
| `_nearest_existing_directory` | 通用检查和写入检查都会调用的内部助手。沿路径向上找到第一个已经存在的目录；如果碰到普通文件，就在查磁盘之前报错。 | `test_configured_root_rejects_file_ancestor_before_write_probe` 通过两个公开入口分别验证同一个非目录父路径被拒，并把磁盘查询替换为“调用就失败”；`test_write_preflight_creates_root_before_layout` 覆盖多级尚未创建的路径。没有单独直接调用私有助手。 |
| `check_configured_root` | 通用 `check` 命令，以及读写检查开始时调用。借助共享助手判断路径是否适合当目录；目标尚未存在可以通过，已是普通文件则报错。 | `test_pipeline_cli_checks_configuration_without_preparing_layout` 分别检查存在的目录、尚未创建的目录、普通文件；`test_configured_root_rejects_file_ancestor_before_write_probe` 检查更深一层的普通文件父路径；无副作用测试证明不探测空间或写权限。 |
| `validate_read_data_root` | 将来的只读任务通过 `validate_for_read` 调用。要求目录确实存在，并实际尝试列目录内容，以发现读权限问题。 | `test_read_check_requires_existing_readable_directory` 检查缺目录会失败，并模拟 `PermissionError` 检查错误说明；`test_read_checks_do_not_probe_write_capacity_or_create_directories` 检查成功且不探测写入条件。 |
| `validate_write_data_root` | 将来的写入任务通过 `validate_for_write` 调用。通过共享助手找到目标磁盘、查空位、按需建根目录、创建临时文件确认可写。 | `test_config_checks_disk_space_and_environment_overrides` 检查磁盘不足和低门槛成功；`test_config_requires_absolute_data_root_and_reports_unwritable` 模拟实际试写失败；`test_write_preflight_creates_root_before_layout` 检查新根目录被创建；非目录父路径测试确认查磁盘前拒绝。 |

空间不足与读写权限失败是测试中注入的故障，没有真的填满磁盘或修改系统权限。检查目录可读，也不能代替将来对某个具体数据文件的可读性检查。

## 文件：[`src/data_io/layout.py`](../src/data_io/layout.py)

**文件职责：**写入任务通过启动检查后创建六层目录，并限制每种 writer 只能写自己的层。只读任务和通用 `check` 不创建这些目录。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `DataLayout.create` | 写入任务拿到 `validate_for_write()` 返回的根路径后调用。创建 `imports`、`bronze`、`silver`、`gold`、`quarantine`、`manifests`，拒绝被符号链接替代的层。 | `test_layout_creates_layers_and_writer_enforces_scope` 核对六个目录；`test_layout_rejects_symlinked_layer` 检查链接层被拒；`test_write_preflight_creates_root_before_layout` 验证从写入前检查到建层目录的调用顺序。 |
| `DataLayout.writer` | 有文件要保存时，任务按岗位申请 writer。`IMPORTER→imports`、`COLLECTOR→bronze`、`NORMALIZER→silver`、`PRODUCT→gold`、`VALIDATOR→quarantine`、`REGISTRY→manifests`。 | `test_each_writer_is_bound_to_its_layer` 对六个角色分别验证本层可写、别层不可写；`test_layout_creates_layers_and_writer_enforces_scope` 检查随意传字符串角色被拒。 |
| `ScopedWriter.write_new` | writer 真正公布一个新文件时调用。先验证路径，写临时文件并同步内容，再独占发布；同名文件不能覆盖。 | `test_layout_creates_layers_and_writer_enforces_scope` 检查正常写入以及跨层、绝对路径、`..`、同名覆盖被拒；`test_writer_rejects_symlink_escape` 检查不能通过链接写到外部；`test_writer_cleans_temporary_file_on_publish_failure` 模拟发布失败，检查目标与临时文件都没有留下；六角色参数化测试检查岗位边界。 |

这属于程序接口的边界，明确假设同机进程合作、只防意外路径错误；[`write_new` 的代码注释](../src/data_io/layout.py) 也写明它不防恶意进程在检查与发布之间并发替换目录。测试没有模拟恶意并发或突然断电。文件内容在发布前已同步，但 PR1 没有实现目录元数据、manifest 和 checkpoint 的一致提交。

## 文件：[`src/data_schema/contracts.py`](../src/data_schema/contracts.py)

**文件职责：**按 [`docs/SCHEMAS.md`](../docs/SCHEMAS.md) v2 校验单条记录，并提供 Arrow 格式。Bronze 保留来源原貌；Silver 是统一格式；Gold 是分析产品。共 1 种 Bronze、8 种 Silver、4 种 Gold。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `get_contract` | 处理某种数据前按名称取字段和主键规则，例如 `silver.trades`。 | `test_schema_document_matches_code_registry` 遍历全部 13 种数据，且断言未知名称报错。 |
| `arrow_schema` | 准备把合格记录交给 Arrow 或 Parquet 时，把字段顺序、类型、可空性和版本转成 Arrow schema。 | `test_schema_document_matches_code_registry` 核对 13 种数据的字段、可空性和版本；`test_gold_one_second_requires_aligned_utc_time` 与 `test_mock_adapter_discover_to_normalize_chain` 把样本实际转成 Arrow 表。 |
| `_parse_json` | `validate_record` 遇到要求 JSON 文本的字段时调用，识别损坏的 JSON。 | `test_bronze_and_silver_validation_rejects_bad_rows` 用坏 JSON 和 `NaN` 字符串检查拒绝，属于经 `validate_record` 的间接覆盖。 |
| `_parse_json` 内部的 `reject_constant` | JSON 解析器遇到非标准 `NaN` 等常量时自动调用，防止错误值混入。 | 上述 `NaN` 用例经 `_parse_json` 间接触发并得到契约错误；没有单独直接调用这个内部回调。 |
| `validate_record` | 一行 Bronze、Silver 或 Gold 数据进入下一步前调用。检查缺栏、多栏、类型、UTC 时间、数字精度和范围、JSON 形状；范围规则同时匹配数据集和字段，避免同名字段语义冲突。训练数据还防止使用观察时点之后才知道的特征。 | `test_every_dataset_accepts_a_populated_contract_row` 对全部 13 种数据集逐一送入填好值的记录；`test_silver_outcomes_accepts_text_label` 确认文字 `YES` 合法、把它改成小数会得到 `ContractError`；Bronze/Silver 异常测试检查坏 JSON、时间、额外字段、负数、价格和精度；Gold 秒级测试检查对齐和价格；训练数据测试检查未来特征、空 manifest 列表和越界小数标签；mock 链路检查市场、成交和盘口记录。 |

`test_schema_document_matches_code_registry` 直接断言文档中的 JSON 与程序注册表完全相等。此次发现 `silver.outcomes.label` 是展示文字，而 `gold.training_datasets.label` 是小数训练标签；原先只按字段名匹配概率规则，导致前者抛出未捕获的 `TypeError`。现已按“数据集 + 字段”限定范围规则，并用真实行验证所有 13 种数据集。但这些规则仍写在代码集合中：将来新增受范围约束的字段，若忘记同步集合，仍可能漏判。后续数据契约升级应将范围声明移入 schema registry，并测试新增字段的拒绝路径。现有全覆盖测试只证明 13 种数据集的**有效样本**能通过，未对每种数据集的全部异常分支逐一测试。当前仍是逐行验证；跨文件主键唯一性、时间覆盖和 venue 特有质量规则未在 PR1 实现。

## 文件：[`src/adapters/base.py`](../src/adapters/base.py)

**文件职责：**规定每个 venue 实现必须提供什么说明与函数。它定义接口，本身不下载数据。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `AdapterMetadata.__post_init__` | 创建 venue 的“说明书”时自动调用。要求能力、版本、主键、分页/续跑、限速、时间、精度、校验规则八项均非空，且限速为正。 | `test_mock_adapter_discover_to_normalize_chain` 取得 mock 的有效说明，并分别把规则改为空、限速改为零，断言失败。 |
| `VenueAdapter.metadata` | 上层任务查询 venue 能做什么、如何限速和续跑时使用；每个实现都必须提供。 | 同一测试确认不能直接实例化抽象 `VenueAdapter`，并读取 mock 的 `metadata`；这是接口完整性检查，没有逐项模拟真实 API。 |
| `VenueAdapter.discover_markets` | 首次列出某场所市场时必须由具体 adapter 实现。 | `test_adapter_missing_one_required_method_cannot_start` 单独移除本方法，确认实例化报错；mock 链路检查实际市场和游标。 |
| `VenueAdapter.backfill_markets` | 补历史市场资料时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路检查回填页与发现页相等。 |
| `VenueAdapter.backfill_trades` | 补历史成交时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路将返回的成交送入标准化。 |
| `VenueAdapter.fetch_settlements` | 获取结算资料时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路检查明确空页。 |
| `VenueAdapter.stream_market_data` | 持续接收选定市场盘口事件时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路检查一条事件及序号。 |
| `VenueAdapter.normalize_market` | 把场所市场资料翻译为统一 Silver 市场行时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路检查契约与 Arrow 转换。 |
| `VenueAdapter.normalize_trade` | 把场所成交翻译为统一 Silver 成交行时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路检查价格与 Arrow 转换。 |
| `VenueAdapter.normalize_book_event` | 把场所盘口事件翻译为统一 Silver 盘口行时必须实现。 | 同一参数化测试单独移除本方法并确认报错；mock 链路检查序号与契约。 |

现在八个抽象方法各有一个“只漏这个方法”的参数化测试，缺失时 Python 在实例化阶段抛出 `TypeError`。接口文档也明确要求：真实读取或标准化失败必须抛错，不能假装返回成功；空页只能表示来源确实没有记录。未来负责运行记录和 checkpoint 的代码还必须记录异常且不得推进进度。PR1 没有真实 adapter 或该运行层，因此**尚未测试真实异常如何被记录或隔离**。真实分页、断线、限速和 API 版本变化也未验证。

## 文件：[`src/adapters/mock.py`](../src/adapters/mock.py)

**文件职责：**用固定的内存样本证明上面接口可走通。不联网，也不代表 Kalshi 或 Polymarket 已接入。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `MockVenueAdapter.metadata` | 测试任务询问 mock 的能力和规则时返回八项固定声明。 | `test_mock_adapter_discover_to_normalize_chain` 读取声明并检查能力数量；无效声明通过 `AdapterMetadata.__post_init__` 测试拒绝。 |
| `discover_markets` | mock 开始发现市场时，返回一个固定市场及“无下一页”。 | 同一测试检查市场 ID 和 `next_cursor is None`。 |
| `backfill_markets` | 模拟补市场资料时，返回同一固定市场页。 | 同一测试断言回填结果与发现结果相等。 |
| `backfill_trades` | 模拟补成交时，返回一条原始成交样本。 | 同一测试取出样本，交给 `normalize_trade`，检查后续结果。 |
| `fetch_settlements` | 模拟取结算时，明确返回空页。 | 同一测试断言 `items == ()`。 |
| `stream_market_data` | 指定 `mock-1` 时产生一条盘口变化事件。 | 同一测试读取一条事件，交给 `normalize_book_event`，检查来源序号为 1。未单测其他市场 ID 的空流。 |
| `normalize_market` | 把固定原始市场转成 Silver 市场行，保留 Bronze 来源指针。 | 同一测试调用契约校验，检查市场 ID，并转成一行 Arrow 表。 |
| `normalize_trade` | 把价格和数量文字转成精确小数，生成 Silver 成交行。 | 同一测试检查价格 `0.65`，并转成一行 Arrow 表；`test_bronze_and_silver_validation_rejects_bad_rows` 基于该行制造越界价格。 |
| `normalize_book_event` | 把固定盘口事件转成 Silver 盘口增量。 | 同一测试检查来源序号为 1，并再次通过 `validate_record`。 |

## 文件：[`src/cli.py`](../src/cli.py) 与 [`src/__main__.py`](../src/__main__.py)

`src/cli.py` 中唯一的函数是 `main`。`src/__main__.py` 没有另写函数，只把 `python -m src check` 交给 `main`。

| 函数 | 做什么；什么场景会调用 | 每个函数的测试证据 |
| --- | --- | --- |
| `main` | 用户运行通用配置检查时调用。读取配置，只确认 `DATA_ROOT` 路径适合作目录；不查空闲空间、不试写、不创建目录。缺设置或错误路径返回状态码 2，正常返回 0。 | `test_pipeline_cli_checks_configuration_without_preparing_layout` 检查缺 `DATA_ROOT`、已有目录、待创建目录、普通文件；把磁盘查询与试写替换为“调用就失败”，证明没有写入检查。`test_module_entry_point_runs_in_a_new_process` 真正启动新 Python 进程执行模块命令，检查退出码和无 `bronze/` 目录。 |

## 验收结果与能力边界

在 Python 3.9.6 环境下，本轮运行：

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest tests/test_pipeline_foundation.py -q
.venv/bin/pytest tests/ -q
```

结果：Ruff 两项均通过；定向测试 **48 passed**；完整测试 **166 passed，5 warnings**。5 条 warning 来自已有第三方库与旧分析测试，没有失败测试。用户可按 [`README.md`](../README.md) 中的 `uv` 步骤复核。

现有 writer 只保证本次接口所述的路径与文件发布边界；它尚未把文件、manifest 和 checkpoint 组成一致事务。空间与权限故障由测试模拟，真实磁盘填满、断电、并发换目录、真实 venue API 和真实 backtest 都未在 PR1 验证。

本报告只覆盖 PR1 当前实现；真实适配器、数据库账本和跨文件校验尚未开始。
