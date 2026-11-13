# 配置位置与使用说明

本文件面向配置使用者，记录当前已经实现的配置放在哪里、如何覆盖以及在什么阶段调用。未来结构见 [`developing.md`](developing.md)，开发摘要见 [`README_FOR_DEVELOPER.md`](README_FOR_DEVELOPER.md)。

## 当前文件位置

| 位置 | 内容 |
| --- | --- |
| `src/config/defaults/storage.json` | 写任务开始前要求的最小剩余空间，默认 `200` GiB。 |
| `src/config/defaults/runtime.json` | 默认日志级别，当前为 `INFO`。 |
| `.env` | 整台机器共享的全局设置与 secrets；受 Git 忽略，不存放任务参数。 |
| `.env.example` | 可用环境变量名称，不含真实 secret。 |
| `src/config/models/pipeline.py` | `PipelineConfig` 设计图纸及数据目录预检。 |
| `src/config/loader.py` | 读取 JSON、`.env` 和进程环境变量。 |
| `src/config/validation.py` | 可复用的字段合法性约束和错误转换。 |
| `src/config/errors.py` | 配置错误类型。 |
| `src/config/__init__.py` | 对外导出 `PipelineConfig` 和 `ConfigError`。 |

目前尚未实现真实 initial load、incremental load、validation job 或 backtest，因此当前没有对应的 task models、profiles、jobs 或 experiments 文件。

## 当前字段

| 字段 | 来源 | 用途 |
| --- | --- | --- |
| `data_root` | `DATA_ROOT`，必填 | 所有数据层的绝对根目录。 |
| `min_free_gib` | `DATA_MIN_FREE_GIB` 或 `defaults/storage.json` | 写任务开始前的最小剩余空间。 |
| `log_level` | `PIPELINE_LOG_LEVEL` 或 `defaults/runtime.json` | 运行日志级别。 |
| `config_dir` | `load(config_dir=...)`、`PIPELINE_CONFIG_DIR` 或 `src/config/defaults/` | 本次实际使用的默认配置目录。 |

仅 `PipelineConfig` 共享环境设置可由环境变量覆盖；venue、quality、execution 和 task 等参数从 JSON 与 CLI 获取。优先级为：进程环境变量 > 本机 `.env` > version-controlled JSON default。配置目录另有显式参数优先：`load(config_dir=...)` > `PIPELINE_CONFIG_DIR` > 默认目录。空的覆盖值回退到 JSON 默认值；`DATA_ROOT` 没有默认值。`DATA_MIN_FREE_GIB` 的环境覆盖值只接受 ASCII 十进制数字字符串，可带首尾空白；不接受正负号或下划线。JSON 中须是非负整数，不接受布尔值。

正常调用 `PipelineConfig.load()` 时，会读取默认 `.env`。显式传入 `environ` 且未传 `env_file` 时，不读取本机默认 `.env`，便于隔离测试；若同时显式传入 `env_file`，则先读取该文件，再由 `environ` 中的同名值覆盖。`.env` 的 `${变量}` 插值仅使用传入的 `environ` 和文件中此前已定义的值，同名时 `environ` 优先；没有传入 `environ` 时使用实际进程环境。文件中未定义且环境不存在的变量展开为空字符串，`${变量:-默认值}` 使用给定默认值。配置 JSON 的同一对象和 `.env` 文件均不允许重复键；格式无法解析时直接报错。

`PipelineConfig` 使用不可变 pydantic 模型；无论通过 `load()` 还是直接构造，都会校验共享字段：两个路径须为绝对 `Path` 且不含 NUL 字符，空间门槛须为非负整数（不接受布尔值），日志级别须为有效级别并标准化为大写。直接构造不会读取默认文件、检查路径是否存在、创建目录、探测空闲空间或试写；正式任务仍须调用对应 preflight。

默认 `.env` 仅在文件确实不存在时可省略；目录、悬空软链接或无法读取的文件会报告配置错误。配置模型的公开校验入口将错误转为 `ConfigError`；错误位置最多显示已声明的顶层字段，不显示未知字段名或输入字典的键。错误原因使用固定的安全说明，未列出的类型使用通用说明，不复制 pydantic 原始消息。将其嵌入普通第三方 pydantic 模型时，外层模型的错误输出不受此保护，不得记录包含敏感值的原始异常。

## 调用方式

通用无副作用检查：

```bash
uv run python -m src check
```

它只加载配置并检查 `DATA_ROOT` 是否适合作为目录，不检查磁盘空间、不试写，也不创建目录。开始检查前，它在日志级别允许 `INFO` 时向 stderr 输出一条 JSON 日志（`event` 为 `config.effective`）：`details.settings` 列出每个字段的生效值及来源（如 `environment:DATA_ROOT`、`default:storage.json`、`argument:config_dir`；直接构造的对象为 `direct`），`details.sha256` 是生效值的哈希（不含来源，同样的值得到同样的哈希）。`PipelineConfig` 不含 secrets，因此全部字段都会输出；`.env` 中的其他变量不会出现在日志中。之后的任务应在产生副作用前复用 `PipelineConfig.effective_settings()` 记录同样内容。

只读任务在读取数据前调用：

```python
from src.config import PipelineConfig

config = PipelineConfig.load()
root = config.validate_for_read()
```

写任务在创建布局或写入数据前调用：

```python
from src.config import PipelineConfig
from src.data_io.layout import DataLayout

config = PipelineConfig.load()
root = config.validate_for_write()
layout = DataLayout.create(root)
```

写预检检查空间、试写和硬链接支持；逐层创建目录时同步每一层的父目录，确保目录项进入文件系统同步流程。macOS 上 `/Volumes/<卷名>` 本身必须是实际挂载点，卷名不能为软链接，无法确认时拒绝写入；检查也覆盖大小写变体和路径软链接指向的卷；该路径不接受 `..`。卷目录下更深的软链接仍被解析，可能指向其他卷；使用外接盘时须检查解析后的 `DATA_ROOT`。其他系统不对 `/Volumes` 特判。预检失败时，仅从最深层开始移除本次新建且仍为空的目录，并同步受影响的父目录；已有目录和文件不会删除，无法清理或同步的目录会出现在错误信息中。真实断电行为仍需在实际设备上验证。

## Secrets

凭据只能来自 `.env`、进程环境变量或未来的 secret manager。不要把 API key、private key、数据库密码写入 defaults、profiles、jobs、experiments、日志、manifest 或配置快照。

## 修改配置后的检查

```bash
uv run python -m src check
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

## 常见配置错误

| 错误 | 处理方法 |
| --- | --- |
| `DATA_ROOT is required` 或 `DATA_ROOT must be an absolute Path` | 设置绝对的数据根目录。 |
| `DATA_ROOT is not a directory` | 检查目标或其父路径是否为普通文件。 |
| `DATA_ROOT has no existing parent` | 检查路径及挂载是否可访问。 |
| `must not contain NUL characters` | 移除路径中的 NUL 字符。 |
| `DATA_MIN_FREE_GIB` 或 `PIPELINE_LOG_LEVEL` 不合法 | 分别填写非负十进制整数或 DEBUG、INFO、WARNING、ERROR、CRITICAL。 |
| `Cannot check free disk space` | 检查数据目录所在卷和访问权限。 |
| `DATA_ROOT volume is not mounted` | 确认 `/Volumes` 下指定卷是实际挂载点且卷名不是软链接，然后重试。 |
| `DATA_ROOT does not support hard links` | 使用支持硬链接的文件系统。 |
| `DATA_ROOT is not writable` | 检查目录权限和文件系统状态。 |
