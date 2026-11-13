# 数据契约 v7

[`src/data_schema/schema_registry.json`](../src/data_schema/schema_registry.json) 是字段、主键、字段说明和全部行级硬规则的唯一事实来源。下方表格使用 `uv run python scripts/generate_schema_docs.py` 生成；不要手工修改标记之间的内容。

## 存储与版本规则

- 所有路径相对于配置的 `DATA_ROOT`。Bronze 的 JSONL.zst 或 Parquet.zstd、Silver 和 Gold 的 Parquet.zstd 为计划格式，尚未实现。
- 当前契约版本为 `7.0.0`，所有数据集共享。目前没有旧版本数据的迁移器。registry 的顶层 `version_field` 指定各数据集的版本字段，加载时检查每个数据集都使用一个针对该必填字段的版本规则，且拒绝 JSON 的重复键。字段的含义、类型、可空性、增删或主键变更，以及规则新增、放宽或收紧（包括范围、枚举和行内规则），都需要提升版本；破坏性变更提升主版本，兼容新增提升次版本，非语义修正提升补丁版本。拒绝未知字段。
- `utc_datetime` 只接受 `tzinfo is datetime.timezone.utc` 的 Python 时间；`ZoneInfo("UTC")` 等独立的零偏移时区对象均拒绝。Python 的 `timezone(timedelta(0))` 和 `timezone.utc` 是同一个对象，无法区分，均被接受。Arrow 类型是 `timestamp[us, tz=UTC]`。
- `int` 必须能表示为 Arrow 有符号 `int64`；`decimal` 使用有限 Python `Decimal`、Arrow `decimal128(28, 10)`；`binary` 使用 Python `bytes` 和 Arrow binary。价格和 payout 为 0–1，份数、金额、次数和时长非负。JSON 中盘口价格、份数和金额也必须能精确放入相同精度；超出精度时拒绝，不进行舍入。JSON 中盘口数字可用十进制字符串，分钟档位字典只用十进制字符串，以避免浮点精度丢失。需要结构化解释的 JSON 字段由 `unique_json_keys` 规则拒绝对象及嵌套对象中的重复键；Bronze `raw_payload` 可保留原始 JSON 文本，包括重复键，`raw_bytes` 可保留不需先解析的原始字节。规范化解释前须严格解析并拒绝歧义、保留原始证据。
- 字段类型后的 `?` 表示可空，字段依然必须存在；所有字符串字段不得为空或全空格，所有 Arrow 字符串（包括 JSON 文本）必须能够编码为 UTF-8。主键在行内必填，跨行唯一性由 PR4 检查。
- `bronze.raw` 的 JSON 原文和原始字节恰好填写一种；没有交易所、API 版本或接收/写入时间时可为空，不编造。接收时间晚于写入时间的记录仍可作为原始证据；`VenueAdapter` 基类的规范化边界（对所有 adapter 生效）拒绝将其规范化为 Silver。该契约不实现实际原始文件、manifest 或隔离流程，大文件的来源级保存方案留待后续实现。
- Silver 通过 Bronze 运行标识和记录序号追溯；Gold 的非空 `source_manifest_ids` 指向输入。各 Gold 产品约定只使用 `as_of` 或 `observation_time` 前已知的信息，目前仅 `gold.training_datasets` 有 `max_feature_available_at <= observation_time` 的代码检查。训练集构建和回测还须检查可用时间不晚于决策时间减实验配置的信息延迟；该第二层留待对应 PR 实现。历史数据的可用时间假设须经批准并记录。
- `gold.market_1m` 使用 UTC 整分钟的半开窗口；`trade_data_status` 区分有观测、确认无成交和数据缺失。缺失不得填零；确认无成交时成交份数和笔数为零，成交金额为 null 或零。盘口为持续时间加权平均，明确零覆盖时对应的盘口值为空，未知覆盖不视为零；`spread` 上限为 1。`gold.market_1s` 的滚动成交量未知时留空，确认无成交时才填零；`mid` 必须在双侧报价都有值时才可填写，其平均值按十位小数四舍六入五成双。`microprice` 有值时必须有双侧报价；`imbalance` 有值时须有双侧深度且不能同时为零，当前未验证这两个值的完整计算公式。具体档位 N 与滚动窗口由特征参数决定，覆盖秒数是简要信息，详细缺口和问题在关联 manifest 与质量记录中追溯。JSON 档位字典作为 Arrow 字符串保存，实际 Parquet 嵌套兼容性和性能尚待验证。`gold.market_1s` 和 `gold.market_1m` 的 `as_of` 至少是窗口结束时刻，实际输入或结果晚到时还须如实记录较晚的可用时间；窗口结束不证明结果当时已可用。

## 自动生成字段表

<!-- BEGIN GENERATED SCHEMA TABLES -->

