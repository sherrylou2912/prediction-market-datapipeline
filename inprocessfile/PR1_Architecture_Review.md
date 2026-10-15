# PR 1 架构与配置重构审查报告

日期：2026 年 10 月 14 日

对象：项目负责人及后续 PR 的开发者

范围：仅 PR1，涵盖配置、数据目录、行级契约、venue 接口和 mock 链路；不包含真实下载、真实交易场所 API 或 PostgreSQL 表。后续工作何时开始由项目负责人决定。

## 结论与审查重点

本次修改把新管线代码直接放在 `src/` 下，按职责分成 `config/`（设置与启动检查）、`data_schema/`（数据格式）、`data_io/`（目录与写入接口）、`adapters/`（交易场所接口与假数据实现）。目前没有真实数据 loader。可以把这套基础想成仓库：配置决定仓库建在哪里、留多少空间；数据契约规定入库单据有哪些栏位；writer 决定哪个岗位能把文件放进哪个库区；adapter 规定交易场所将来怎样交货。非敏感的可编辑默认值放在 `src/config/defaults/storage.json` 和 `src/config/defaults/runtime.json`，环境变量名称列在 `.env.example`。本机还创建了受 Git 忽略的 `.env`，其凭据项保持空白。每次读取配置时按“进程环境变量 > 本机 `.env` > JSON 默认值”合并取值。通用 `check` 只看设置和路径；只读任务检查目录可读；只有写入任务才检查剩余空间和实际写入能力。

writer 只接受所属层的根目录相对路径，拒绝跨层、绝对路径、`..`、符号链接越界和覆盖已有文件。写入时先生成临时文件并同步文件内容，再用独占硬链接发布目标名；普通写入或发布失败不会留下目标文件。**这还不是完整的数据事务**：目录元数据持久化、manifest 登记、checkpoint 推进均未在 PR1 实现。文件存在不能等同于“数据已完成登记并可安全续跑”。

下面逐一说明每个函数**什么时候会被调用、用大白话说它做什么、测试确实证明了什么**。最终测试数量见文末复核结果。模拟故障测试不等于已经模拟全部生产故障。

## 文件与配置边界

| 位置 | 用途 | 是否进入 Git |
| --- | --- | --- |
| [`src/config/defaults/storage.json`](../src/config/defaults/storage.json) | 写入任务的默认最小剩余空间，当前为 200 GiB | 是 |
| [`src/config/defaults/runtime.json`](../src/config/defaults/runtime.json) | 默认日志级别，当前为 `INFO` | 是 |
| [`.env.example`](../.env.example) | 所有当前和预留环境变量的名称；不放真实密钥 | 是 |
| 本机 `.env` | 实际 `DATA_ROOT` 与将来的密钥；当前凭据为空 | 否，受 `.gitignore` 忽略 |
| [`src/config/settings.py`](../src/config/settings.py) | 读取 JSON、`.env` 和进程环境，形成非敏感配置对象 | 是 |
| [`src/config/validation.py`](../src/config/validation.py) | 校验配置取值、磁盘空间和目录可写性 | 是 |
| [`src/data_io/layout.py`](../src/data_io/layout.py) | 创建六层目录并限制 writer 写入范围 | 是 |
| [`src/data_schema/contracts.py`](../src/data_schema/contracts.py) | 将版本化 schema 转为 Arrow schema，并校验单行 | 是 |
| [`src/adapters/base.py`](../src/adapters/base.py) | 规定 venue 元数据和八个操作 | 是 |
| [`src/adapters/mock.py`](../src/adapters/mock.py) | 无网络的固定样本链路 | 是 |

Bronze 是保留来源原貌的记录，Silver 是整理成统一格式且经过行级检查的记录，Gold 是用于分析的成品。`quarantine/` 预留用于隔离可疑资料，`manifests/` 预留用于记录文件清单。目录创建成功不表示这些后续流程已经实现。

