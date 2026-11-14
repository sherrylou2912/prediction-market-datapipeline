# Prediction Market Data Pipeline

This repository contains the foundation of a new, versioned prediction-market data pipeline. The pipeline is designed for reproducible research, traceable source records, and recoverable data collection. `agent/PROJECT.md` is the architecture authority.

## Current scope

The pipeline foundation currently provides configuration loading, startup checks, six data layers with scoped writers, Bronze/Silver/Gold row contracts, a venue adapter interface, a network-free mock adapter, and a SQLite ledger that registers runs, file manifests, and checkpoints, plus a read-only `audit` command. It does not download venue data yet. Future work begins when the project owner authorizes the next PR.

## Source layout

`src/` holds the pipeline code. Each folder has one responsibility:

| Path | Responsibility |
| --- | --- |
| `src/config/` | Load configuration and check its values and the data disk. |
| `src/config/defaults/` | Editable, version-controlled non-secret defaults. |
| `src/data_schema/` | Versioned Bronze, Silver, and Gold row contracts. |
| `src/data_io/` | Create data directories, restrict each writer to its assigned layer, and keep the run/manifest/checkpoint ledger. |
| `src/adapters/` | Venue interface and a deterministic mock implementation. |
| `src/cli.py`, `src/__main__.py` | The non-writing `python -m src check` and `python -m src audit` commands. |

There is no real data loader yet. `src/data_io/` contains the directory and writer foundation for future loading work.

## Python environment and required libraries

Use Python 3.9 or newer and install `uv`. Run these commands from the repository root:

```bash
uv sync --locked --group dev
uv run python -m src check
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

Run the startup command after setting `DATA_ROOT` as described below. `uv sync --locked --group dev` creates or updates the local `.venv` from the committed lockfile and includes the test and lint tools. The `--locked` flag prevents an accidental lockfile update during installation. `.venv` is local and ignored by Git; do not edit installed packages inside it.

**Where are the required library names?** Root [`pyproject.toml`](pyproject.toml) lists runtime libraries, including `pyarrow`, `python-dotenv`, and `pydantic`, in `[project].dependencies`. The same file lists `pytest` and `ruff` in `[dependency-groups].dev`. Root [`uv.lock`](uv.lock) records the resolved package versions and transitive dependencies. To change a requirement, edit `pyproject.toml`, regenerate `uv.lock` with `uv lock`, and commit both files together.

Dependency versions are controlled, but wheel distribution is not configured: `pyproject.toml` has no build backend. Run commands from the repository root so Python can import `src` directly.

## Configure the pipeline

Copy `.env.example` to `.env`, set `DATA_ROOT` to an absolute path on the intended data volume, then run the non-writing configuration check:

```bash
cp .env.example .env
# Edit .env and set DATA_ROOT.
uv run python -m src check
```

See the [configuration guide](src/config/README.md) for settings, precedence, preflight checks, and startup errors.

## Data layout and writer boundaries

After a write job passes `validate_for_write()`, it calls `DataLayout.create()` to create `imports/`, `bronze/`, `silver/`, `gold/`, `quarantine/`, `manifests/`, and `recovery/` under `DATA_ROOT`. A `.writer.lock` coordinates cooperating writers and recovery on one machine. By default the lock does not wait: if another writer (or another `DataLayout` in the same process) holds it, `DataLayout.create()` and each write fail immediately with `WriteBoundaryError` and leave data untouched. Setting `writer_lock_timeout_seconds` (0–3600, see the configuration guide) and passing it as `DataLayout.create(root, lock_timeout_seconds=...)` makes them wait up to that many seconds before failing the same way. While holding the lock, `DataLayout.create()` scans all six layers for abandoned partial files and re-checksums every file in `recovery/`, so initialization takes longer as data grows; the scan is intentionally not narrowed. The general `check` command does not create these directories. A writer is bound to one layer:

| Writer role | Allowed directory |
| --- | --- |
| `IMPORTER` | `imports/` |
| `COLLECTOR` | `bronze/` |
| `NORMALIZER` | `silver/` |
| `PRODUCT` | `gold/` |
| `VALIDATOR` | `quarantine/` |
| `REGISTRY` | `manifests/` |

A `COLLECTOR` write uses the receipt ID as the file's immediate parent directory, such as `bronze/source/run-1/file.jsonl`, and supplies the same `receipt_id`. Receipt IDs must match `[a-z0-9][a-z0-9_-]*`; invalid IDs are rejected rather than silently changed, preventing case or Unicode aliases. The writer rejects paths outside its layer, traversal, symlink escapes, and nested mounts on a different device. A byte-identical retry of the same receipt succeeds; conflicting data is retained in `recovery/` and raises an error. Recovery metadata references its expected `.bin` payload; a JSON record without that payload is an incomplete recovery, and layout initialization logs it for review. Initialization checks recovery metadata and matching payload checksums and stops on inconsistencies without overwriting evidence. Publication uses a temporary sibling and a hard link. A writer call alone does not register a manifest or advance a checkpoint; use the run ledger below.

Directory preparation retries the parent-directory sync even when a prior attempt left the directory behind. Recovery rejects partial metadata that lacks a valid original modification time or does not mark integrity as unknown; rebuilt metadata for an orphaned payload retains unknown integrity without inventing the original modification time.

## Runs, manifests, and checkpoints

The ledger is a SQLite file at `DATA_ROOT/manifests/ledger.sqlite3` ([ADR-003](docs/adr/ADR-003-pr2-sqlite-ledger.md); PostgreSQL can replace it later). A write task wraps its work in a run:

```python
with Run.start(layout, config, RunSpec(task="mock_backfill", task_version="1")) as run:
    run.commit_file(WriterRole.NORMALIZER, "silver/trades/x.parquet", payload,
                    FileFacts(dataset="silver.trades", row_count=2, validation="contract per row"),
                    CheckpointAdvance(key="mock/trades", cursor="page-2", expected_version=0))
    run.finish("succeeded")  # or "partial" / "failed"
