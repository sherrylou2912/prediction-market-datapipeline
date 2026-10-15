# Prediction Market Data Pipeline — Project Overview

> Single source of truth for all future development (v1). For a beginner-friendly walkthrough, see the Chinese explainer doc. This document is the authority when docs disagree.

## 1. Goal & v1 Boundaries

**Goal**: Build a highly-engineered data factory for prediction-market research, without introducing unnecessary distributed complexity.

| Dimension | v1 Decision |
|---|---|
| Primary consumers | Offline research, daily-frequency taker strategies |
| Forward-looking capability | Keep the ability to reconstruct second-level market-maker order books |
| Venues | Kalshi + Polymarket |
| Deployment | Single on-prem server or single cloud host |
| Historical data | Build reliable storage + audit mechanisms in parallel with downloading and importing |

**What "industrial-grade" means here** (discipline, not hardware): idempotency, atomic commits, complete audit records, failure recovery, data contracts, point-in-time correctness, verifiable data coverage.

**Data correctness is the product.** This pipeline exists for one reason: downstream research and trading decisions must be able to trust the data. A single silently-corrupted dataset can invalidate months of research — or worse, lead a live strategy to the wrong conclusion. Correctness is therefore not a final "validation step"; it is designed into every layer: append-only raw storage (§3), an independent validation gate before Silver (§4), atomic checkpoints and manifests (§6), and acceptance criteria that must all pass before Phase 1 is done (§9). Whenever a choice trades correctness for speed or convenience, correctness wins. Non-negotiable.

**Visualization is a first-class consumer.** Every Gold dataset ships with default visual outputs (PNG/PDF figures plus JSON chart configs for web display), produced through the unified chart interface. Charts are how researchers spot data problems early — visualization doubles as a correctness tool, not just presentation.

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
| Historical + streaming raw data | Append-only files: JSONL.zst / Parquet.zstd | Immutable, cheap |
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
               Daily research    1-second market data
                         │             │
                         ▼             ▼
                  Taker features   Maker features
```

**Priority rule**: historical trades can be backfilled, but historical orderbook deltas cannot — the WebSocket recorder ships first.

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
│   ├── market_daily/ market_1s/ liquidity_features/ training_datasets/
├── quarantine/
└── manifests/
```

**Hard rule**: the data root must come from `DATA_ROOT` config. Never hardcode `data/...` paths in code.

## 6. Audit & Recoverability (Keep Record)

Every run must leave a complete audit trail:

- **Run record**: run_id, collector + version, venue, dataset, start/end time, backfill range, status/errors, request count / rows received / rows written / rows quarantined, code commit SHA, config summary.
- **Checkpoint record**: cursor / timestamp / block number, last successfully committed data file, source watermark, validation-complete flag, update version.
  - **Advancement rule**: a checkpoint may only move forward after the data file is durably written + validated + registered in the manifest.
- **File manifest**: path, row count, schema version, min/max event time, min/max source sequence, checksum, primary-key hash, creating run ID.
- **Raw record envelope**: venue, source, message_type, source_event_id, event_time, received_at, ingested_at, sequence, schema_version, raw_payload.

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

- **Track A — Download & import framework**: resumable downloads, download to `.partial`, record URL/ETag/Content-Length/SHA-256, atomic rename, extract to staging, path-traversal protection, manifest generation, promote after profile + validation; three modes: archive-only / stream-extract / delete-after-import.
- **Track B — Real-time recorders first**: Polymarket public market-stream recorder → Kalshi recorder (needs API credentials) → snapshot/delta reconstruction with sequence-gap detection → 1-second BBO data product.
- **Track C — Import historical archive**: keep legacy structure untouched; read schema and time coverage; compute duplicates/gaps/outages; convert to Silver; overlap reconciliation against API backfills.
- **Track D — Rewrite historical backfill**: Kalshi live+historical cutoff dual path; Polymarket API metadata + chain logs; confirmation/reorg handling; backfill/live handoff; reruns must be bit-identical.
- **Disk constraint**: ~139 GiB free currently; the 36 GiB bundle needs more headroom after extraction + staging + rewrites → **do NOT run the old `make setup` directly**.

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
- [ ] Re-running the same interval adds no duplicate records (idempotent)
- [ ] Every dataset can report exact time coverage and gaps
- [ ] Every landed file has a manifest + checksum
- [ ] Anomalous records can never silently enter Silver
- [ ] Any Silver row traces back to its raw payload and run
- [ ] Book sequence gaps are detected and trigger automatic snapshot refetch
- [ ] Daily and 1-second data pass point-in-time tests

## 10. Open Inputs Before Kickoff

1. **Data location**: 139 GiB is tight; recommend ≥200–250 GiB free, or an external disk path as `DATA_ROOT`.
2. **Kalshi API key**: not blocking overall (Polymarket stream + Kalshi REST/backfill can proceed), but required for the Kalshi orderbook WebSocket.

**Recommended order**: freeze design in repo docs → PRs 1–3 (config/contracts, reliable writes, resumable download + profiling) → start the large download (develop the WebSocket recorder in parallel).

## 11. General Guidelines

> Cross-cutting principles that apply to every PR. When in doubt, these win over local convenience.

1. **Simplicity first**: choose the simplest solution that satisfies the contract. No premature abstraction, no distributed systems "just in case".
2. **Single source of truth**: this document is authoritative. Code, docs, and comments must agree with it; when they don't, fix them — not this document (change the document only via explicit decision).
3. **Contracts before code**: data schemas and interfaces are written down before implementation starts.
4. **No silent failures**: errors are logged, quarantined, or raised — never swallowed, never `except: pass`.
5. **Reproducibility**: any run must be reproducible from (code version + config + input manifest).
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
