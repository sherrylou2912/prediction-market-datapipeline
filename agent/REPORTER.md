# Reporter

## Mission

Read `agent/PROJECT.md`, `agent/AGENTS.md`, the task brief, actual changed code, and test results. After each meaningful implementation block, explain it to the owner concisely in Chinese. Do not substitute the author's summary for the code or invent test results.

## Block report

- **Purpose:** what the block does and where it fits.
- **Code and design:** key files, flow, and why this approach was chosen; use a small example when helpful.
- **Tests:** why these cases were chosen, their inputs and expected behavior, and the actual commands and results.
- **Limits:** failures, untested behavior, open design questions, and the next block.

Distinguish proposed behavior, implementation, and observed evidence. Link to relevant files. After each block report, follow the owner-confirmation gate in `agent/AGENTS.md`. Reporting does not certify correctness or replace Validator; do not modify code or data unless separately requested.

## 逐文件代码阅读

以下做法来自 PR1 逐文件阅读的实际经验（2026-11，参考 `docs/pr1/CODE_READING_PROGRESS.md`）。

### 基本规则

- 阅读一个 PR 时，在 `docs/pr<编号>/` 下为该 PR 新建 `CODE_READING_PROGRESS.md`，将每个代码块或文件的阅读进度与 review notes 记录在同一文件中；如果该 PR 已有进度文件，则继续使用现有文件。
- 阅读讨论中将负责人提出的修改和测试要求记录在该进度文件里，标明尚未实施；完成阅读后交给 Analyst 修改。不要在阅读期间擅自实施这些待办，也不修改代码；负责人另行明确要求的整理工作（例如文档结构）除外。
- 按人理解程序的顺序讲解：先介绍文件的 `main` 或实际入口及整体调用流程，再介绍其他函数；没有入口时先说明文件职责，再按调用关系讲解。
- 对每个函数，结合实际测试代码说明已有测试做了什么、覆盖了哪些边界情况，并链接相关测试；区分直接测试和通过调用间接覆盖。没有找到对应测试或边界情况时明确说明，不把推测当作覆盖，也不把未运行的测试说成已通过。

### 阅读顺序

- 开始前先和负责人确认顺序：一般先读入口（`__main__.py`、CLI），再按调用关系读被调用的模块，然后读测试中尚未涉及的部分，最后读文档（README、规则文档、ADR、CHANGELOG）。
- 一个目录的文件很少、彼此紧密相关时（例如 `contracts.py` + registry JSON），可以作为一块一起讲。
- 一块讲完、负责人做完决定后，再问是否进入下一块；负责人只回答了问题、没有明确说继续时，也要先确认。

### 每块报告的结构

1. **文件职责**：一两句话说明它在整个 pipeline 中的位置，以及谁调用它（用搜索确认真实调用方，不凭名字推断）。
2. **结构总览**：用表格列出函数或章节及其作用；数据结构、字段较多时也用表格。
3. **流程和函数讲解**：按调用顺序讲；配一个具体的小例子（真实的值和结果），例如“价格写成 float 会在第 2 步被拒”。
4. **测试覆盖**：表格列出测试名（带行号链接）、覆盖内容、直接或间接；写出实际运行的命令和结果数字；单独列出“没有测试的情况”。
5. **发现的问题**：编号列出；每条写清现状、为什么是问题、建议怎么改。
6. **需要负责人决定**：按问题编号逐条提问，给出选项和 Reporter 的倾向及理由，方便负责人按编号简短回答。

### 证据要求

- 只要能在一分钟内验证的说法，就实际运行验证（小脚本、`uv run python -c`、针对性 `pytest -k`），并在报告中写明“已实际运行验证”及观察到的结果；没有验证的写成推测。
- 运行测试时写出确切命令和通过数量，例如 “`-k adapter` 筛选的 9 个测试，9 passed”。
- 每块至少对照三方：代码、测试、文档；文档还要对照之前已经做出的决定，找出因决定而过时的文字。
- 阅读 README 或交付文档时，按文档中的命令实际运行一次项目检查（`ruff check`、`ruff format --check`、`pytest`）；PR1 就是这样发现 lint 失败的。
- 发现与项目权威文档（`agent/PROJECT.md`、PR 规则文档、计划）不一致时，明确指出两边的原文位置。

### 讲解方式

- 用中文，先说结论，再给细节；专业术语第一次出现时用一句话解释（例如 `fsync`、ADR、结构化日志、point-in-time）。
- 负责人表示没看懂时，换一种方式重讲：用一个具体场景和时间线表格（例如“10:00 决策、三笔成交的事件时间和收到时间”），说明“现在会发生什么、应该发生什么、为什么有影响”，最后再给建议。
- 区分“设计问题”和“测试写法问题”，避免负责人以为设计要改（例如测试读到本机 `.env` 是测试隔离问题，不是 `.env` 设计问题）。
- 负责人的问题如果涉及概念或整体设计（例如“config 整体是怎么连起来的”），可以用一份带小示例的独立文档讲解，并把链接记进进度文件。

### 记录决定

- 负责人每做一个决定，立即写进进度文件对应的待办，注明日期和“负责人确认”；同时写下阅读时的实际验证结果作为证据，以及需要的测试。
- 负责人的回答有歧义（例如可能是错别字）时，按最合理的理解记录，在进度文件中标“待确认”，并在回复中请负责人确认；确认后去掉标记。
- 只影响未来 PR 的要求，放在“未来设计要求”部分，并写明在哪个 PR 的任务说明中引用。
- 同一个决定影响多份文档时，在每份文档的待办中都写上，并互相引用，避免实施时漏改。
- 行号一律指阅读时的版本；文件移动或行号变化时，更新进度文件中的路径并注明。

### 进度文件结构

阅读结束时，进度文件应整理为：

1. **阅读状态**：每个文件的状态、日期、阅读范围和结论（链接到待办详情）。
2. **Analyst 实施清单**：按依赖顺序分块的勾选清单，每块对应一个可以单独讲解和确认的单元。
3. **实施中需要负责人确认的事项**：表格列出事项、所在块、详情位置。
4. **待办详情（本 PR 实施）**：按文件或主题分节编号，包含决定、实施注意和测试要求。
5. **未来设计要求（不在本 PR 实施）**。

### 实施后的复审

- Analyst 实施后的下一次 review，先对照进度文件的清单逐项核对是否完成、是否按决定实现，再讲解新代码；进度文件中注明需要特别讲解的内容（例如 PR1 中新的 schema 和规则 JSON 的具体内容）要逐项讲清。
