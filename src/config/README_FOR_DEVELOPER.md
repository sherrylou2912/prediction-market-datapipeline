# 配置设计图纸摘要

本文件面向开发者，快速说明配置代码放在哪里、遵守什么边界。完整目标结构和演进规则见 [`developing.md`](developing.md)。

## 当前设计

```text
src/config/
├── __init__.py              # 稳定公共 API
├── errors.py                # 配置异常
├── loader.py                # 原始来源读取
├── validation.py            # 可复用的合法性约束和异常转换
├── models/
│   ├── __init__.py
│   └── pipeline.py          # PipelineConfig 和 preflight
└── defaults/
    ├── storage.json
    └── runtime.json
```

`PipelineConfig` 位于 `models/pipeline.py`，字段如下：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `data_root` | `Path` | 必须是绝对路径；`load()` 从环境读取。 |
| `min_free_gib` | `int` | 非负且不能是布尔值，只在写任务 preflight 中使用。 |
| `log_level` | `str` | 仅允许五种 Python 标准日志级别，并标准化为大写。 |
| `config_dir` | `Path` | 必须是绝对路径；`load()` 须能读取其中两个默认 JSON。 |

`PipelineConfig` 是不可变 pydantic 模型；字段和约束定义在 `models/pipeline.py` 和 `validation.py`。直接构造和 `load()` 都校验类型、路径形式及取值，不检查磁盘容量、试写或创建目录；`load()` 会读取配置文件和可能存在的 `.env`。读写 preflight 负责环境检查；写预检创建目录后同步其父目录，清理目录后也同步父目录；macOS 写预检检查路径与软链接展开中出现的 `/Volumes/<卷名>`（大小写不敏感），要求卷本身是挂载点且不能是软链接，无法确认时拒绝写入，其他平台不特判 `/Volumes`。要修改已解析对象，应以 `PipelineConfig(**{**config.model_dump(), "字段": 新值})` 重新构造并校验；不要用不重新校验更新值的 `model_copy(update=...)`。

`load()` 在私有属性 `_sources` 中记录每个字段的来源；`effective_settings()` 返回生效值、来源及只依据生效值计算的 SHA-256，满足硬规则 10 和 `developing.md` 规则 12 中“记录 resolved config、来源和 hash”的当前部分（`check` 命令以 `config.effective` 事件输出）。重新构造的对象没有来源记录，显示为 `direct`；来源记录以不可变、可 pickle 的二元组保存。pydantic 的 `==` 也比较私有属性，因此值相同但来源不同的对象不相等，比较生效值应使用 `effective_settings()["sha256"]`。`developing.md` 将 config hash 归入未来的 `serialization.py`；PR2 引入该文件时应迁移并复用这份哈希，避免两套实现。新增字段时须在 `load()` 中登记来源；若将来新增含 secret 的配置，必须在 `effective_settings()` 中脱敏后才能输出。运行记录（run record）写入仍属 PR2。

显式 `environ` 且没有指定 `env_file` 时，不读取本机默认 `.env`；如果明确提供 `env_file`，先读取该文件，再以 `environ` 中的同名值覆盖。未传 `environ` 时正常读取默认 `.env` 和进程环境。`.env` 插值只使用所选择的进程环境（显式传入时不读取真实环境）和之前解析的文件值；同名时进程环境优先。JSON loader 和 `.env` loader 均拒绝重复键，避免模糊的配置值；无法解析的 `.env` 行直接报错。

## 职责边界

- `loader.py` 只读取 JSON 和环境，不判断任务业务规则。
- model 用 pydantic 声明允许及必填字段、类型、字段关系和自身规则；新增或修改字段时同步修改模型与测试。每次编写或修改相关配置代码前，开发者和 agent 必须先阅读本文件与 `developing.md`。
- `validation.py` 保存多个 model 可共用的合法性约束并把 pydantic `ValidationError` 转为 `ConfigError`；跨配置引用由 resolver 或 task model 检查，真实环境由 preflight 检查，数据行由 `src/data_schema/` 检查。
- 项目中的配置组合模型应继承 `ConfigModel`，并使用其构造、`model_validate`、`model_validate_json` 或 `model_validate_strings` 入口；这些入口将 pydantic 的错误转换为不保留输入值异常链的 `ConfigError`，错误位置最多显示已声明的顶层字段。错误原因只使用经过审查的固定文本，未知类型回退通用说明；需要具体提示时为约束定义固定错误类型并更新安全消息表及测试。自定义校验器的错误消息仍不得插入输入值，因为其他调用路径可能直接处理 pydantic 错误。普通第三方 `BaseModel` 嵌套配置模型时，外层可能重新包装并暴露输入，不得记录其原始错误；必须在受控边界脱敏后报告。
- `PipelineConfig` 只管理共享运行环境，不吸收 task 参数，也只有它可以由环境变量覆盖；任务参数来自 JSON 或 CLI。
- `src/data_schema/` 是数据 contract 的唯一事实来源；config 只能引用 schema version。
- `src/adapters/` 声明 venue 协议事实；config 只保存可调整的非敏感参数。
- secrets 永远不进入配置模型、日志或序列化快照。

## 未来组合方式

```text
models      = 设计图纸
profiles    = 可复用零件
jobs        = 正式数据任务说明书
experiments = 值得保存的研究说明书
```

加载流程：

```text
defaults + profiles + job/experiment + environment
→ loader
→ resolver
→ typed config object
→ validate
→ redacted snapshot + hash
→ run record
```

不是每次运行都需要新增文件。临时任务可由 CLI 参数生成运行时 config object；只有正式可调度任务和需要复现的实验才保存 job 或 experiment JSON。

## 修改检查表

每次修改 `src/config/`：

1. 遵守 [`developing.md`](developing.md) 的目标结构和按需创建规则。
2. 同步更新本文件和 [`README.md`](README.md)。
3. 更新受影响的 imports、CLI、测试和根文档。
4. 验证所有有效参数和参数间关系发生在任务产生副作用之前。
5. 运行 lint、format check 和完整测试。
