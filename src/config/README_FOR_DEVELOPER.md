# 配置设计图纸摘要

本文件面向开发者，快速说明配置代码放在哪里、遵守什么边界。完整目标结构和演进规则见 [`developing.md`](developing.md)。

## 当前设计

```text
src/config/
├── __init__.py              # 稳定公共 API
├── errors.py                # 配置异常
├── loader.py                # 原始来源读取
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

`PipelineConfig.__post_init__()` 对 `load()`、直接构造和 `dataclasses.replace()` 共用字段校验；两个路径须为不含 NUL 字符的绝对路径。`load()` 在读取默认文件之前也会拒绝含 NUL 的配置目录。直接构造只校验类型、路径形式和取值，不探测磁盘、不创建目录，也不读取默认文件；读写 preflight 仍负责实际环境检查。

显式 `environ` 且没有指定 `env_file` 时，不读取本机默认 `.env`；如果明确提供 `env_file`，先读取该文件，再以 `environ` 中的同名值覆盖。未传 `environ` 时正常读取默认 `.env` 和进程环境。

## 职责边界

- `loader.py` 只读取 JSON 和环境，不判断任务业务规则。
- model 负责字段类型、字段关系和与自身相关的验证。
- `PipelineConfig` 只管理共享运行环境，不吸收 task 参数。
- `src/data_schema/` 是数据 contract 的唯一事实来源；config 只能引用 schema version。
- `src/adapters/` 声明 venue 协议事实；config 只保存可调整的非敏感参数。
- secrets 永远不进入 dataclass、日志或序列化快照。

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
