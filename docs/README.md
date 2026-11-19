# 文档索引

`main` 分支上所有 Markdown 文档的位置和用途。新增正式文档时放进下表对应的位置，并在这里登记。

`main` 只放正式文档。审查日志、代码阅读进度、计划、负责人笔记等过程记录放在各 PR 工作分支的 `docs/pr<N>/` 下，合并后保留该分支作为审计记录：PR1 的过程记录在分支 `codex/pr1-architecture`，PR2 的在分支 `codex/pr2-run-ledger`。旧代码和旧流程文档在分支 `archive/upstream-main-2026-11-13`。

## 目录约定

| 位置 | 放什么 |
| --- | --- |
| 仓库根目录 | 约定俗成的入口文件：`README.md`、`CHANGELOG.md`、`AGENTS.md` |
| `agent/` | 项目权威总览和 agent 角色规则 |
| `docs/` | 长期有效的正式文档：数据基础规则、数据契约及其规则说明 |
| `docs/adr/` | 架构决策记录（ADR），已接受的 ADR 不改写，新决定写新 ADR |
| `docs/reports/` | 每个 PR 合并后的总结汇报（HTML），面向需要了解结果和风险的读者 |
| `src/config/` | 配置模块自带的使用、开发和演进文档 |

## 文档清单

### 入口

| 文档 | 用途 |
| --- | --- |
| [`README.md`](../README.md) | 项目首页：范围、安装、配置、检查命令 |
| [`CHANGELOG.md`](../CHANGELOG.md) | 变更记录 |
| [`AGENTS.md`](../AGENTS.md) | agent 入口，指向 `agent/` |
| [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) | GitHub PR 描述模板（来自上游项目） |

### 项目权威与 agent 规则

| 文档 | 用途 |
| --- | --- |
| [`agent/PROJECT.md`](../agent/PROJECT.md) | v1 架构、数据布局、执行计划；文档冲突时以它为准 |
| [`agent/AGENTS.md`](../agent/AGENTS.md) | 共享工作流（阶段与两层循环、独立子代理）、负责人提问格式、对负责人的讲解要求、硬性规则和约定 |
| [`agent/ORCHESTRATOR.md`](../agent/ORCHESTRATOR.md) | Orchestrator（主会话）：启动各角色子代理、转交问题、提交已收敛的块、维护 `PROGRESS.md`、快捷命令的具体执行 |
| [`agent/PLANNER.md`](../agent/PLANNER.md) | Planner：写任务说明、划分代码块和验收例子 |
| [`agent/ANALYST.md`](../agent/ANALYST.md) | Analyst：实施确认过的代码块，逐条处理 Reviewer 意见 |
| [`agent/REVIEWER.md`](../agent/REVIEWER.md) | Reviewer：内循环中逐轮审查，用通俗方式提出设计问题（分阻塞 / 非阻塞），直到没有阻塞性意见 |
| [`agent/REPORTER.md`](../agent/REPORTER.md) | Reporter：阶段完成后逐块讲解（一次一块），反馈修改后只汇报改动 |
| [`agent/VALIDATOR.md`](../agent/VALIDATOR.md) | Validator：所有阶段验收后对整个 PR 的独立最终验证 |
| [`.claude/agents/`](../.claude/agents/)、[`.claude/commands/`](../.claude/commands/) | Claude Code 的角色子代理定义和快捷命令（`/status`、`/continue-work`、`/explain`、`/start-fixes`、`/accept-phase`、`/decisions`、`/validate`、`/save-progress`） |

### 长期文档

| 文档 | 用途 |
| --- | --- |
| [`docs/FOUNDATION_RULES.md`](FOUNDATION_RULES.md) | 负责人确认的数据基础规则（分层、时间、版本、审核、看板等），补充 `agent/PROJECT.md` |
| [`docs/SCHEMAS.md`](SCHEMAS.md) | 数据契约字段及规则（由 registry 生成，路径不要移动） |
| [`docs/SCHEMA_GUIDE.md`](SCHEMA_GUIDE.md) | 数据契约规则逐项说明、关键选择及已知限制 |
| [`docs/reports/PR1_REPORT.html`](reports/PR1_REPORT.html) | PR1 汇报：结论与风险、重要配置说明、每轮代码设计改动和证据（在浏览器中打开） |
| [`docs/adr/ADR-001-v1-architecture.md`](adr/ADR-001-v1-architecture.md) | ADR-001：单机、版本化数据 pipeline（已接受） |
| [`docs/adr/ADR-002-pr1-foundation.md`](adr/ADR-002-pr1-foundation.md) | ADR-002：PR1 基础设施和契约补充决定（已接受） |
| [`docs/adr/ADR-003-pr2-sqlite-ledger.md`](adr/ADR-003-pr2-sqlite-ledger.md) | ADR-003：SQLite 运行账本、写锁等待和运行记录（已接受） |

### 配置模块

| 文档 | 用途 |
| --- | --- |
| [`src/config/README.md`](../src/config/README.md) | 配置使用说明 |
| [`src/config/README_FOR_DEVELOPER.md`](../src/config/README_FOR_DEVELOPER.md) | 配置开发者摘要 |
| [`src/config/developing.md`](../src/config/developing.md) | 配置结构演进规则 |
