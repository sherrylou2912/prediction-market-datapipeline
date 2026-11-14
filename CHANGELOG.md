# Changelog

## Unreleased (PR2)

### Added

- SQLite ledger at `DATA_ROOT/manifests/ledger.sqlite3` for runs, file manifests, and checkpoints (ADR-003). Manifest registration re-hashes the file, takes the schema version from the contract registry, and advances a checkpoint in the same transaction with optimistic versioning and history.
- Run lifecycle (`src/data_io/runs.py`): `Run.start`, `commit_file`, `add_counts`, `finish`; publishes `manifests/runs/<run_id>/record.json` and an optional `report.md` with code version, effective configuration, parameters, counts, files, and checkpoints.
- `python -m src audit`: read-only reconciliation of files against the ledger.
- `writer_lock_timeout_seconds` (`PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS`, 0–3600, default 0): writers, layout initialization, and ledger transactions wait up to this many seconds for a held lock.

### Changed

- The `REGISTRY` writer rejects `manifests/ledger.sqlite3*` targets.

## 0.1.0 — 2026-11-13

First version of the pipeline foundation (PR #1). No venue data is downloaded yet.

### Added

- `python -m src check`: validates configuration without writing data and logs each effective non-secret setting with its source and a SHA-256 of the values (`config.effective`).
- Shared configuration validated with pydantic: `DATA_ROOT`, `DATA_MIN_FREE_GIB`, `PIPELINE_LOG_LEVEL`, `PIPELINE_CONFIG_DIR`. Errors never echo input values. Read and write jobs use separate preflight checks; write jobs check free space, write access and hard-link support first.
- Data layout under `DATA_ROOT` with one writer per layer (`imports`, `bronze`, `silver`, `gold`, `quarantine`, `manifests`) plus `recovery/`. Files are published without overwriting and synced to disk; conflicting or interrupted writes are kept in `recovery/` with metadata. A writer lock fails immediately when held.
- Data contracts version 7.0.0 for 14 datasets (1 Bronze, 8 Silver, 5 Gold), declared in `src/data_schema/schema_registry.json` and enforced by `validate_record`. `docs/SCHEMAS.md` is generated from the registry.
- `VenueAdapter` interface and a network-free mock adapter. Records are routed by venue, API version and protocol version; normalization failures keep the original evidence.
- Structured JSON logging for pipeline commands.

### Changed

- `main` holds only the new pipeline and formal documents. The upstream analysis workflow and indexers are preserved on the branch `archive/upstream-main-2026-11-13`; dependencies used only by that code were removed.
