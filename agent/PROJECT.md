# Prediction Market Data Pipeline — Project Overview

> Single source of truth for all future development (v1). For a beginner-friendly walkthrough, see the Chinese explainer doc. This document is the authority when docs disagree.

This document describes the project and planned PRs, not proof of implementation or current external API behavior. Verify the active branch, worktree, actual code, tests, and relevant current source documentation before making status claims. Use `agent/AGENTS.md` for shared rules and the role guides in `agent/` for the current task.

负责人确认的 PR1 基础规则和实现边界见 [`docs/PR1_FOUNDATION_RULES.md`](../docs/PR1_FOUNDATION_RULES.md)。该文档补充本总览；如果两者发生冲突，以本总览为准，并在实施前与负责人确认修正。

## 1. Goal & v1 Boundaries

**Goal**: Build a highly-engineered data factory for prediction-market research, without introducing unnecessary distributed complexity.

| Dimension | v1 Decision |
|---|---|
| Primary consumers | 离线研究与 taker 策略；首个研究产品以 1 分钟数据为目标 |
| Forward-looking capability | Keep the ability to reconstruct second-level market-maker order books |
| Venues | Kalshi + Polymarket |
| Deployment | Single on-prem server or single cloud host |
| Historical data | Build reliable storage + audit mechanisms in parallel with downloading and importing |

**What "industrial-grade" means here** (discipline, not hardware): idempotency, atomic commits, complete audit records, failure recovery, data contracts, point-in-time correctness, verifiable data coverage.

**Data correctness is the product.** This pipeline exists for one reason: downstream research and trading decisions must be able to trust the data. A single silently-corrupted dataset can invalidate months of research — or worse, lead a live strategy to the wrong conclusion. Correctness is therefore not a final "validation step"; it is designed into every layer: append-only raw storage (§3), an independent validation gate before Silver (§4), atomic checkpoints and manifests (§6), and acceptance criteria that must all pass before Phase 1 is done (§9). Whenever a choice trades correctness for speed or convenience, correctness wins. Non-negotiable.

**可视化是重要的数据使用方式。** 未来使用一个本地服务支持的 HTML 交互式看板，按选择的市场、时间和指标懒加载历史数据；不为每个 Parquet 文件自动生成静态图。用户可按需导出当前图表。看板展示数据版本、覆盖情况和相关问题，实际查询性能需要验证。

## 2. Status & Key Discovery

- The existing code (`prediction-market-datapipeline`, a clone of jon-becker/prediction-market-analysis) is a runnable starting point, but its API usage is behind current official interfaces:
  - **Kalshi**: data is now split into live and historical tiers; calling only `/markets` and `/markets/trades` no longer guarantees complete history. Must read the cutoff and combine both endpoints, with dedup + reconciliation at the migration boundary.
  - **Kalshi WebSocket**: sends an orderbook snapshot first, then sequenced incremental deltas → ideal for building a recoverable book recorder.
  - **Polymarket market stream**: provides full book, price changes, last trade, best bid/ask, tick-size changes, and resolution events → sufficient for second-level book research.
  - **Polymarket** is rolling out a unified SDK, Data API v2, and Protocol V2; existing code only covers the old CTF/NegRisk/FPMM contracts → adapters must carry an API/protocol version; contract addresses and field models must not be hardcoded.
- **Conclusion**: Phase 1 is not "fix the old indexers" — it is to establish a **versioned source-adapter framework**.

## 3. Architecture Decisions (v1)

| Component | v1 Choice | Rationale |
|---|---|---|
| Historical + streaming raw data | 保留带来源信息的原始内容和文件，按来源选择格式 | 不强制所有输入转成 JSON，保留原始证据 |
| Normalized data | Partitioned Parquet | Fast scans by date/market |
| Research queries | DuckDB | Serverless, single-machine |
| Checkpoints / runs / manifests | PostgreSQL | Ledger database |
| Scheduling | Plain CLI + systemd/cron (adopt Dagster once stable) | Simple first |
| Observability | Structured logs + PostgreSQL run records + metrics | — |
| Message queue | No Kafka in v1 | Not needed at this scale |
| Iceberg / ClickHouse | Interface reserved, not adopted in v1 | — |

## 4. Dual-Path Data Pipeline

Batch (historical archives / REST / blockchain) and stream (WebSocket recorders) converge into one canonical model:

```
Historical archive / REST / Blockchain
                │
                ▼
          Batch collectors
                │
                ├──────────────┐
                ▼              │
          Bronze Raw           │
                ▲              │
                │              │
         WebSocket recorders   │
                ▲              │
 Kalshi / Polymarket live      │
                               ▼
                    Validation + Quarantine
                               │
                               ▼
                       Silver Canonical
                         │             │
                         ▼             ▼
              1-minute research   1-second market data
                         │             │
                         ▼             ▼
                  Taker features   Maker features
```

**Priority rule**: historical trades can be backfilled, but historical orderbook deltas cannot — the WebSocket recorder ships first.

未来数据处理流程：读取并保存原始证据，发现问题时进入人工审核与修复；合格数据可进入 Silver，最终 Gold 入库前执行独立验证。异常可经人工审核后附 caveat 继续，回测报告必须说明相关问题。未经确认的历史可用时间不得当作事实；经人工批准的假设应明确记录。

## 5. Data Layout

```
data/
├── imports/
│   └── legacy_archive/          # legacy bundle: source-manifest.json, archive.sha256, extracted/
├── bronze/
│   ├── kalshi/                  # markets/ trades/ orderbook/ lifecycle/
│   └── polymarket/              # markets/ trades/ orderbook/ lifecycle/ blockchain_logs/
├── silver/
│   ├── events/ markets/ outcomes/ market_states/
│   ├── trades/ book_snapshots/ book_deltas/ settlements/
├── gold/
│   └── <venue>/<market_id>/market_1m/<data_version>/<UTC-date>.parquet
├── quarantine/
└── manifests/
```

**Hard rule**: the data root must come from `DATA_ROOT` config. Never hardcode `data/...` paths in code.

上面的 Gold 路径是首个分钟研究产品的目标约定，不表示已经实现；每个文件只含一个市场和一个 UTC 日期，同一市场的 outcome 可以共用文件。数据版本的 manifest 可引用旧版本中未变化的文件。市场 ID 必须安全映射到路径并保留来源标识。

## 6. Audit & Recoverability (Keep Record)

Every run must leave a complete audit trail:

- **Run record**: run_id, collector + version, venue, dataset, start/end time, backfill range, status/errors, request count / rows received / rows written / rows quarantined, code commit SHA, config summary.
- **Checkpoint record**: cursor / timestamp / block number, last successfully committed data file, source watermark, validation-complete flag, update version.
  - **Advancement rule**: a checkpoint may only move forward after the data file is durably written + validated + registered in the manifest.
- **File manifest**: path, row count, schema version, min/max event time, min/max source sequence, checksum, primary-key hash, creating run ID.
- **Raw record envelope**: venue, source, message_type, source_event_id, event_time, received_at, ingested_at, sequence, schema_version, raw_payload.

原始数据也可能来自非 venue 来源或原始文件；缺失或不适用的来源信息不能编造。Bronze 已保存内容不得静默改写；未来归档或清理必须有可核查的清单并经负责人确认，保留审核与追溯记录。每个运行的机器可读记录使用 JSON；人可读 Markdown 默认生成，可由任务设置关闭。PostgreSQL 账本、JSON 记录和文件的一致性与中断恢复属于后续实现。

## 7. Second-Level Book Storage Strategy

Do not store full L2 books every second. Store:
1. All raw snapshots and deltas;
2. Connect/disconnect/reconnect and sequence-gap events;
3. A fresh snapshot after every reconnect;
4. Optional periodic full snapshots every 1–5 minutes;
5. 1-second BBO/depth features reconstructed from deltas.

Gold `market_1s` columns: best bid/ask, spread, mid, microprice, top-N depth, imbalance, last trade, rolling volume, update count, book age, receive latency, gap/recovery flag.

## 8. Venue Adapter Interface (Standard for New Venues)

Adding a venue (e.g., PredictIt) means implementing an adapter only — no changes to storage / validation / preprocessing:

```python
class VenueAdapter:
    def discover_markets(...)
    def backfill_markets(...)
    def backfill_trades(...)
    def fetch_settlements(...)
    def stream_market_data(...)
    def normalize_market(...)
    def normalize_trade(...)
    def normalize_book_event(...)
```

Each adapter must declare: supported capabilities, API/protocol version, primary keys, pagination/checkpoint semantics, rate limits, timestamp semantics, price/quantity precision, validation rules.

## 9. Execution Plan

### 9.1 Four parallel tracks