### `bronze.raw`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `run_id` | `str` | 否 | 是 | — | 接收运行的唯一标识。 |
| `record_index` | `int` | 否 | 是 | `{"field": "record_index", "min": "0", "type": "range"}` | 运行内接收记录序号，从 0 开始。 |
| `venue` | `str` | 是 | 否 | — | 来源交易场所标识；不适用或未知时为空。 |
| `source` | `str` | 否 | 否 | — | 原始数据来源标识。 |
| `message_type` | `str` | 否 | 否 | — | 来源消息类型。 |
| `source_event_id` | `str` | 是 | 否 | — | 来源提供的事件标识；未知时为空。 |
| `event_time` | `utc_datetime` | 是 | 否 | — | 来源事件发生的 UTC 时间；未知时为空。 |
| `received_at` | `utc_datetime` | 是 | 否 | — | 本系统接收来源记录的 UTC 时间；未知时为空。 |
| `ingested_at` | `utc_datetime` | 是 | 否 | — | 原始记录写入的 UTC 时间；未知时为空。 |
| `sequence` | `int` | 是 | 否 | `{"field": "sequence", "min": "0", "type": "range"}` | 来源序列号；未提供时为空。 |
| `api_version` | `str` | 是 | 否 | — | 来源 API 版本；不适用或未知时为空。 |
| `protocol_version` | `str` | 是 | 否 | — | 来源协议版本；不适用时为空。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |
| `raw_payload` | `json` | 是 | 否 | `{"left": "raw_payload", "right": "raw_bytes", "type": "exactly_one_present"}` | 来源消息的 JSON 原文；与 raw_bytes 恰好填写一个。 |
| `raw_bytes` | `binary` | 是 | 否 | `{"left": "raw_payload", "right": "raw_bytes", "type": "exactly_one_present"}` | 来源原始字节，可含非 JSON、无效编码或空内容；与 raw_payload 恰好填写一个。 |

