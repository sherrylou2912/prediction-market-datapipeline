# 配置目录发展规范

本文件定义完整项目的目标结构。它是结构约束，不是要求一次创建全部文件：只有当前 PR 实际实现某项能力时，才创建对应模块、profile、job 或 experiment；禁止空占位文件。

## 心智模型

```text
models      = 设计图纸：字段、类型、关系和验证规则
profiles    = 乐高零件：可被多个任务复用的配置组件
jobs        = 生产说明书：正式、可调度、可恢复的数据任务
experiments = 研究说明书：值得保存、比较和复现的实验
```

## 完整目标结构

```text
src/config/
├── __init__.py
│   # 稳定公共 API；只导出外部调用者需要的类型和函数。
├── README.md
│   # 面向使用者，记录已实现配置的详细位置和调用方法。
├── README_FOR_DEVELOPER.md
│   # 面向开发者，简述设计图纸、字段、结构和修改规则。
├── developing.md
│   # 本文件：目标结构、职责边界和演进规则。
├── errors.py
│   # 配置文件、引用、字段和 preflight 的异常类型。
├── loader.py
│   # 读取 JSON、.env 和进程环境；不承担业务验证。
├── resolver.py
│   # 在 profiles 出现后，展开 job/experiment 的显式引用并记录来源。
├── serialization.py
│   # 生成脱敏稳定 JSON、config hash 和 run-record 快照。
│
├── models/
│   ├── __init__.py
│   │   # 导出公共配置类型。
│   ├── common.py
│   │   # TimeWindow、ConfigReference、ConfigVersion 等小型共享值对象。
│   ├── pipeline.py
│   │   # PipelineConfig：DATA_ROOT、空间门槛、日志和共享 preflight。
│   ├── dataset.py
│   │   # DatasetConfig/Ref：数据集身份、层、schema version 和分区引用。
│   ├── venue.py
│   │   # VenueConfig：可调整端点、timeout、限速覆盖和 secret 变量名。
│   ├── quality.py
│   │   # QualityPolicy：coverage、重复、缺失、quarantine 和 PIT 要求。
│   ├── execution.py
│   │   # ExecutionConfig：batch、并发、重试、timeout 和 checkpoint 间隔。
│   └── tasks/
│       ├── __init__.py
│       ├── initial_load.py
│       │   # InitialLoadConfig：第一次历史加载的专用字段。
│       ├── incremental_load.py
│       │   # IncrementalLoadConfig：checkpoint、overlap 和增量专用字段。
│       ├── validation_job.py
│       │   # ValidationJobConfig：独立质量验证与报告字段。
│       └── backtest.py
│           # BacktestConfig：数据快照、策略、费用、seed 和 PIT 字段。
│
├── defaults/
│   ├── storage.json
│   │   # 所有写任务都安全适用的存储默认值。
│   ├── runtime.json
│   │   # 所有任务都安全适用的运行默认值。
│   └── execution.json
│       # 只有存在普遍安全的保守执行值时才创建。
│
├── profiles/
│   ├── datasets/
│   │   ├── polymarket_trades_v1.json
│   │   ├── polymarket_markets_v1.json
│   │   ├── kalshi_trades_v1.json
│   │   └── kalshi_markets_v1.json
│   │       # 共享数据集身份；只引用 src/data_schema 的 schema。
│   ├── venues/
│   │   ├── polymarket.json
│   │   └── kalshi.json
│   │       # 非敏感、可调整的 venue 运行参数；不复制 adapter 协议事实。
│   ├── quality/
│   │   ├── ingestion_strict.json
│   │   ├── silver_strict.json
│   │   └── backtest_strict.json
│   │       # 显式命名和版本化的质量政策；不设宽松隐式默认值。
│   └── execution/
│       ├── local_conservative.json
│       └── local_parallel.json
│           # 可复用的资源组合，仍须在任务开始前验证当前环境。
│
├── jobs/
│   ├── initial_load/
│   │   ├── polymarket_trades_history.json
│   │   └── kalshi_trades_history.json
│   │       # 可重复执行的正式历史加载任务。
│   ├── incremental/
│   │   ├── polymarket_trades_daily.json
│   │   └── kalshi_trades_daily.json
│   │       # 使用稳定 checkpoint、可被调度器调用的增量任务。
│   └── validation/
│       ├── bronze_daily.json
│       └── silver_daily.json
│           # 定期运行的完整性、coverage 和 contract 检查。
│
└── experiments/
    └── backtests/
        ├── calibration_baseline.json
        └── strategy_001.json
            # 固定数据 manifest 和参数、值得长期复现的回测。
```

## 配置流

```text
defaults + profiles + job/experiment + environment/CLI
→ loader
→ resolver
→ typed immutable config objects
→ 完整验证
→ serialization
→ 脱敏 resolved config + hash + run record 开始记录
→ 任务执行
→ run record 完成记录
```

解析后的运行快照不写回 `src/config/`，而应进入 `DATA_ROOT/manifests/runs/<run_id>/` 或未来 PostgreSQL run registry。

## 强制规则

1. `PipelineConfig` 只管理所有任务共享的运行环境；task 参数放入对应 task model。
2. 每种任务只有一个顶层 task config class；共享配置使用组合，不建立大型继承树。
3. `loader.py` 只读原始来源；model 验证字段；resolver 只解析显式 profile 引用。
4. profile 引用保持一层，不允许任意深度继承或不透明 deep merge。
5. 所有 profile、job 和 experiment JSON 包含 `config_version`；required value 必须显式，只有普遍安全的值才可进入 defaults。
6. Quality policy 必须显式选择，不提供宽松的隐藏默认政策。
7. secrets 只来自环境或 secret manager，不进入代码、JSON、对象 repr、日志或快照。
8. 数据 schema 的唯一事实来源是 `src/data_schema/`；venue 协议事实属于 adapter。
9. 临时运行可由 CLI 生成对象；只有正式 job 和值得复现的 experiment 才保存 JSON。
10. 新增结构必须有当前 PR 的真实调用者和测试；不得提前创建空模块、空目录或示例配置。
11. 每次修改 `src/config/`，必须同时更新 `README.md` 和 `README_FOR_DEVELOPER.md`。
12. 每次运行在副作用发生前验证所有最终参数，并记录脱敏后的 resolved config、来源和 hash。
