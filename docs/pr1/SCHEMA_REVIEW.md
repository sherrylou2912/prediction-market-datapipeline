# PR1 数据契约复审指南

本指南按当前工作区的 `schema_registry.json`（`7.0.0`）解释已实施的契约，供负责人逐项复审；不代表合并或生产可用。机器可读的唯一事实来源是 [`src/data_schema/schema_registry.json`](../../src/data_schema/schema_registry.json)，执行器是 [`contracts.py`](../../src/data_schema/contracts.py)。每个数据集链接到 [`docs/SCHEMAS.md`](../SCHEMAS.md) 的对应生成表：表格逐字段列出类型、可空、主键、适用的每条规则及字段含义；下文逐项解释规则。表格由 `uv run python scripts/generate_schema_docs.py` 生成，测试会检查生成内容与 JSON 一致。复审字段时请同时看表格，避免在这里复制说明形成第二份来源。

## 如何读 JSON

顶层 `version` 是全 registry 共用的版本；`version_field` 声明每个数据集中的版本字段，自检要求该字段必填且各有一条针对它的版本规则；`datasets` 以数据集名为键。加载 registry 时任意层的 JSON 重复键都会被拒绝。每个数据集有三部分：

1. `primary_key`：按顺序列出构成行身份的字段。它们必须存在且不可空；跨行唯一性不在本次 contract 内检查。
2. `fields`：每个字段用 `type` 和 `description` 声明类型和含义。类型后缀 `?` 表示值可为 null，**字段本身仍必须存在**；无 `?` 时不得为 null。所有 `str` 必须含非空白字符。未声明的字段会被拒绝。
3. `rules`：一条对象声明一条规则；同一条涉及多个字段的规则会显示在表格中相应字段的多行，仍是同一条规则。

例如，`{"type":"range","field":"price","min":"0","max":"1"}` 是含边界的 `[0, 1]`，数字界限用十进制字符串表达；`{"type":"compare","left":"scheduled_open_at","op":"<=","right":"scheduled_close_at"}` 是两者都有值时要求前者不晚于后者，任一为空则不比较。`enum.values` 是合法值的完整集合；`alignment.unit` 指定整秒或整分钟；`difference` 要求三字段均有值时结果等于左值减右值。`version` 要求字段值等于顶层版本。

`string_array` 要求 JSON 数组中的每项为非空白字符串；`nonempty: true` 还要求至少一项。`json_object` 要求 JSON 对象。`unique_json_keys` 拒绝任意层对象中的重复键。`book_levels` 要求 JSON 数组，每档恰有 `price` 和 `quantity`，均是有限十进制数字或十进制字符串，价格在 `[0, 1]`、数量非负，且均须能精确表示为 `decimal128(28, 10)`。`level_map` 要求 JSON 对象，键是无前导零的正整数档位序号字符串，值是能精确表示为 `decimal128(28, 10)` 的非负有限十进制字符串；`max: "1"` 还把值上限设为 1，`max: null` 表示无上限。`conditional_null`、`conditional_value`、`conditional_positive` 和 `conditional_reason` 分别表示条件成立时目标必须为空、等于指定值、有值时大于零，以及目标为空时必须填写原因；`conditional_value` 的 `allow_null: true` 同时允许 null。`requires_present` 表示目标有值时，其引用的 `required` 字段也必须有值；目标为 null 不触发。`zero_coverage_null` 在覆盖时间明确为零时要求相关字段为 null；未知覆盖不等于零。`zero_pair_null` 在两项均为零时要求目标为空；`exactly_one_present` 要求两个可空字段恰有一个有值。`rounded_mean` 以指定小数位数按四舍六入五成双检查两个值的平均数，计算不受调用方的十进制上下文影响。`window_end` 要求目标时间不早于 `start` 字段加一个指定单位的窗口长度。`iso_date` 要求合法且规范的 `YYYY-MM-DD` 日期。`day_start` 要求两者均有值时，UTC 时间字段 `field` 不早于日期字段 `day` 的 UTC 零点（允许相等）；registry 自检要求 `field` 为 `utc_datetime`、`day` 为 `str` 且同一数据集对 `day` 声明了 `iso_date` 规则。

