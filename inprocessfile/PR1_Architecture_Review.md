# PR 1 架构与配置重构审查报告

日期：2026 年 10 月 14 日

对象：项目负责人及后续 PR 的开发者

范围：配置、数据目录、行级契约、venue 接口、mock 链路；不包含真实下载、真实交易场所 API 或 PostgreSQL 表。

## 结论与审查重点

本次修改把新管线代码集中在 `src/pipeline/`，把非敏感的可编辑默认值放在 `config/storage.json` 和 `config/runtime.json`，把环境变量名称集中列在 `.env.example`。本机还创建了受 Git 忽略的 `.env`，其凭据项保持空白。启动时按“进程环境变量 > 本机 `.env` > JSON 默认值”读取配置，然后检查 `DATA_ROOT`、剩余空间和实际写入能力。

writer 只接受所属层的根目录相对路径，拒绝跨层、绝对路径、`..`、符号链接越界和覆盖已有文件。写入时先生成临时文件并同步文件内容，再用独占硬链接发布目标名；普通写入或发布失败不会留下目标文件。**这还不是完整的数据事务**：目录元数据持久化、manifest 登记、checkpoint 推进必须由 PR 2 一起实现和验证。

本轮在 Python 3.9.6 环境中运行了 `ruff check`、`ruff format --check` 和完整 `pytest`，结果分别为通过、通过、**139 passed，5 warnings**。5 条 warning 来自已有第三方库或旧分析测试；没有失败测试。下面给出每个函数的职责和对应的可复核测试，避免把“运行过测试”误写成“所有生产故障均已模拟”。

## 文件与配置边界

| 位置 | 用途 | 是否进入 Git |
| --- | --- | --- |
| [`config/storage.json`](../config/storage.json) | 默认最小剩余空间，当前为 200 GiB | 是 |
| [`config/runtime.json`](../config/runtime.json) | 默认日志级别，当前为 `INFO` | 是 |
| [`.env.example`](../.env.example) | 所有当前和预留环境变量的名称；不放真实密钥 | 是 |
| 本机 `.env` | 实际 `DATA_ROOT` 与将来的密钥；当前凭据为空 | 否，受 `.gitignore` 忽略 |
| [`src/pipeline/config.py`](../src/pipeline/config.py) | 读取 JSON、`.env` 和进程环境，形成非敏感配置对象 | 是 |
| [`src/pipeline/config_validation.py`](../src/pipeline/config_validation.py) | 校验配置取值、磁盘空间和目录可写性 | 是 |
| [`src/pipeline/layout.py`](../src/pipeline/layout.py) | 创建六层目录并限制 writer 写入范围 | 是 |
| [`src/pipeline/contracts.py`](../src/pipeline/contracts.py) | 将版本化 schema 转为 Arrow schema，并校验单行 | 是 |
| [`src/pipeline/adapter.py`](../src/pipeline/adapter.py) | 规定 venue 元数据和八个操作 | 是 |
| [`src/pipeline/mock_adapter.py`](../src/pipeline/mock_adapter.py) | 无网络的固定样本链路 | 是 |

`DATA_ROOT` 不在 JSON 中给默认路径，是为了避免把研究数据误写到仓库或系统盘。`PIPELINE_CONFIG_DIR` 可指向另一套绝对路径的配置目录。环境变量 `DATA_MIN_FREE_GIB` 和 `PIPELINE_LOG_LEVEL` 可覆盖 JSON；空覆盖值回退到 JSON。进程环境中的同名键优先于 `.env`。`KALSHI_API_KEY_ID`、`KALSHI_PRIVATE_KEY_PEM`、`POLYMARKET_API_KEY`、`POLYMARKET_API_SECRET`、`POLYMARKET_API_PASSPHRASE` 和 `DATABASE_URL` 仅预留，PR 1 不读取它们，也不调用任何真实 API 或数据库。`POLYGON_RPC` 与 `POLYMARKET_START_BLOCK` 是旧 indexer 已使用的键；后者保留可解析的数值默认值。

### 包与依赖是否受控

**依赖受控，分发打包尚未配置。** [`pyproject.toml`](../pyproject.toml) 声明 Python 3.9+、运行依赖、pytest 和 ruff；[`uv.lock`](../uv.lock) 保存解析结果；CI 使用 `uv sync --group dev`。本次没有新增依赖，`python-dotenv` 和 `pyarrow` 都已在现有依赖中。`pyproject.toml` 目前没有 build backend，因此不能把此仓库视为已配置好的 wheel 发布包；在仓库根目录通过 `python -m src.pipeline` 和测试配置导入 `src`。

## 配置函数与逐项验证