`DATA_ROOT` 不在 JSON 中给默认路径，是为了避免把研究数据误写到仓库或系统盘。`PIPELINE_CONFIG_DIR` 可指向另一套绝对路径的配置目录。环境变量 `DATA_MIN_FREE_GIB` 和 `PIPELINE_LOG_LEVEL` 可覆盖 JSON；空覆盖值回退到 JSON。进程环境中的同名键优先于 `.env`。`KALSHI_API_KEY_ID`、`KALSHI_PRIVATE_KEY_PEM`、`POLYMARKET_API_KEY`、`POLYMARKET_API_SECRET`、`POLYMARKET_API_PASSPHRASE` 和 `DATABASE_URL` 仅预留，PR 1 不读取它们，也不调用任何真实 API 或数据库。`POLYGON_RPC` 与 `POLYMARKET_START_BLOCK` 是旧 indexer 已使用的键；后者保留可解析的数值默认值。

### 包与依赖是否受控

**依赖受控，分发打包尚未配置。** 所需库的**名字**写在根目录 [`pyproject.toml`](../pyproject.toml)：`[project].dependencies` 是运行时库，例如 `python-dotenv` 和 `pyarrow`；`[dependency-groups].dev` 是测试与格式检查用的 `pytest` 和 `ruff`。[`uv.lock`](../uv.lock) 保存解析后的具体版本与间接依赖。在仓库根目录运行 `uv sync --locked --group dev`，会按锁定版本建立本机 `.venv`；`--locked` 避免安装时意外改锁文件。本次没有新增依赖。`pyproject.toml` 目前没有 build backend，因此不能把此仓库视为已配置好的 wheel 发布包；在仓库根目录通过 `python -m src` 和测试配置导入 `src`。具体操作在 [`README.md`](../README.md)。

## 配置函数与逐项验证

| 函数 | 未来在什么情况调用；用大白话说做什么 | 对应测试及实际断言 |
| --- | --- | --- |
| `_read_json_settings` | 每次启动读空间门槛或日志默认值时，由 `PipelineConfig.load` 调用；它像检查表格格式一样，只接受约定的一个键及正确类型。 | `test_config_files_reject_malformed_or_unexpected_values` 分别断言缺失文件、坏 JSON、布尔值冒充整数、额外键和非法日志级别会报清晰错误。 |
| `_read_environment` | 每次启动合并本机 `.env` 与当前命令的环境设置时调用；先读本机值，再让命令显式指定的同名值覆盖，不把密钥装进配置对象。 | `test_split_config_files_and_environment_precedence` 断言三级优先级，并确认模拟密钥不出现在配置对象的表示中；指定不存在的 `.env` 由配置文件错误测试断言。 |
| `PipelineConfig.load` | 启动命令或未来任务需要完整设置时调用；它找到两个 JSON，把各处设置合在一起，形成不可随意修改的配置对象。 | 上述优先级测试、`test_config_directory_environment_override` 和错误配置测试覆盖默认值、覆盖值、绝对配置目录与非法输入。 |
| `PipelineConfig.from_env` | 现有调用者只想从环境获取配置时调用；它是简化入口，实际交给 `load`，没有另一套独立规则。 | `test_config_requires_absolute_data_root_and_reports_unwritable`、`test_config_checks_disk_space_and_environment_overrides` 使用该入口。 |
| `PipelineConfig.validate_for_read` | 未来只读 backtest 等任务开始读已有数据时调用；只确认目录存在且可读，不要求空闲空间或写权限。 | `test_read_checks_do_not_probe_write_capacity_or_create_directories` 用“若碰空间或试写就失败”的替身证明无写入检查；缺目录和拒绝读取由 `test_read_check_requires_existing_readable_directory` 验证。 |
| `PipelineConfig.validate_for_write` | 未来采集或生产任务准备写新文件时调用；只有这类任务才要求足够空间和真正可写的目录。 | 磁盘不足和不可写测试证明会拒绝；`test_write_preflight_creates_root_before_layout` 证明新目录能被建立并交给六层布局。 |
| `parse_data_root` | 读到 `DATA_ROOT` 后调用；防止空值或相对路径把文件误放在项目目录等意外位置。 | `test_config_requires_absolute_data_root_and_reports_unwritable` 对两类错误做断言，成功路径由配置加载测试覆盖。 |
| `parse_min_free_gib` | 读到最小剩余空间设置后调用；把它变成非负整数，负数和布尔值不算合法门槛。 | `test_config_checks_disk_space_and_environment_overrides` 验证环境覆盖与负数；错误配置测试拒绝 JSON 中的布尔值。 |
| `parse_log_level` | 读到日志设置后调用；把 `debug` 统一成 `DEBUG`，只允许五个标准等级。 | `test_split_config_files_and_environment_precedence` 验证 `DEBUG` 覆盖；错误配置测试拒绝 `TRACE`。 |
| `check_configured_root` | 用户运行通用 `check`，或读写任务开始正式检查前调用；只确认配置路径本身适合当目录。尚未创建的目录会被报告为待创建，已存在但其实是文件的路径会被拒绝。 | `test_pipeline_cli_checks_configuration_without_preparing_layout` 检查缺目录不创建、普通文件会失败；只读无副作用测试证明不探测空间和写权限。 |
| `validate_read_data_root` | 只读任务启动时由 `validate_for_read` 调用；要求目录已经存在，并实际尝试列出目录内容以确认能读。 | `test_read_check_requires_existing_readable_directory` 分别检查缺目录和模拟读取权限错误；只读无副作用测试证明不查看空间。 |
| `validate_write_data_root` | 写入任务启动时由 `validate_for_write` 调用；查看空闲空间、按需创建数据根目录，再真正尝试创建临时文件。 | `test_config_checks_disk_space_and_environment_overrides` 模拟 3 GiB 可用空间却要求 4 GiB；不可写测试模拟 `PermissionError`；新目录写入前检查测试验证创建成功。 |