其余通用类型约束也适用：`int` 拒绝 `bool` 并要求位于有符号 Arrow int64 范围；`bool` 仅接受布尔值；`binary` 接受原始 bytes（可为空字节）；`decimal` 是有限 `Decimal`，且必须能精确放入 Arrow `decimal128(28, 10)`；`str` 与 JSON 文本必须能编码为 UTF-8，`json` 还必须是合法 JSON 文本；`utc_datetime` 必须使用 `datetime.timezone.utc`。`difference` 的精确比较不依赖调用方的十进制精度或异常陷阱。需解释的 JSON 字段另有 `unique_json_keys` 声明；Bronze 原始文本不加该规则以保留证据，规范化前才严格解析拒绝歧义。可空字段为 null 时，针对其值的普通范围、枚举、格式规则跳过；条件规则按其各自声明执行。导入时自检字段类型、说明、主键和规则引用及格式；`get_contract()` 返回递归只读视图，不能通过返回值改写 registry。

## 数据集逐项复审

下面每项的“字段表”均涵盖该数据集**全部字段**及主键标记；这里另列主键和每条规则，方便与 JSON 交叉核对。所有数据集都有一条 `version` 规则：`schema_version` 必须等于 `7.0.0`。Silver 所有数据集均要求 `bronze_record_index >= 0`；Gold 所有数据集的 `source_manifest_ids` 均有非空 `string_array` 规则。除 `bronze.raw.raw_payload` 外，所有 JSON 字段都有 `unique_json_keys` 规则。下文不再逐项重复这些共同规则。

### Bronze

