# Changelog

## Unreleased (PR2)

### Added

- SQLite ledger at `DATA_ROOT/manifests/ledger.sqlite3` for runs, file manifests, and checkpoints (ADR-003). Manifest registration re-hashes the file, takes the schema version from the contract registry, and advances a checkpoint in the same transaction with optimistic versioning and history.
- Run lifecycle (`src/data_io/runs.py`): `Run.start`, `commit_file`, `add_counts`, `finish`; publishes `manifests/runs/<run_id>/record.json` and an optional `report.md` with code version, effective configuration, parameters, counts, files, and checkpoints.
- `python -m src audit`: read-only reconciliation of files against the ledger.
- Manifest registration requires Silver and Gold files to be in the folder named after their dataset (`silver/trades/…`, `gold/market_1m/…`, `gold/training_datasets/<name>/…`); Bronze files are checked by layer only. The Gold path convention moves the product name to the second level: `gold/market_1m/<venue>/<market_id>/<data_version>/<UTC-date>.parquet` (owner decision 2026-11-19).
- `writer_lock_timeout_seconds` (`PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS`, 0–3600, default 0): writers and layout initialization wait up to this many seconds for a held `.writer.lock` (0 fails immediately). Ledger transactions wait separately for SQLite's lock, for `max(writer_lock_timeout_seconds, 5)` seconds, so they wait at least 5 seconds even when the setting is 0.
- `open_write_layout(config)` in `src/data_io/layout.py`: the single way for write tasks to create the data layout. It runs `validate_for_write()` first and then `DataLayout.create` with `writer_lock_timeout_seconds`; a source scan rejects any other `DataLayout.create`, direct `DataLayout(...)` or `ScopedWriter(...)` construction, and renamed imports of these classes in `src/` (code that never names the classes, such as `type(layout)(...)`, is not detected).

### Changed

- The `REGISTRY` writer rejects `manifests/ledger.sqlite3*` targets.
- Waiting for `.writer.lock` uses a blocking `flock` in a background thread instead of polling every 50 ms, so a waiting writer is woken when the lock is released and is usually not kept out by a writer that publishes files back to back (not a strict queue). A waiter that gave up stays blocked until the lock is free and releases the lock immediately if it obtains it then; a later wait on the same lock in the same process reuses it, so retries do not accumulate threads or open files, and a forked child closes its inherited copy of the waiter's file. When several threads of one process wait, a lock obtained by a reused waiter goes only to the wait that currently owns it. The waiter thread opens and closes its own lock-file handle, so an exception raised while it is being started cannot block the caller or close that handle twice. Releasing the lock unlocks before closing, so a child forked during a write no longer keeps the lock after the parent's write ends. A program that catches Ctrl-C during a wait or release and keeps running may, in rare cases, keep the lock until it exits. A timeout of 0 still fails immediately. Verified only on macOS.

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