磁盘不足和权限失败通过注入故障测试，未以真实磁盘填满或修改系统目录权限的方式测试。默认 200 GiB 只在写入任务启动前生效；通用检查和只读任务不会因当前空闲空间低于此值而失败。测试仅在临时目录将写入门槛设为 0。

## 目录与 writer 函数逐项验证

| 函数 | 未来在什么情况调用；用大白话说做什么 | 对应测试及实际断言 |
| --- | --- | --- |
| `DataLayout.create` | **写入前检查通过后**由写入任务调用；在选定数据盘建立六个库区，若库区被换成指向别处的符号链接就拒绝使用。通用 `check` 和只读任务不调用它。 | `test_layout_creates_layers_and_writer_enforces_scope` 比对六个目录；`test_layout_rejects_symlinked_layer` 验证链接层被拒绝；`test_write_preflight_creates_root_before_layout` 验证调用顺序。 |
| `DataLayout.writer` | 某岗位准备保存文件时调用，例如 collector 保存原始资料；它发给岗位一把只能进入指定库区的“钥匙”。 | `test_layout_creates_layers_and_writer_enforces_scope` 拒绝字符串角色；`test_each_writer_is_bound_to_its_layer` 对六个角色逐一验证。 |
| `ScopedWriter.write_new` | 未来任务已有文件内容要保存时调用；先检查路径属于自己的库区，再写临时文件、同步内容，最后用不覆盖旧文件的方式公布。 | 目录测试拒绝跨层、绝对路径、`..` 与覆盖；`test_writer_rejects_symlink_escape` 拒绝嵌套符号链接且不碰外部目录；`test_writer_cleans_temporary_file_on_publish_failure` 注入发布失败并确认无残留目标或临时文件；六角色测试验证各自正反路径。 |