- [`bronze.raw` 字段表](../SCHEMAS.md#bronzeraw)：主键 `(run_id, record_index)`。`record_index >= 0`，可空 `sequence` 有值时 `>= 0`。`raw_payload` 保存合法 JSON 原文，`raw_bytes` 保存不需先解析的原始字节；两者恰好填写一个。交易所、API 版本、接收和写入时间未知时可空；时间顺序异常仍保留原始记录，但 `VenueAdapter` 基类的规范化边界拒绝将其规范化为 Silver（对所有 adapter 生效）。原始文件落盘、隔离及人工审核尚未实现。

### Silver

- [`silver.events` 字段表](../SCHEMAS.md#silverevents)：主键 `(venue, event_id, observed_at)`。除共同规则外无额外规则。
- [`silver.markets` 字段表](../SCHEMAS.md#silvermarkets)：主键 `(venue, market_id, observed_at)`。`status` 限 `pending`、`open`、`closed`、`settled`、`cancelled`、`unknown`。`scheduled_open_at`/`scheduled_close_at` 保存来源公布的计划时间，`actual_open_at`/`actual_close_at` 只保存有可靠证据的实际时间；同一组两者均有值时要求开放不晚于关闭（允许相等），计划与实际之间不作比较（例如提前关闭可以表示）。来源没有说明时间属于计划还是实际时（负责人确认，2026-11-13），四个字段都不填，不猜测含义，原文按原样存入 `source_open_time_text`、`source_close_time_text`，不解析；这样可区分“来源没给”和“来源给了但未分类”。实际时间是否晚于观察时间等时钟问题按来源在后续质量规则中处理，本行契约不检查。`description`、`settlement_rules` 保存来源原文，未提供时为空；有值时不得为空白。来源给出空字符串或纯空白时如何映射（置空或作为异常审核）由各来源 adapter 按来源语义决定并记录；契约本身拒绝空白值。该说明同样适用于 `source_open_time_text`、`source_close_time_text`；来源时间原值不是字符串（如 epoch 数字）时如何保存为原文也由来源 adapter 决定并记录，原始值始终保留在 Bronze。契约不交叉检查计划/实际时间与原文字段是否同时填写（同一来源可能同时提供已分类和未分类的时间）；只把未说明含义的时间放入原文字段由 adapter 保证。
- [`silver.outcomes` 字段表](../SCHEMAS.md#silveroutcomes)：主键 `(venue, market_id, outcome_id, observed_at)`：加入已有必填的 `market_id`，使同一来源不同市场若重用相同 outcome ID 也不会身份冲突（真实来源 ID 的唯一范围仍待相应 adapter PR 核实）。除共同规则外无额外规则；此处 `label` 是非空显示文本，不是训练标签的数字范围；可空 `description` 保存来源 outcome 说明原文。
- [`silver.market_states` 字段表](../SCHEMAS.md#silvermarket_states)：主键 `(venue, market_id, observed_at)`。`status` 使用与 `silver.markets` 相同的六值；`best_bid`、`best_ask` 有值时各在 `[0, 1]`；两者均有值时 `best_bid <= best_ask`，任一为空时不作交叉比较。
- [`silver.trades` 字段表](../SCHEMAS.md#silvertrades)：主键 `(venue, trade_id)`。`price` 在 `[0, 1]`，`quantity >= 0`；可空 `taker_side` 有值时只能是 `buy`、`sell`。
- [`silver.book_snapshots` 字段表](../SCHEMAS.md#silverbook_snapshots)：主键 `(venue, snapshot_id)`。可空 `source_sequence` 有值时 `>= 0`；`bids`、`asks` 各有上述 `book_levels` 规则。它验证每档形状及范围，不判断跨档顺序、重复价格或整本盘口一致性。
- [`silver.book_deltas` 字段表](../SCHEMAS.md#silverbook_deltas)：主键 `(venue, delta_id)`。`price` 在 `[0, 1]`，`quantity >= 0`，可空 `source_sequence` 有值时 `>= 0`；`side` 只能是 `bid`、`ask`。
- [`silver.settlements` 字段表](../SCHEMAS.md#silversettlements)：主键 `(venue, market_id, outcome_id, observed_at)`。`payout` 在 `[0, 1]`。`settled_at` 来源未提供时为空，不以观察时间等代替；依赖结算时刻的质量检查和研究不得把空值当作已确认时间（相关检查属于 PR4）。

### Gold

- [`gold.market_daily` 字段表](../SCHEMAS.md#goldmarket_daily)：主键 `(venue, market_id, day, as_of)`。`volume`、`trade_count` 未知时可为空，有值时必须非负；`day` 必须是有效的规范 ISO 日历日期；`as_of` 不得早于 `day` 的 UTC 零点（B7，例如 `day=2024-01-02` 时 `as_of=2024-01-01T23:59Z` 被拒），但不要求当日已结束：日内部分汇总是否完整由后续覆盖与产品规则判断。确认无成交时填写零；成交笔数为零时成交份数只能为零或未知。当前行契约没有额外状态字段来证明零确实经过确认。
- [`gold.market_1s` 字段表](../SCHEMAS.md#goldmarket_1s)：主键 `(venue, market_id, outcome_id, second)`。`best_bid`、`best_ask`、`mid`、`microprice`、`last_trade_price` 有值时各在 `[0, 1]`；`spread`、`bid_depth_top_n`、`ask_depth_top_n`、`rolling_volume`、`update_count`、`book_age_ms`、`receive_latency_ms` 有值时各非负；`imbalance` 有值时在 `[-1, 1]`。`second` 对齐 UTC 整秒；`as_of >= second + 1 秒`。买卖价均有值时 `best_bid <= best_ask`；`spread` 和 `mid` 有值均须同时有买价和卖价，`spread` 必须等于 `best_ask - best_bid`，`mid` 必须等于两侧报价的算术平均并按十位小数四舍六入五成双；两者本身仍可为空。滚动成交量未知时为空。`microprice` 有值要求双侧报价有值；`imbalance` 有值要求双侧深度有值且不能同时为零。当前不验证 microprice、imbalance 的完整计算公式或 gap 的来源证据。
- [`gold.liquidity_features` 字段表](../SCHEMAS.md#goldliquidity_features)：主键 `(venue, market_id, outcome_id, observation_time)`。`spread`、`depth_top_n` 有值时非负，`imbalance` 有值时在 `[-1, 1]`。此数据集没有买卖价字段，不能在本行核对 spread 是否等于卖价减买价。
- [`gold.training_datasets` 字段表](../SCHEMAS.md#goldtraining_datasets)：主键 `(dataset_name, venue, market_id, observation_time)`。`features` 必须为 JSON 对象；可空数字 `label` 有值时在 `[0, 1]`；`max_feature_available_at <= observation_time`，允许相等；`label_available_at` 有值时必须严格晚于 `observation_time`，不允许相等。
- [`gold.market_1m` 字段表](../SCHEMAS.md#goldmarket_1m)：主键 `(venue, market_id, outcome_id, minute)`。`minute` 对齐 UTC 整分钟，`as_of >= minute + 1 分钟`；`open`、`high`、`low`、`close`、`vwap`、`bid_best_price`、`ask_best_price` 有值时各在 `[0, 1]`；`volume`、`trade_amount`、`trade_count`、`bid_depth_top_n_quantity`、`bid_depth_top_n_amount`、`ask_depth_top_n_quantity`、`ask_depth_top_n_amount`、`bid_observed_levels_avg`、`ask_observed_levels_avg`、`bid_observed_levels_min`、`ask_observed_levels_min`、`spread` 有值时各非负；`bid_coverage_seconds`、`ask_coverage_seconds`、`joint_coverage_seconds` 有值时各在 `[0, 60]`。共同覆盖有值时要求两侧覆盖都有值，并分别不超过买侧和卖侧覆盖。`low <= high`，且 `open`、`close`、`vwap` 各自不小于 `low`、不大于 `high`；每个比较都只在两端有值时执行。`bid_level_prices`、`ask_level_prices` 使用上限为 1 的 `level_map`；`bid_level_quantities`、`ask_level_quantities`、`bid_level_amounts`、`ask_level_amounts` 使用无上限的 `level_map`。六个字段可空，有值才检查。

  明确零买侧或卖侧覆盖时，对应侧的价格、档位、深度和观察档位统计必须为空；任一侧覆盖或共同覆盖明确为零时 `spread` 必须为空。覆盖为 null 表示未知，不视为零。`spread` 有值时处于 `[0, 1]`。

  `trade_data_status` 只能是 `observed`、`confirmed_no_trades`、`missing`：

  - `missing`：`volume`、`trade_amount`、`trade_count`、`open`、`high`、`low`、`close`、`vwap` 必须全为 null，不能把缺失写成零。
  - `confirmed_no_trades`：`volume` 和 `trade_count` 必须为零；`open`、`high`、`low`、`close`、`vwap` 必须为 null。`trade_amount` 可以为 null 或零，不可为非零值。
  - `observed`：`volume`、`trade_count` 如果有值必须大于零，仍允许为空；`open` 或 `close` 为空时必须填写 `open_close_reason`，用于记录例如同时刻成交顺序不明。其他成交字段依照各自可空和范围规则处理。

## 关键选择、边界和待负责人复审

1. **破坏性变更与版本**：工作区未发布版本先由 `4.0.0` 升至 `5.0.0`，再升至 `6.0.0`、`7.0.0`（仓库 HEAD 为 `2.0.0`），所有行共享版本。`7.0.0`（B7）的直接原因：`gold.market_daily` 新增 `day_start` 规则，`as_of` 早于该 UTC 日开始的旧行将被拒绝。`6.0.0`（B6）的直接原因：`silver.markets` 删除 `open_at`、`close_at`，改为计划/实际开放与关闭四个可空时间，并新增可空 `description`、`settlement_rules`、`source_open_time_text`、`source_close_time_text`；`silver.outcomes` 新增可空 `description`，主键加入 `market_id`；`silver.settlements.settled_at` 改为可空。旧市场行会因未知字段被拒绝，缺新增键的旧行会因缺字段被拒绝。`5.0.0`（B5）的直接原因是 `bronze.raw`：`venue`、`api_version` 和 `raw_payload` 改为可空，新增必填键 `raw_bytes`（缺该键的旧行会被拒绝），并新增 `exactly_one_present` 规则。相对 HEAD 此前已累计的变化：`gold.training_datasets.max_feature_event_time` 改名为必填 `max_feature_available_at`，旧字段将作为未知字段被拒绝；新增 `gold.market_1m`、枚举、规则与严格 UTC 也改变可接受输入。字段含义、类型、可空性、增删、主键和规则变化均升级版本；不兼容变更升主版本。当前没有迁移器或旧数据重写实现。
2. **分钟数据粒度与缺失**：窗口 `[minute, minute + 1 分钟)`，盘口价格、数量和金额是按可靠覆盖持续时间加权的分钟均值，金额先逐时刻计算再加权。买卖两侧和共同覆盖秒数用于表达有限覆盖，详细问题须由 manifest 与质量记录追溯。N 由未来特征参数决定，计划默认 5；参数变化产生新 `data_version`。一秒和一分钟产品的 `as_of` 不能早于窗口结束；结束时刻只是最低约束，实际输入或结果晚到时必须按真实可用时间记录，不能编造成窗口结束。本次只定义契约，没有聚合、覆盖计算、质量报告或 manifest 生成器。`level_map` 在 Arrow 中是 JSON 字符串而非原生嵌套类型，实际 Parquet 互操作性和性能尚待验证。
3. **第一层与第二层 point-in-time**：训练数据 contract 只检查 `max_feature_available_at <= observation_time`；其他 Gold 的 point-in-time 是约定，当前没有同等代码检查。未来训练集构建与回测要检查 `max_feature_available_at <= 决策时间 - information_delay`，默认延迟一分钟，放入实验配置并记录；该第二层尚未实现。历史可用时间不能凭事件时间或回补接收时间冒充事实，只能使用经批准且记录的假设。
4. **UTC 的 Python 表示**：代码检查 `tzinfo is timezone.utc`，拒绝 `ZoneInfo("UTC")` 和伦敦冬季等其他零偏移对象。Python 会把 `timezone(timedelta(0))` 规范化为同一个 `timezone.utc` 单例，因此无法识别其构造方式，也不能将该表达式单独拒绝。
5. **本次需复审的具体选择**：六种市场状态、`side` 的 `bid`/`ask`、`taker_side` 的 `buy`/`sell`；标签可用时间严格晚于观察时间；分钟成交状态及条件规则；档位 JSON 的精确十进制字符串表示；统一版本政策。真实 venue 映射及数据语义须在 adapter PR 中核对，不能把 mock 值当成来源事实。
6. **尚未由 contract 保证的内容**：跨行主键唯一性、序列连续性、缺口、跨表/文件一致性、可靠覆盖、OHLC 与成交记录的对应关系、盘口排序及跨档一致性，以及训练/回测第二层延迟检查。单行通过不等于来源完整或数据已具备研究质量；跨行跨文件验证留待 PR4，录制和数据持久化格式也仍属后续工作。
7. **已知的后续质量限制（B7 明确记录，当前未实现）**：以下是阅读阶段发现、按负责人授权由 agent 决定留给后续 PR 的问题；在相应检查实现前，不得把单行契约通过当作这些问题已解决。
   - `gold.training_datasets`：标签有值而 `label_available_at` 为空时契约接受（保留未知、不编造）。无法确认标签何时可用的记录不能自动作为可训练数据，须由 PR4 质量门禁或训练/回测构建检查，或经明确记录的批准假设。
   - `silver.market_states` 的 `best_bid`/`best_ask` 没有 outcome 标识，`gold.liquidity_features.depth_top_n` 没有说明是买侧、卖侧还是合计。在来源映射和产品口径确定（PR5/PR6 adapter 及特征设计）前，不得默认报价对应 Yes，也不得把它们当作已核实的 outcome 级指标。
   - `silver.book_snapshots` 只检查每档结构、范围和精度；买价高于卖价的交叉盘口、跨档排序、重复档位和序列缺口均未检查。PR4/PR7 须按来源规则检查、保留证据并送审核，不能无依据把某种盘口状态对所有来源一律判为错误。
   - `gold.market_1s.update_count` 为必填，但数据不完整时的含义未定义；`gap`/`recovery` 标记的来源证据和完整性也未由行级契约证明。PR7 须区分未知、确认为零和已知缺口，不得把缺失数据当作无更新。
   - `gold.market_daily`：B7 只保证 `as_of` 不早于该 UTC 日开始；是否允许日内部分汇总、以及汇总是否完整，由后续产品与覆盖规则决定。