| 函数 | 输入与职责 | 对应测试及实际断言 |
| --- | --- | --- |
| `config._read_json_settings` | 读取一个 JSON 文件，只接受预期的单个键及指定类型。 | `test_config_files_reject_malformed_or_unexpected_values` 分别断言缺失文件、坏 JSON、布尔值冒充整数、额外键和非法日志级别会报清晰错误。 |
| `config._read_environment` | 读取可选本机 `.env`，再覆盖进程环境；返回映射，不把凭据放进配置对象。 | `test_split_config_files_and_environment_precedence` 断言三级优先级，并确认模拟密钥不出现在配置对象的表示中；坏路径由配置文件错误测试断言。 |
| `PipelineConfig.load` | 选择配置目录，合并 JSON 与环境值，建立 `data_root`、空间阈值和日志级别。 | 上述优先级测试、`test_config_directory_environment_override` 和错误配置测试覆盖默认值、覆盖值、绝对配置目录与非法输入。 |
| `PipelineConfig.from_env` | 保留 PR 1 原有调用方式，委托 `load`。 | `test_config_requires_absolute_data_root_and_reports_unwritable`、`test_config_checks_disk_space_and_environment_overrides` 使用该入口。 |
| `PipelineConfig.validate_startup` | 委托数据根目录的启动校验并返回解析后的路径。 | 缺失路径、不可写模拟、磁盘不足模拟与成功路径测试均调用该方法。 |
| `config_validation.parse_data_root` | 拒绝空值和相对路径。 | `test_config_requires_absolute_data_root_and_reports_unwritable` 对两类错误做断言，成功路径由配置加载测试覆盖。 |
| `config_validation.parse_min_free_gib` | 接受非负整数，拒绝负数、错误格式和布尔值。 | `test_config_checks_disk_space_and_environment_overrides` 验证环境覆盖与负数；错误配置测试拒绝 JSON 中的布尔值。 |
| `config_validation.parse_log_level` | 统一大小写并限制为五个标准级别。 | `test_split_config_files_and_environment_precedence` 验证 `DEBUG` 覆盖；错误配置测试拒绝 `TRACE`。 |
| `config_validation.validate_data_root` | 查找现存父目录、检查可用空间、创建根目录并尝试实际写入。 | `test_config_checks_disk_space_and_environment_overrides` 模拟 3 GiB 可用空间并要求 4 GiB；不可写测试模拟 `PermissionError`；CLI 成功测试验证目录创建。 |

磁盘不足和权限失败通过注入故障测试，未以真实磁盘填满或修改系统目录权限的方式测试。生产启动仍按 200 GiB 默认阈值执行，因此空间不足会按设计失败；测试仅在临时目录将阈值设为 0。

## 目录与 writer 函数逐项验证

| 函数 | 约束 | 对应测试及实际断言 |
| --- | --- | --- |
| `DataLayout.create` | 在配置根目录下创建 `imports`、`bronze`、`silver`、`gold`、`quarantine`、`manifests`；拒绝被符号链接替代的层。 | `test_layout_creates_layers_and_writer_enforces_scope` 比对六个目录；`test_layout_rejects_symlinked_layer` 验证链接层被拒绝。 |
| `DataLayout.writer` | 只接受 `WriterRole`，将角色绑定到固定层。 | `test_layout_creates_layers_and_writer_enforces_scope` 拒绝字符串角色；`test_each_writer_is_bound_to_its_layer` 对六个角色逐一验证。 |
| `ScopedWriter.write_new` | 只写所属层；先写临时文件、同步文件内容，再独占发布；不覆盖旧文件。 | 目录测试拒绝跨层、绝对路径、`..` 与覆盖；`test_writer_rejects_symlink_escape` 拒绝嵌套符号链接且不碰外部目录；`test_writer_cleans_temporary_file_on_publish_failure` 注入发布失败并确认无残留目标或临时文件；六角色测试验证各自正反路径。 |

这些约束由应用接口执行，不是操作系统级的访问控制。测试没有模拟攻击者在检查与发布之间并发替换目录，也没有模拟断电。文件内容在发布前已 `fsync`，但目录元数据、manifest 和 checkpoint 的一致提交仍属于 PR 2。

## 数据契约函数逐项验证

[`docs/SCHEMAS.md`](../docs/SCHEMAS.md) 的 JSON 区块定义 1 个 Bronze、8 个 Silver、4 个 Gold 数据集；代码中的 [`schema_registry.json`](../src/pipeline/schema_registry.json) 与文档逐项相等。版本、字段顺序、类型、可空性和主键都接受测试检查。

