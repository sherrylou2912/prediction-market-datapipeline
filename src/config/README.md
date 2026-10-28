# 配置位置与使用说明

本文件面向配置使用者，记录当前已经实现的配置放在哪里、如何覆盖以及在什么阶段调用。未来结构见 [`developing.md`](developing.md)，开发摘要见 [`README_FOR_DEVELOPER.md`](README_FOR_DEVELOPER.md)。

## 当前文件位置

| 位置 | 内容 |
| --- | --- |
| `src/config/defaults/storage.json` | 写任务开始前要求的最小剩余空间，默认 `200` GiB。 |
| `src/config/defaults/runtime.json` | 默认日志级别，当前为 `INFO`。 |
| `.env` | 本机配置和 secrets；受 Git 忽略。 |
| `.env.example` | 可用环境变量名称，不含真实 secret。 |
| `src/config/models/pipeline.py` | `PipelineConfig` 设计图纸及数据目录预检。 |
| `src/config/loader.py` | 读取 JSON、`.env` 和进程环境变量。 |
| `src/config/errors.py` | 配置错误类型。 |
| `src/config/__init__.py` | 对外导出 `PipelineConfig` 和 `ConfigError`。 |

PR1 尚未实现真实 initial load、incremental load、validation job 或 backtest，因此当前没有对应的 task models、profiles、jobs 或 experiments 文件。

## 当前字段

| 字段 | 来源 | 用途 |
| --- | --- | --- |
| `data_root` | `DATA_ROOT`，必填 | 所有数据层的绝对根目录。 |
| `min_free_gib` | `DATA_MIN_FREE_GIB` 或 `defaults/storage.json` | 写任务开始前的最小剩余空间。 |
| `log_level` | `PIPELINE_LOG_LEVEL` 或 `defaults/runtime.json` | 运行日志级别。 |
| `config_dir` | `PIPELINE_CONFIG_DIR` 或 `src/config/defaults/` | 本次实际使用的默认配置目录。 |

优先级为：进程环境变量 > 本机 `.env` > version-controlled JSON default。空的覆盖值会回退到 JSON 默认值；`DATA_ROOT` 没有默认值。

## 调用方式

通用无副作用检查：

```bash
uv run python -m src check
```

它只加载配置并检查 `DATA_ROOT` 是否适合作为目录，不检查磁盘空间、不试写，也不创建目录。

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

## Secrets

凭据只能来自 `.env`、进程环境变量或未来的 secret manager。不要把 API key、private key、数据库密码写入 defaults、profiles、jobs、experiments、日志、manifest 或配置快照。

## 修改配置后的检查

```bash
uv run python -m src check
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```