### `silver.events`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `event_id` | `str` | 否 | 是 | — | 来源事件标识。 |
| `title` | `str` | 否 | 否 | — | 事件或市场标题。 |
| `observed_at` | `utc_datetime` | 否 | 是 | — | 本系统观察到该值的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.markets`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `event_id` | `str` | 是 | 否 | — | 来源事件标识。 |
| `title` | `str` | 否 | 否 | — | 事件或市场标题。 |
| `description` | `str` | 是 | 否 | — | 来源提供的市场描述原文；来源未提供时为空。 |
| `settlement_rules` | `str` | 是 | 否 | — | 来源提供的结算条件原文；来源未提供时为空。 |
| `status` | `str` | 否 | 否 | `{"field": "status", "type": "enum", "values": ["pending", "open", "closed", "settled", "cancelled", "unknown"]}` | 市场状态：pending、open、closed、settled、cancelled 或 unknown。 |
| `scheduled_open_at` | `utc_datetime` | 是 | 否 | `{"left": "scheduled_open_at", "op": "<=", "right": "scheduled_close_at", "type": "compare"}` | 来源公布的计划开放 UTC 时间；未提供或来源未区分计划与实际时为空，原文见 source_open_time_text / source_close_time_text。 |
| `scheduled_close_at` | `utc_datetime` | 是 | 否 | `{"left": "scheduled_open_at", "op": "<=", "right": "scheduled_close_at", "type": "compare"}` | 来源公布的计划关闭 UTC 时间；未提供或来源未区分计划与实际时为空，原文见 source_open_time_text / source_close_time_text。 |
| `actual_open_at` | `utc_datetime` | 是 | 否 | `{"left": "actual_open_at", "op": "<=", "right": "actual_close_at", "type": "compare"}` | 有可靠证据的实际开放 UTC 时间；无证据或来源未区分计划与实际时为空，原文见 source_open_time_text / source_close_time_text。 |
| `actual_close_at` | `utc_datetime` | 是 | 否 | `{"left": "actual_open_at", "op": "<=", "right": "actual_close_at", "type": "compare"}` | 有可靠证据的实际关闭 UTC 时间；无证据或来源未区分计划与实际时为空，原文见 source_open_time_text / source_close_time_text。 |
| `source_open_time_text` | `str` | 是 | 否 | — | 来源提供但未说明属于计划还是实际的开放时间原文，按原样保存、不解析；来源已明确区分或未提供时为空。 |
| `source_close_time_text` | `str` | 是 | 否 | — | 来源提供但未说明属于计划还是实际的关闭时间原文，按原样保存、不解析；来源已明确区分或未提供时为空。 |
| `observed_at` | `utc_datetime` | 否 | 是 | — | 本系统观察到该值的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.outcomes`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `outcome_id` | `str` | 否 | 是 | — | 来源 outcome 标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `label` | `str` | 否 | 否 | — | outcome 的非空显示名称。 |
| `description` | `str` | 是 | 否 | — | 来源提供的 outcome 说明原文；来源未提供时为空。 |
| `observed_at` | `utc_datetime` | 否 | 是 | — | 本系统观察到该值的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.market_states`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `status` | `str` | 否 | 否 | `{"field": "status", "type": "enum", "values": ["pending", "open", "closed", "settled", "cancelled", "unknown"]}` | 市场状态：pending、open、closed、settled、cancelled 或 unknown。 |
| `best_bid` | `decimal` | 是 | 否 | `{"field": "best_bid", "max": "1", "min": "0", "type": "range"}`<br>`{"left": "best_bid", "op": "<=", "right": "best_ask", "type": "compare"}` | 观察窗口内的最佳买价，概率单位。 |
| `best_ask` | `decimal` | 是 | 否 | `{"field": "best_ask", "max": "1", "min": "0", "type": "range"}`<br>`{"left": "best_bid", "op": "<=", "right": "best_ask", "type": "compare"}` | 观察窗口内的最佳卖价，概率单位。 |
| `observed_at` | `utc_datetime` | 否 | 是 | — | 本系统观察到该值的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.trades`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `trade_id` | `str` | 否 | 是 | — | 来源成交标识。 |
| `market_id` | `str` | 否 | 否 | — | 来源市场标识。 |
| `outcome_id` | `str` | 是 | 否 | — | 来源 outcome 标识。 |
| `price` | `decimal` | 否 | 否 | `{"field": "price", "max": "1", "min": "0", "type": "range"}` | 价格，概率单位，范围 0 至 1。 |
| `quantity` | `decimal` | 否 | 否 | `{"field": "quantity", "min": "0", "type": "range"}` | 数量，份数。 |
| `taker_side` | `str` | 是 | 否 | `{"field": "taker_side", "type": "enum", "values": ["buy", "sell"]}` | 主动成交方：buy 或 sell；未知时为空。 |
| `event_time` | `utc_datetime` | 是 | 否 | — | 来源事件发生的 UTC 时间；未知时为空。 |
| `observed_at` | `utc_datetime` | 否 | 否 | — | 本系统观察到该值的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.book_snapshots`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `snapshot_id` | `str` | 否 | 是 | — | 来源盘口快照标识。 |
| `market_id` | `str` | 否 | 否 | — | 来源市场标识。 |
| `outcome_id` | `str` | 否 | 否 | — | 来源 outcome 标识。 |
| `source_sequence` | `int` | 是 | 否 | `{"field": "source_sequence", "min": "0", "type": "range"}` | 来源盘口序列号；未提供时为空。 |
| `bids` | `json` | 否 | 否 | `{"field": "bids", "type": "book_levels"}`<br>`{"field": "bids", "type": "unique_json_keys"}` | 买盘档位 JSON 数组；每档为 price 和 quantity 字段组成的对象，价格 0 至 1，数量非负，值为十进制数字或十进制字符串。 |
| `asks` | `json` | 否 | 否 | `{"field": "asks", "type": "book_levels"}`<br>`{"field": "asks", "type": "unique_json_keys"}` | 卖盘档位 JSON 数组；每档为 price 和 quantity 字段组成的对象，价格 0 至 1，数量非负，值为十进制数字或十进制字符串。 |
| `event_time` | `utc_datetime` | 是 | 否 | — | 来源事件发生的 UTC 时间；未知时为空。 |
| `received_at` | `utc_datetime` | 否 | 否 | — | 本系统接收来源记录的 UTC 时间。 |
| `recovery` | `bool` | 否 | 否 | — | 快照用于断线或序列缺口后的恢复，或该秒处于恢复状态时为 true。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.book_deltas`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `delta_id` | `str` | 否 | 是 | — | 来源盘口变动标识。 |
| `market_id` | `str` | 否 | 否 | — | 来源市场标识。 |
| `outcome_id` | `str` | 否 | 否 | — | 来源 outcome 标识。 |
| `source_sequence` | `int` | 是 | 否 | `{"field": "source_sequence", "min": "0", "type": "range"}` | 来源盘口序列号；未提供时为空。 |
| `side` | `str` | 否 | 否 | `{"field": "side", "type": "enum", "values": ["bid", "ask"]}` | 盘口方向：bid 或 ask。 |
| `price` | `decimal` | 否 | 否 | `{"field": "price", "max": "1", "min": "0", "type": "range"}` | 价格，概率单位，范围 0 至 1。 |
| `quantity` | `decimal` | 否 | 否 | `{"field": "quantity", "min": "0", "type": "range"}` | 数量，份数。 |
| `event_time` | `utc_datetime` | 是 | 否 | — | 来源事件发生的 UTC 时间；未知时为空。 |
| `received_at` | `utc_datetime` | 否 | 否 | — | 本系统接收来源记录的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `silver.settlements`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `outcome_id` | `str` | 否 | 是 | — | 来源 outcome 标识。 |
| `payout` | `decimal` | 否 | 否 | `{"field": "payout", "max": "1", "min": "0", "type": "range"}` | 每份结算支付金额，范围 0 至 1。 |
| `settled_at` | `utc_datetime` | 是 | 否 | — | 来源结算 UTC 时间；来源未提供时为空，不以观察时间或其他时间代替；依赖结算时刻的检查和研究不得把空值当作已确认时间。 |
| `observed_at` | `utc_datetime` | 否 | 是 | — | 本系统观察到该值的 UTC 时间。 |
| `bronze_run_id` | `str` | 否 | 否 | — | 对应 Bronze 记录的运行标识。 |
| `bronze_record_index` | `int` | 否 | 否 | `{"field": "bronze_record_index", "min": "0", "type": "range"}` | 对应 Bronze 记录在运行中的序号。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `gold.market_daily`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `day` | `str` | 否 | 是 | `{"field": "day", "type": "iso_date"}`<br>`{"day": "day", "field": "as_of", "type": "day_start"}` | UTC 日历日期，格式 YYYY-MM-DD。 |
| `volume` | `decimal` | 是 | 否 | `{"field": "volume", "min": "0", "type": "range"}`<br>`{"allow_null": true, "equals": 0, "field": "volume", "type": "conditional_value", "value": "0", "when": "trade_count"}` | 成交份数；确认无成交时为 0，未知时为空。 |
| `trade_count` | `int` | 是 | 否 | `{"field": "trade_count", "min": "0", "type": "range"}`<br>`{"allow_null": true, "equals": 0, "field": "volume", "type": "conditional_value", "value": "0", "when": "trade_count"}` | 成交笔数；确认无成交时为 0，未知时为空。 |
| `as_of` | `utc_datetime` | 否 | 是 | `{"day": "day", "field": "as_of", "type": "day_start"}` | 计算结果截至的 UTC 可用时间；不得早于 day 的 UTC 零点，可早于当日结束（日内部分汇总的完整性由覆盖规则判断）。 |
| `source_manifest_ids` | `json` | 否 | 否 | `{"field": "source_manifest_ids", "nonempty": true, "type": "string_array"}`<br>`{"field": "source_manifest_ids", "type": "unique_json_keys"}` | 输入 manifest 标识组成的非空 JSON 数组；详细覆盖和问题由 manifest 及关联记录追溯。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `gold.market_1s`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `outcome_id` | `str` | 否 | 是 | — | 来源 outcome 标识。 |
| `second` | `utc_datetime` | 否 | 是 | `{"field": "second", "type": "alignment", "unit": "second"}`<br>`{"field": "as_of", "start": "second", "type": "window_end", "unit": "second"}` | UTC 整秒窗口起点。 |
| `best_bid` | `decimal` | 是 | 否 | `{"field": "best_bid", "max": "1", "min": "0", "type": "range"}`<br>`{"left": "best_bid", "op": "<=", "right": "best_ask", "type": "compare"}`<br>`{"left": "best_ask", "result": "spread", "right": "best_bid", "type": "difference"}`<br>`{"field": "spread", "required": "best_bid", "type": "requires_present"}`<br>`{"field": "mid", "required": "best_bid", "type": "requires_present"}`<br>`{"left": "best_bid", "result": "mid", "right": "best_ask", "scale": 10, "type": "rounded_mean"}`<br>`{"field": "microprice", "required": "best_bid", "type": "requires_present"}` | 观察窗口内的最佳买价，概率单位。 |
| `best_ask` | `decimal` | 是 | 否 | `{"field": "best_ask", "max": "1", "min": "0", "type": "range"}`<br>`{"left": "best_bid", "op": "<=", "right": "best_ask", "type": "compare"}`<br>`{"left": "best_ask", "result": "spread", "right": "best_bid", "type": "difference"}`<br>`{"field": "spread", "required": "best_ask", "type": "requires_present"}`<br>`{"field": "mid", "required": "best_ask", "type": "requires_present"}`<br>`{"left": "best_bid", "result": "mid", "right": "best_ask", "scale": 10, "type": "rounded_mean"}`<br>`{"field": "microprice", "required": "best_ask", "type": "requires_present"}` | 观察窗口内的最佳卖价，概率单位。 |
| `spread` | `decimal` | 是 | 否 | `{"field": "spread", "min": "0", "type": "range"}`<br>`{"left": "best_ask", "result": "spread", "right": "best_bid", "type": "difference"}`<br>`{"field": "spread", "required": "best_bid", "type": "requires_present"}`<br>`{"field": "spread", "required": "best_ask", "type": "requires_present"}` | 最佳卖价减最佳买价；缺任一报价时为空。 |
| `mid` | `decimal` | 是 | 否 | `{"field": "mid", "max": "1", "min": "0", "type": "range"}`<br>`{"field": "mid", "required": "best_bid", "type": "requires_present"}`<br>`{"field": "mid", "required": "best_ask", "type": "requires_present"}`<br>`{"left": "best_bid", "result": "mid", "right": "best_ask", "scale": 10, "type": "rounded_mean"}` | 最佳买卖价的算术平均，以十位小数按四舍六入五成双取整；缺报价时为空。 |
| `microprice` | `decimal` | 是 | 否 | `{"field": "microprice", "max": "1", "min": "0", "type": "range"}`<br>`{"field": "microprice", "required": "best_bid", "type": "requires_present"}`<br>`{"field": "microprice", "required": "best_ask", "type": "requires_present"}` | 微价格：(最佳卖价 × 最佳买量 + 最佳买价 × 最佳卖量) / (最佳买量 + 最佳卖量)；缺少输入或分母为零时为空。 |
| `bid_depth_top_n` | `decimal` | 是 | 否 | `{"field": "bid_depth_top_n", "min": "0", "type": "range"}`<br>`{"field": "imbalance", "required": "bid_depth_top_n", "type": "requires_present"}`<br>`{"field": "imbalance", "left": "bid_depth_top_n", "right": "ask_depth_top_n", "type": "zero_pair_null"}` | 买盘前 N 档挂单份数之和；N 由特征参数决定。 |
| `ask_depth_top_n` | `decimal` | 是 | 否 | `{"field": "ask_depth_top_n", "min": "0", "type": "range"}`<br>`{"field": "imbalance", "required": "ask_depth_top_n", "type": "requires_present"}`<br>`{"field": "imbalance", "left": "bid_depth_top_n", "right": "ask_depth_top_n", "type": "zero_pair_null"}` | 卖盘前 N 档挂单份数之和；N 由特征参数决定。 |
| `imbalance` | `decimal` | 是 | 否 | `{"field": "imbalance", "max": "1", "min": "-1", "type": "range"}`<br>`{"field": "imbalance", "required": "bid_depth_top_n", "type": "requires_present"}`<br>`{"field": "imbalance", "required": "ask_depth_top_n", "type": "requires_present"}`<br>`{"field": "imbalance", "left": "bid_depth_top_n", "right": "ask_depth_top_n", "type": "zero_pair_null"}` | 盘口不平衡度：(买盘前 N 档份数 − 卖盘前 N 档份数) / (两侧前 N 档份数之和)；N 由特征参数决定，分母为零时为空。 |
| `last_trade_price` | `decimal` | 是 | 否 | `{"field": "last_trade_price", "max": "1", "min": "0", "type": "range"}` | 最近一笔成交价格，概率单位；未知时为空。 |
| `rolling_volume` | `decimal` | 是 | 否 | `{"field": "rolling_volume", "min": "0", "type": "range"}` | 滚动成交份数，窗口长度由特征参数决定；缺少成交数据时为空，确认无成交时为 0。 |
| `update_count` | `int` | 否 | 否 | `{"field": "update_count", "min": "0", "type": "range"}` | 该秒盘口更新次数。 |
| `book_age_ms` | `int` | 是 | 否 | `{"field": "book_age_ms", "min": "0", "type": "range"}` | 窗口时点距离最近一次可靠盘口更新的时间，毫秒；未知时为空。 |
| `receive_latency_ms` | `int` | 是 | 否 | `{"field": "receive_latency_ms", "min": "0", "type": "range"}` | 来源事件时间至本系统接收时间的延迟，毫秒；未知时为空。 |
| `gap` | `bool` | 否 | 否 | — | 该秒存在已知序列缺口或不可靠盘口时为 true。 |
| `recovery` | `bool` | 否 | 否 | — | 快照用于断线或序列缺口后的恢复，或该秒处于恢复状态时为 true。 |
| `as_of` | `utc_datetime` | 否 | 否 | `{"field": "as_of", "start": "second", "type": "window_end", "unit": "second"}` | 窗口汇总结果的可用 UTC 时间；不得早于窗口结束，并须如实反映实际输入和结果的较晚可用时间。 |
| `source_manifest_ids` | `json` | 否 | 否 | `{"field": "source_manifest_ids", "nonempty": true, "type": "string_array"}`<br>`{"field": "source_manifest_ids", "type": "unique_json_keys"}` | 输入 manifest 标识组成的非空 JSON 数组；详细覆盖和问题由 manifest 及关联记录追溯。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `gold.liquidity_features`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `outcome_id` | `str` | 否 | 是 | — | 来源 outcome 标识。 |
| `observation_time` | `utc_datetime` | 否 | 是 | — | 特征观察或决策的 UTC 时间。 |
| `spread` | `decimal` | 是 | 否 | `{"field": "spread", "min": "0", "type": "range"}` | 最佳卖价减最佳买价；缺任一报价时为空。 |
| `depth_top_n` | `decimal` | 是 | 否 | `{"field": "depth_top_n", "min": "0", "type": "range"}` | 前 N 档挂单深度，份数；N 由特征参数决定。 |
| `imbalance` | `decimal` | 是 | 否 | `{"field": "imbalance", "max": "1", "min": "-1", "type": "range"}` | 盘口不平衡度：(买盘前 N 档份数 − 卖盘前 N 档份数) / (两侧前 N 档份数之和)；N 由特征参数决定，分母为零时为空。 |
| `source_manifest_ids` | `json` | 否 | 否 | `{"field": "source_manifest_ids", "nonempty": true, "type": "string_array"}`<br>`{"field": "source_manifest_ids", "type": "unique_json_keys"}` | 输入 manifest 标识组成的非空 JSON 数组；详细覆盖和问题由 manifest 及关联记录追溯。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