| 函数 | 职责 | 对应测试及实际断言 |
| --- | --- | --- |
| `get_contract` | 按数据集名称读取契约，拒绝未知名称。 | `test_schema_document_matches_code_registry` 遍历 13 个数据集并断言未知名称报错。 |
| `arrow_schema` | 把字符串类型映射为 Arrow 字段、可空性及版本元数据。 | 同一测试比较 13 个 schema 的字段顺序和可空性；mock 链路与 Gold 秒级测试用实际 Arrow 表转换验证可写类型。 |
| `_parse_json` 与内部 `reject_constant` | 严格解析 JSON，拒绝语法错误和非标准 `NaN`。 | `test_bronze_and_silver_validation_rejects_bad_rows` 用坏 JSON 与 `NaN` 两种输入触发。 |
| `validate_record` | 检查字段集合、版本、类型、UTC 时间、十进制精度、范围、JSON 形状和训练特征的可见时间。 | Bronze/Silver 异常测试验证缺字段之外的多种拒绝路径；`test_gold_one_second_requires_aligned_utc_time` 验证整秒、价格范围及 Arrow 转换；`test_training_features_obey_point_in_time_contract` 验证未来特征与空 manifest 列表被拒绝。mock 三类标准化结果再次调用该函数。 |

这是**行级**验证；跨文件主键唯一性、时间覆盖、关系完整性和源特有质量规则仍由计划中的 PR 4 校验关口承担。当前测试证明文档与注册表一致，并不等于已证明真实交易场所数据符合契约。

## Venue 接口与 mock 函数逐项验证

[`AdapterMetadata.__post_init__`](../src/pipeline/adapter.py) 要求八项声明均非空，并拒绝非正数限速。[`MockVenueAdapter.metadata`](../src/pipeline/mock_adapter.py) 提供八项固定声明。`test_mock_adapter_discover_to_normalize_chain` 断言有效声明可用，同时用空规则和零限速分别验证拒绝。`VenueAdapter.metadata` 和八个抽象方法使不完整实现无法实例化；该测试直接尝试实例化抽象类，预期得到 `TypeError`。

| 接口与 [mock 实现](../src/pipeline/mock_adapter.py) | 行为 | 对应测试 |
| --- | --- | --- |
| `discover_markets` | 返回固定市场及无下一页游标。 | `test_mock_adapter_discover_to_normalize_chain` 验证市场 ID 与游标。 |
| `backfill_markets` | 返回同一固定市场页。 | 同一测试比较回填页与发现页。 |
| `backfill_trades` | 返回固定成交原始记录。 | 同一测试取得样本并交给 `normalize_trade`。 |
| `fetch_settlements` | 返回明确的空页。 | 同一测试断言空元组。 |
| `stream_market_data` | 对 `mock-1` 产生一条订单簿变更。 | 同一测试读取一条事件并检查源序号。 |
| `normalize_market` | 生成含 Bronze 来源字段的 Silver 市场行。 | 同一测试调用校验器并写入内存 Arrow 表。 |
| `normalize_trade` | 把价格和数量转为 `Decimal`，生成 Silver 成交行。 | 同一测试断言价格为 `0.65` 并转换 Arrow 表；异常测试再验证非法价格拒绝。 |
| `normalize_book_event` | 生成带序号的 Silver 订单簿变更行。 | 同一测试断言序号及契约校验通过。 |

mock 的回填不模拟真实分页、限速、断线或 API 版本切换；它验证接口可调用、数据可进入统一契约，不代表 Kalshi 或 Polymarket 接入已完成。

## 启动入口与测试证据

[`src/pipeline/__main__.py`](../src/pipeline/__main__.py) 的 `main` 解析 `check` 命令，加载配置、校验根目录并建立六层目录；失败返回状态码 2 并打印原因。测试 `test_pipeline_cli_reports_configuration_errors_and_prepares_layout` 直接覆盖缺失 `DATA_ROOT` 与成功路径；`test_module_entry_point_runs_in_a_new_process` 在新进程执行 `python -m src.pipeline check`，验证真正的模块入口和目录结果。

可复核的命令：

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest tests/test_pipeline_foundation.py -q
.venv/bin/pytest tests/ -q
```

本轮定向测试为 **22 passed**，完整测试为 **139 passed，5 warnings**。本地以现有 `.venv` 直接执行工具，因为沙箱对用户级 uv 缓存没有写权限；CI 仍使用 `uv` 和同一项目依赖。更改前的 `commit0` 为 `ce97ac0`，原 PR 1 实现提交 `commit1.1` 为 `3d3752e`。本轮反馈修改以独立提交交付，便于审阅差异。

## 负责人验收建议

1. 打开 [`README.md`](../README.md) 按“Configure the pipeline”设置本机 `.env`，确认 `DATA_ROOT` 指向预期磁盘，且绝不把真实凭据加入 `.env.example`。
2. 审查两个 JSON 文件中的默认值。生产空间阈值当前是 200 GiB；若磁盘低于此值，启动失败是预期的保护行为。
3. 运行上述四条检查命令，确认定向测试、全量测试与格式检查结果。
4. 审查 [`docs/SCHEMAS.md`](../docs/SCHEMAS.md) 中的字段、单位、主键和可空性。后续 PR 必须沿用或显式升级版本。
5. 在 PR 2 交付前，不把 `write_new` 成功返回解释为 manifest 已登记或 checkpoint 已安全推进。