- **Track A — 下载与导入框架**：支持续传、下载至 `.partial`、记录 URL/ETag/Content-Length/SHA-256、原子重命名、解压到 staging、防路径穿越、生成 manifest，并在 profiling 和验证后提升数据。可采用仅归档、流式解压或导入后删除；删除前必须生成可审核清单并由负责人确认。
- **Track B — Real-time recorders first**: Polymarket public market-stream recorder → Kalshi recorder (needs API credentials) → snapshot/delta reconstruction with sequence-gap detection → 1-second BBO data product.
- **Track C — Import historical archive**: keep legacy structure untouched; read schema and time coverage; compute duplicates/gaps/outages; convert to Silver; overlap reconciliation against API backfills.
- **Track D — 历史回填重构**：Kalshi live 和 historical cutoff 双路径；Polymarket API 元数据与链上日志；处理确认和 reorg；历史回填与实时采集交接。等价重跑应产生可复现的规范化结果；Bronze 保留重复接收证据。
- **磁盘限制**：旧快照曾记录约 139 GiB 可用空间及 36 GiB 归档包；规划前应重新确认当前卷和归档大小。解压、staging 和重写需要额外空间 → **不要直接运行旧的 `make setup`**。

### 9.2 Phase 1 — 7 PRs

1. Architecture, data contracts, config & directory conventions
2. Run registry, checkpoint, manifest, atomic writer
3. Resumable downloader, legacy importer, data profiler
4. Validation, quarantine, quality reports
5. Kalshi v2 adapter: live + historical
6. Polymarket versioned adapter: API + blockchain
7. WebSocket raw recorder, book reconstruction, 1-second BBO

### 9.3 Phase 1 Done Criteria

- [ ] Any job killed mid-run recovers safely
- [ ] 重跑同一时间范围不增加重复的规范化记录；Bronze 可以保留重复接收证据
- [ ] Every dataset can report exact time coverage and gaps
- [ ] Every landed file has a manifest + checksum
- [ ] Anomalous records can never silently enter Silver
- [ ] Any Silver row traces back to its raw payload and run
- [ ] Book sequence gaps are detected and trigger automatic snapshot refetch
- [ ] 适用的研究数据集（包括 1 分钟和 1 秒产品）通过 point-in-time 测试

## 10. Open Inputs Before Kickoff

1. **数据位置**：旧快照记录的 139 GiB 可用空间较紧张；规划前重新检查当前空间，建议准备至少 200–250 GiB，或将外部磁盘路径配置为 `DATA_ROOT`。
2. **Kalshi API key**: not blocking overall (Polymarket stream + Kalshi REST/backfill can proceed), but required for the Kalshi orderbook WebSocket.

**Recommended order**: freeze design in repo docs → PRs 1–3 (config/contracts, reliable writes, resumable download + profiling) → start the large download (develop the WebSocket recorder in parallel).

## 11. General Guidelines

> Cross-cutting principles that apply to every PR. When in doubt, these win over local convenience.

1. **Simplicity first**: choose the simplest solution that satisfies the contract. No premature abstraction, no distributed systems "just in case".
2. **Single source of truth**: this document is authoritative. Code, docs, and comments must agree with it; when they don't, fix them — not this document (change the document only via explicit decision).
3. **Contracts before code**: data schemas and interfaces are written down before implementation starts.
4. **No silent failures**: errors are logged, quarantined, or raised — never swallowed, never `except: pass`.
5. **可复现性**：记录代码版本、配置、输入 manifest、方法和输出，以便调查并在可行时复现。部分 NLP 模型等非确定性方法即使可追溯，也不能保证每次输出完全一致。
6. **Secrets hygiene**: secrets come from the environment only. Never in code, logs, prompts, or docs.
7. **Small PRs**: one PR does one thing, touches one concern, and passes all gates before merge.
8. **Documentation is a deliverable**: every PR updates the docs it affects (PROJECT.md, schemas, docstrings, CHANGELOG).
9. **Boring technology**: prefer proven, well-understood tools over novel ones for load-bearing parts.
10. **Optimize for debuggability**: when choosing between two designs, pick the one that is easier to investigate at 2am.

## 12. Glossary

| Term | Meaning |
|---|---|
| Bronze / Silver / Gold | Raw layer (as-received) / canonical layer (unified schema) / product layer (purpose-built) |
| Venue | Trading venue (Kalshi, Polymarket) |
| Taker / Maker | Aggressive (market) side / passive (limit) side |
| BBO | Best bid and offer |
| Snapshot / Delta | Full book image / book change |
| Sequence gap | Missing sequence numbers in the delta stream |
| Point-in-time | Backtests may only use information known at the time |
| Idempotent | Re-running yields the same result as running once |
| Atomic commit | All-or-nothing landing |
| Quarantine | Holding area for records that fail validation |
| Manifest | A data file's "ID card" (checksum, row count, time range, …) |
| Canonical model | One unified schema across all venues |