### `gold.training_datasets`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `dataset_name` | `str` | 否 | 是 | — | 训练数据集名称。 |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `observation_time` | `utc_datetime` | 否 | 是 | `{"left": "max_feature_available_at", "op": "<=", "right": "observation_time", "type": "compare"}`<br>`{"left": "observation_time", "op": "<", "right": "label_available_at", "type": "compare"}` | 特征观察或决策的 UTC 时间。 |
| `features` | `json` | 否 | 否 | `{"field": "features", "type": "json_object"}`<br>`{"field": "features", "type": "unique_json_keys"}` | 训练特征组成的 JSON 对象。 |
| `label` | `decimal` | 是 | 否 | `{"field": "label", "max": "1", "min": "0", "type": "range"}` | 训练标签值，概率单位，范围 0 至 1；未知时为空。 |
| `label_available_at` | `utc_datetime` | 是 | 否 | `{"left": "observation_time", "op": "<", "right": "label_available_at", "type": "compare"}` | 标签可供使用的 UTC 时间；未知时为空。 |
| `source_manifest_ids` | `json` | 否 | 否 | `{"field": "source_manifest_ids", "nonempty": true, "type": "string_array"}`<br>`{"field": "source_manifest_ids", "type": "unique_json_keys"}` | 输入 manifest 标识组成的非空 JSON 数组；详细覆盖和问题由 manifest 及关联记录追溯。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |
| `max_feature_available_at` | `utc_datetime` | 否 | 否 | `{"left": "max_feature_available_at", "op": "<=", "right": "observation_time", "type": "compare"}` | 输入特征中最晚的可用 UTC 时间，即实际可供使用而非仅事件发生的时间；历史假设须经批准并记录。 |