六把“钥匙”的对应关系是 `IMPORTER→imports`、`COLLECTOR→bronze`、`NORMALIZER→silver`、`PRODUCT→gold`、`VALIDATOR→quarantine`、`REGISTRY→manifests`。这些约束由应用接口执行，不是操作系统级的访问控制。测试没有模拟攻击者在检查与发布之间并发替换目录，也没有模拟断电。文件内容在发布前已 `fsync`，但目录元数据、manifest 和 checkpoint 的一致提交未在 PR1 实现。

## 数据契约函数逐项验证

[`docs/SCHEMAS.md`](../docs/SCHEMAS.md) 的 JSON 区块定义 1 个 Bronze、8 个 Silver、4 个 Gold 数据集；代码中的 [`schema_registry.json`](../src/data_schema/schema_registry.json) 与文档逐项相等。版本、字段顺序、类型、可空性和主键都接受测试检查。

| 函数 | 未来在什么情况调用；用大白话说做什么 | 对应测试及实际断言 |
| --- | --- | --- |
| `get_contract` | 需要处理某种数据，例如 `silver.trades`，先查它的规则时调用；按名称交出字段清单和主键，未知名称会报错。 | `test_schema_document_matches_code_registry` 遍历 13 个数据集并断言未知名称报错。 |
| `arrow_schema` | 准备把记录交给 Arrow 或 Parquet 时调用；把人读的规格变成机器理解的字段顺序、类型、可空性和版本标签。 | 同一测试比较 13 个 schema 的字段顺序和可空性；mock 链路与 Gold 秒级测试用实际 Arrow 表转换验证可写类型。 |
| `_parse_json` | 某栏位要求 JSON 文本时由 `validate_record` 调用；检查文字真的符合 JSON 格式。 | `test_bronze_and_silver_validation_rejects_bad_rows` 用坏 JSON 和 `NaN` 输入触发。 |
| `_parse_json` 内的 `reject_constant` | 解析器遇到 `NaN` 等非标准数值时自动调用；打断解析，避免假装这是一条合格记录。 | 上述 `NaN` 测试触发该回调并收到契约错误。 |
| `validate_record` | 一条原始、标准化或产品记录准备进入下一步时调用；像检查单据一样，核对是否缺栏、多栏、错版本、错类型、非 UTC 时间、越界价格、错误 JSON 或使用未来才知道的训练特征。 | Bronze/Silver 异常测试验证多种拒绝路径；`test_gold_one_second_requires_aligned_utc_time` 验证整秒、价格范围及 Arrow 转换；`test_training_features_obey_point_in_time_contract` 验证未来特征与空 manifest 列表被拒绝。mock 三类标准化结果再次调用该函数。 |

这是**行级**验证；跨文件主键唯一性、时间覆盖、关系完整性和源特有质量规则仍由计划中的 PR 4 校验关口承担。当前测试证明文档与注册表一致，并不等于已证明真实交易场所数据符合契约。

## Venue 接口与 mock 函数逐项验证

当将来接入一个真实交易场所时，开发者先要实现 [`src/adapters/base.py`](../src/adapters/base.py) 中的接口。`VenueAdapter.metadata` 要交代八件事：支持什么能力、API/协议版本、记录主键、翻页与续跑规则、限速、时间语义、数值精度、专属校验规则。[`AdapterMetadata.__post_init__`](../src/adapters/base.py) 在创建这份“场所说明书”时确认八项均非空、限速大于零；[`MockVenueAdapter.metadata`](../src/adapters/mock.py) 每次被询问时给出一套固定的假场所说明。`test_mock_adapter_discover_to_normalize_chain` 断言有效声明可用，同时用空规则和零限速分别验证拒绝。`VenueAdapter.metadata` 和八个抽象方法使不完整实现无法实例化；该测试直接尝试实例化抽象类，预期得到 `TypeError`。