```

`commit_file` publishes the file durably, then in one ledger transaction registers its manifest entry (checksum and size computed by the ledger, schema version from the contract registry) and advances the checkpoint. A checkpoint whose current version differs from `expected_version` is not advanced and nothing is registered. `finish` stores the final status, then publishes `manifests/runs/<run_id>/record.json` and `report.md` built from the ledger; the record contains the code commit and uncommitted-change flag, the effective configuration with its sources and hash, parameters, counts, files, and checkpoints. An exception inside the `with` block records the run as `failed`.

If a process stops between publishing a file and registering it, the file stays unregistered. `uv run python -m src audit` is read-only and reports unregistered, changed, unreadable, or missing files, symbolic links (never followed), abandoned partials, recovery payloads and orphaned recovery metadata, unfinished runs, and missing run records; it exits 0 when clean, 1 with issues, and 2 on errors. Run it while no writer is active: a running writer can make transient issues appear. If the ledger has a rollback journal (a write in progress or interrupted), audit refuses with exit 2 instead of letting SQLite roll it back; the next write task performs that rollback. `imports/` and `quarantine/` are not registered or audited yet.

## Data contracts and adapter interface

[Data Contracts v7](docs/SCHEMAS.md) defines the Bronze raw envelope, eight Silver datasets, and five Gold products including `gold.market_1m`. Field tables are generated from the JSON registry in `src/data_schema/schema_registry.json` and checked by tests. `validate_record` enforces row shape, types, UTC timestamps, declared row rules, and the first point-in-time check. A later training and backtest check will also apply the configured information delay; that check is not yet implemented. File-wide uniqueness, coverage, and source-specific quality checks belong to the later validation gate.

Bronze records can represent a source without a venue or API version and retain either JSON text or original bytes, including malformed or non-UTF-8 content. These are record contracts, not a large-file importer or a persistence workflow; actual source-specific file handling and manifests remain future work. An ingestion timestamp earlier than receipt is kept in Bronze but prevents every `VenueAdapter` from normalizing the record until reviewed.

`VenueAdapter` defines five collection operations, seven normalization operations, and nine metadata fields, including the venue and API/protocol identity used to check routing. Collection returns source records; the future orchestrator wraps and persists them as Bronze records before normalization. The mock uses in-memory data to demonstrate pagination, time filtering, provenance, all Silver normalizers, and explicitly identifies book snapshots and deltas. `NormalizationError` retains the evidence for future quarantine, while unsupported capabilities and adapter routing errors raise separate errors. There are no real API calls or quarantine job yet.

Invalid Bronze envelopes and source JSON exceeding the parser's nesting limit are reported as normalization errors. When evidence can be copied, `evidence_is_snapshot` is true and `raw_record` is an independent copy; if copying fails or the mapping or value type has unverified access or copy behavior (including custom subclasses), it is false and `raw_record` retains the input reference, which can change later. A read-only mapping proxy is copied, and therefore normalized like a plain `dict`, only when its underlying mapping can be confirmed as a built-in dictionary; otherwise it takes the reference path. The confirmation uses CPython's `gc.get_referents`; on other Python implementations a valid proxy safely falls back to the reference path and is not normalized. Evidence is copied before routing, so a misrouted envelope that cannot be copied is reported as a normalization error rather than a routing error. `evidence_copy_error_type` identifies the copy failure type. The exception alone does not persist that evidence or place it in quarantine.

## Run checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

The focused acceptance tests are in `tests/test_pipeline_foundation.py`. They cover startup failures, configuration precedence, writer boundaries, schema/document agreement, point-in-time checks, and the mock adapter chain.

## Legacy code

The upstream analysis workflow and indexers (`src/common/`, `src/indexers/`, `src/analysis/`, `main.py`, `make index/analyze/package/setup`) are not on `main`. They are preserved unchanged on the branch `archive/upstream-main-2026-11-13`; later migration PRs bring pieces into the pipeline from there through the adapter and writer interfaces. Its `make setup` downloads a large archive into the old `data/` layout and must not be used to initialize this pipeline.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture and execution plan](agent/PROJECT.md)
- [数据基础规则](docs/FOUNDATION_RULES.md)
- [Data contracts](docs/SCHEMAS.md)
- [数据契约规则说明](docs/SCHEMA_GUIDE.md)
- [Architecture decision records](docs/adr/)
- [Configuration guide](src/config/README.md)
- [Configuration developer summary](src/config/README_FOR_DEVELOPER.md)
- [Configuration evolution rules](src/config/developing.md)

## Origin and license

This repository started as a clone of [jon-becker/prediction-market-analysis](https://github.com/jon-becker/prediction-market-analysis). Its license is retained in [`LICENSE`](LICENSE). The upstream research citations and dataset references remain on `archive/upstream-main-2026-11-13`.