### `gold.market_1m`

| 字段 | 类型 | 可空 | 主键 | 适用规则 | 说明 |
| --- | --- | --- | --- | --- | --- |
| `venue` | `str` | 否 | 是 | — | 来源交易场所标识。 |
| `market_id` | `str` | 否 | 是 | — | 来源市场标识。 |
| `outcome_id` | `str` | 否 | 是 | — | 来源 outcome 标识。 |
| `minute` | `utc_datetime` | 否 | 是 | `{"field": "minute", "type": "alignment", "unit": "minute"}`<br>`{"field": "as_of", "start": "minute", "type": "window_end", "unit": "minute"}` | UTC 整分钟窗口起点；窗口包含起点、不包含一分钟后的终点。 |
| `open` | `decimal` | 是 | 否 | `{"field": "open", "max": "1", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "open", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "open", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "open", "reason": "open_close_reason", "type": "conditional_reason", "when": "trade_data_status"}`<br>`{"left": "low", "op": "<=", "right": "open", "type": "compare"}`<br>`{"left": "open", "op": "<=", "right": "high", "type": "compare"}` | 开盘成交价，概率单位；无法可靠计算时为空。 |
| `high` | `decimal` | 是 | 否 | `{"field": "high", "max": "1", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "high", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "high", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"left": "open", "op": "<=", "right": "high", "type": "compare"}`<br>`{"left": "close", "op": "<=", "right": "high", "type": "compare"}`<br>`{"left": "vwap", "op": "<=", "right": "high", "type": "compare"}`<br>`{"left": "low", "op": "<=", "right": "high", "type": "compare"}` | 最高成交价，概率单位；无法可靠计算时为空。 |
| `low` | `decimal` | 是 | 否 | `{"field": "low", "max": "1", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "low", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "low", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"left": "low", "op": "<=", "right": "open", "type": "compare"}`<br>`{"left": "low", "op": "<=", "right": "close", "type": "compare"}`<br>`{"left": "low", "op": "<=", "right": "vwap", "type": "compare"}`<br>`{"left": "low", "op": "<=", "right": "high", "type": "compare"}` | 最低成交价，概率单位；无法可靠计算时为空。 |
| `close` | `decimal` | 是 | 否 | `{"field": "close", "max": "1", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "close", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "close", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "close", "reason": "open_close_reason", "type": "conditional_reason", "when": "trade_data_status"}`<br>`{"left": "low", "op": "<=", "right": "close", "type": "compare"}`<br>`{"left": "close", "op": "<=", "right": "high", "type": "compare"}` | 收盘成交价，概率单位；无法可靠计算时为空。 |
| `vwap` | `decimal` | 是 | 否 | `{"field": "vwap", "max": "1", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "vwap", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "vwap", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"left": "low", "op": "<=", "right": "vwap", "type": "compare"}`<br>`{"left": "vwap", "op": "<=", "right": "high", "type": "compare"}` | 成交量加权平均成交价，概率单位；无法可靠计算时为空。 |
| `open_close_reason` | `str` | 是 | 否 | `{"equals": "observed", "field": "open", "reason": "open_close_reason", "type": "conditional_reason", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "close", "reason": "open_close_reason", "type": "conditional_reason", "when": "trade_data_status"}` | 开盘或收盘价无法可靠确定时的原因，例如同一时间成交顺序不明。 |
| `trade_data_status` | `str` | 否 | 否 | `{"field": "trade_data_status", "type": "enum", "values": ["observed", "confirmed_no_trades", "missing"]}`<br>`{"equals": "missing", "field": "volume", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "trade_amount", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "trade_count", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "open", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "high", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "low", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "close", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "missing", "field": "vwap", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "volume", "type": "conditional_value", "value": "0", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "trade_count", "type": "conditional_value", "value": "0", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "open", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "high", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "low", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "close", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "vwap", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "volume", "type": "conditional_positive", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "trade_count", "type": "conditional_positive", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "open", "reason": "open_close_reason", "type": "conditional_reason", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "close", "reason": "open_close_reason", "type": "conditional_reason", "when": "trade_data_status"}`<br>`{"allow_null": true, "equals": "confirmed_no_trades", "field": "trade_amount", "type": "conditional_value", "value": "0", "when": "trade_data_status"}` | 成交覆盖状态：observed、confirmed_no_trades 或 missing。 |
| `volume` | `decimal` | 是 | 否 | `{"field": "volume", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "volume", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "volume", "type": "conditional_value", "value": "0", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "volume", "type": "conditional_positive", "when": "trade_data_status"}` | 成交份数；确认无成交时为 0，未知时为空。 |
| `trade_amount` | `decimal` | 是 | 否 | `{"field": "trade_amount", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "trade_amount", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"allow_null": true, "equals": "confirmed_no_trades", "field": "trade_amount", "type": "conditional_value", "value": "0", "when": "trade_data_status"}` | 成交金额；仅在来源单位支持可靠计算时填写，未知时为空。 |
| `trade_count` | `int` | 是 | 否 | `{"field": "trade_count", "min": "0", "type": "range"}`<br>`{"equals": "missing", "field": "trade_count", "type": "conditional_null", "when": "trade_data_status"}`<br>`{"equals": "confirmed_no_trades", "field": "trade_count", "type": "conditional_value", "value": "0", "when": "trade_data_status"}`<br>`{"equals": "observed", "field": "trade_count", "type": "conditional_positive", "when": "trade_data_status"}` | 成交笔数；确认无成交时为 0，未知时为空。 |
| `bid_best_price` | `decimal` | 是 | 否 | `{"field": "bid_best_price", "max": "1", "min": "0", "type": "range"}`<br>`{"field": "bid_best_price", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧最佳价格的持续时间加权分钟平均，概率单位；无可靠覆盖时为空。 |
| `bid_level_prices` | `json` | 是 | 否 | `{"field": "bid_level_prices", "max": "1", "type": "level_map"}`<br>`{"field": "bid_level_prices", "type": "unique_json_keys"}`<br>`{"field": "bid_level_prices", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧以正整数档位序号字符串为键、十进制字符串为值的 JSON 对象；价格（概率单位）的持续时间加权平均，未知档不填零。金额先逐时刻计算再加权。 |
| `bid_level_quantities` | `json` | 是 | 否 | `{"field": "bid_level_quantities", "max": null, "type": "level_map"}`<br>`{"field": "bid_level_quantities", "type": "unique_json_keys"}`<br>`{"field": "bid_level_quantities", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧以正整数档位序号字符串为键、十进制字符串为值的 JSON 对象；挂单份数的持续时间加权平均，未知档不填零。金额先逐时刻计算再加权。 |
| `bid_level_amounts` | `json` | 是 | 否 | `{"field": "bid_level_amounts", "max": null, "type": "level_map"}`<br>`{"field": "bid_level_amounts", "type": "unique_json_keys"}`<br>`{"field": "bid_level_amounts", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧以正整数档位序号字符串为键、十进制字符串为值的 JSON 对象；挂单金额的持续时间加权平均，未知档不填零。金额先逐时刻计算再加权。 |
| `bid_depth_top_n_quantity` | `decimal` | 是 | 否 | `{"field": "bid_depth_top_n_quantity", "min": "0", "type": "range"}`<br>`{"field": "bid_depth_top_n_quantity", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧前 N 档份数之和的持续时间加权平均；N 由特征参数决定。 |
| `bid_depth_top_n_amount` | `decimal` | 是 | 否 | `{"field": "bid_depth_top_n_amount", "min": "0", "type": "range"}`<br>`{"field": "bid_depth_top_n_amount", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧前 N 档金额之和的持续时间加权平均；N 由特征参数决定。 |
| `bid_observed_levels_avg` | `decimal` | 是 | 否 | `{"field": "bid_observed_levels_avg", "min": "0", "type": "range"}`<br>`{"field": "bid_observed_levels_avg", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧实际观察档位数的持续时间加权平均。 |
| `bid_observed_levels_min` | `int` | 是 | 否 | `{"field": "bid_observed_levels_min", "min": "0", "type": "range"}`<br>`{"field": "bid_observed_levels_min", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧实际观察档位数的最小值；覆盖不足不代表实际只有这些档。 |
| `bid_coverage_seconds` | `decimal` | 是 | 否 | `{"field": "bid_coverage_seconds", "max": "60", "min": "0", "type": "range"}`<br>`{"field": "joint_coverage_seconds", "required": "bid_coverage_seconds", "type": "requires_present"}`<br>`{"left": "joint_coverage_seconds", "op": "<=", "right": "bid_coverage_seconds", "type": "compare"}`<br>`{"field": "bid_best_price", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_level_prices", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_level_quantities", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_level_amounts", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_depth_top_n_quantity", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_depth_top_n_amount", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_observed_levels_avg", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "bid_observed_levels_min", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "spread", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}` | bid 侧可靠盘口覆盖时间，秒；未知时为空，详细问题由 manifest 关联。 |
| `ask_best_price` | `decimal` | 是 | 否 | `{"field": "ask_best_price", "max": "1", "min": "0", "type": "range"}`<br>`{"field": "ask_best_price", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧最佳价格的持续时间加权分钟平均，概率单位；无可靠覆盖时为空。 |
| `ask_level_prices` | `json` | 是 | 否 | `{"field": "ask_level_prices", "max": "1", "type": "level_map"}`<br>`{"field": "ask_level_prices", "type": "unique_json_keys"}`<br>`{"field": "ask_level_prices", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧以正整数档位序号字符串为键、十进制字符串为值的 JSON 对象；价格（概率单位）的持续时间加权平均，未知档不填零。金额先逐时刻计算再加权。 |
| `ask_level_quantities` | `json` | 是 | 否 | `{"field": "ask_level_quantities", "max": null, "type": "level_map"}`<br>`{"field": "ask_level_quantities", "type": "unique_json_keys"}`<br>`{"field": "ask_level_quantities", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧以正整数档位序号字符串为键、十进制字符串为值的 JSON 对象；挂单份数的持续时间加权平均，未知档不填零。金额先逐时刻计算再加权。 |
| `ask_level_amounts` | `json` | 是 | 否 | `{"field": "ask_level_amounts", "max": null, "type": "level_map"}`<br>`{"field": "ask_level_amounts", "type": "unique_json_keys"}`<br>`{"field": "ask_level_amounts", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧以正整数档位序号字符串为键、十进制字符串为值的 JSON 对象；挂单金额的持续时间加权平均，未知档不填零。金额先逐时刻计算再加权。 |
| `ask_depth_top_n_quantity` | `decimal` | 是 | 否 | `{"field": "ask_depth_top_n_quantity", "min": "0", "type": "range"}`<br>`{"field": "ask_depth_top_n_quantity", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧前 N 档份数之和的持续时间加权平均；N 由特征参数决定。 |
| `ask_depth_top_n_amount` | `decimal` | 是 | 否 | `{"field": "ask_depth_top_n_amount", "min": "0", "type": "range"}`<br>`{"field": "ask_depth_top_n_amount", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧前 N 档金额之和的持续时间加权平均；N 由特征参数决定。 |
| `ask_observed_levels_avg` | `decimal` | 是 | 否 | `{"field": "ask_observed_levels_avg", "min": "0", "type": "range"}`<br>`{"field": "ask_observed_levels_avg", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧实际观察档位数的持续时间加权平均。 |
| `ask_observed_levels_min` | `int` | 是 | 否 | `{"field": "ask_observed_levels_min", "min": "0", "type": "range"}`<br>`{"field": "ask_observed_levels_min", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧实际观察档位数的最小值；覆盖不足不代表实际只有这些档。 |
| `ask_coverage_seconds` | `decimal` | 是 | 否 | `{"field": "ask_coverage_seconds", "max": "60", "min": "0", "type": "range"}`<br>`{"field": "joint_coverage_seconds", "required": "ask_coverage_seconds", "type": "requires_present"}`<br>`{"left": "joint_coverage_seconds", "op": "<=", "right": "ask_coverage_seconds", "type": "compare"}`<br>`{"field": "ask_best_price", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_level_prices", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_level_quantities", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_level_amounts", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_depth_top_n_quantity", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_depth_top_n_amount", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_observed_levels_avg", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "ask_observed_levels_min", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "spread", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}` | ask 侧可靠盘口覆盖时间，秒；未知时为空，详细问题由 manifest 关联。 |
| `spread` | `decimal` | 是 | 否 | `{"field": "spread", "max": "1", "min": "0", "type": "range"}`<br>`{"field": "spread", "type": "zero_coverage_null", "when": "bid_coverage_seconds"}`<br>`{"field": "spread", "type": "zero_coverage_null", "when": "ask_coverage_seconds"}`<br>`{"field": "spread", "type": "zero_coverage_null", "when": "joint_coverage_seconds"}` | 买卖双方同时有可靠报价时的价差持续时间加权平均，概率单位。 |
| `joint_coverage_seconds` | `decimal` | 是 | 否 | `{"field": "joint_coverage_seconds", "max": "60", "min": "0", "type": "range"}`<br>`{"field": "joint_coverage_seconds", "required": "bid_coverage_seconds", "type": "requires_present"}`<br>`{"left": "joint_coverage_seconds", "op": "<=", "right": "bid_coverage_seconds", "type": "compare"}`<br>`{"field": "joint_coverage_seconds", "required": "ask_coverage_seconds", "type": "requires_present"}`<br>`{"left": "joint_coverage_seconds", "op": "<=", "right": "ask_coverage_seconds", "type": "compare"}`<br>`{"field": "spread", "type": "zero_coverage_null", "when": "joint_coverage_seconds"}` | 买卖双方同时有可靠报价的覆盖时间，秒；未知时为空。 |
| `as_of` | `utc_datetime` | 否 | 否 | `{"field": "as_of", "start": "minute", "type": "window_end", "unit": "minute"}` | 窗口汇总结果的可用 UTC 时间；不得早于窗口结束，并须如实反映实际输入和结果的较晚可用时间。 |
| `source_manifest_ids` | `json` | 否 | 否 | `{"field": "source_manifest_ids", "nonempty": true, "type": "string_array"}`<br>`{"field": "source_manifest_ids", "type": "unique_json_keys"}` | 输入 manifest 标识组成的非空 JSON 数组；详细覆盖和问题由 manifest 及关联记录追溯。 |
| `schema_version` | `str` | 否 | 否 | `{"field": "schema_version", "type": "version"}` | 本行使用的数据契约版本。 |

<!-- END GENERATED SCHEMA TABLES -->

## 校验边界

Contract 执行 JSON 声明的行级硬规则；无法只凭单行判断的重复、连续性、跨表和跨文件一致性、覆盖与异常值等留给 PR4 的独立 validation 模块。Bronze 保留来源证据，异常数据须带原因进入 `quarantine/`，不得静默进入 Silver。流序列缺口必须记录，不能静默插值。