| 接口与 [mock 实现](../src/adapters/mock.py) | 未来什么时候调用；用大白话说做什么 | 对应测试 |
| --- | --- | --- |
| `discover_markets` | 首次找某个 venue 有哪些市场时调用；取一页市场目录并说明有没有下一页。mock 返回一个固定市场。 | `test_mock_adapter_discover_to_normalize_chain` 验证市场 ID 与无下一页游标。 |
| `backfill_markets` | 要补过去一段时间的市场资料时调用；按时间范围索取历史市场。mock 返回同一固定页。 | 同一测试比较回填页与发现页。 |
| `backfill_trades` | 要补一段时间的成交时调用；取原始成交供后续整理。mock 返回一条固定成交。 | 同一测试取得样本并交给 `normalize_trade`。 |
| `fetch_settlements` | 要获取市场最终结算资料时调用；mock 明确返回空页，表示这套样例没有结算数据。 | 同一测试断言空元组。 |
| `stream_market_data` | 要持续收取指定市场的盘口变化时调用；mock 对 `mock-1` 产生一条固定变更。 | 同一测试读取一条事件并检查源序号。 |
| `normalize_market` | 拿到场所自己的市场资料后调用；翻译成统一 Silver 市场格式，带上来源指针并检查字段。 | 同一测试调用校验器并写入内存 Arrow 表。 |
| `normalize_trade` | 拿到场所自己的成交资料后调用；把价格和数量转成准确小数，再做成统一 Silver 成交记录。 | 同一测试断言价格为 `0.65` 并转换 Arrow 表；异常测试再验证非法价格拒绝。 |
| `normalize_book_event` | 收到盘口变更后调用；做成带来源序号的统一 Silver 盘口增量。 | 同一测试断言序号及契约校验通过。 |

mock 的回填不模拟真实分页、限速、断线或 API 版本切换；它验证接口可调用、数据可进入统一契约，不代表 Kalshi 或 Polymarket 接入已完成。

## 启动入口与测试证据

[`src/cli.py`](../src/cli.py) 的 `main` 是用户运行 `python -m src check` 时真正调用的函数：读设置，只确认配置路径可作为目录；不查空间、不试写、不建六层目录。路径尚未创建时，它说明写入任务将来会创建；路径是普通文件时，它清楚报错。失败返回状态码 2，成功返回 0。[`src/__main__.py`](../src/__main__.py) 只负责把模块命令交给 `main`，没有另一套启动逻辑。`test_pipeline_cli_checks_configuration_without_preparing_layout` 覆盖缺失 `DATA_ROOT`、已存在目录、待创建目录和错误文件路径，并设置“若查询空间或试写就失败”的测试替身；`test_module_entry_point_runs_in_a_new_process` 用新 Python 进程验证用户实际会运行的命令。

可复核的命令：

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest tests/test_pipeline_foundation.py -q
.venv/bin/pytest tests/ -q
```

本轮修改后，定向测试为 **25 passed**，完整测试为 **143 passed，5 warnings**；`ruff check` 和 `ruff format --check` 均通过。5 条 warning 来自现有第三方库及旧分析测试，没有失败测试。本地以现有 `.venv` 直接执行工具；README 给出常规用户的 `uv` 安装与运行命令。更改前的 `commit0` 为 `ce97ac0`，原 PR1 实现提交 `commit1.1` 为 `3d3752e`；目录结构调整提交为 `36b80a3`。本轮反馈修改以独立提交交付，便于审阅差异。

## 负责人验收建议

1. 打开 [`README.md`](../README.md) 按“Configure the pipeline”设置本机 `.env`，确认 `DATA_ROOT` 指向预期磁盘，且绝不把真实凭据加入 `.env.example`。
2. 审查两个 JSON 文件中的默认值。生产写入空间阈值当前是 200 GiB；低于此值会阻止写入任务，但不会阻止只读任务或通用检查。
3. 运行上述四条检查命令，确认定向测试、全量测试与格式检查结果。
4. 审查 [`docs/SCHEMAS.md`](../docs/SCHEMAS.md) 中的字段、单位、主键和可空性。后续 PR 必须沿用或显式升级版本。
5. 不把 `write_new` 成功返回解释为 manifest 已登记或 checkpoint 已安全推进；这些能力尚未在 PR1 实现。
