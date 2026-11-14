"""SQLite ledger for runs, file manifests, and checkpoints.

The ledger lives at ``DATA_ROOT/manifests/ledger.sqlite3``. Data files remain
the data plane; the ledger records which files are registered and how far each
checkpoint has advanced. A checkpoint advances only in the same transaction
that registers the manifest entry of its durably written, validated file.

The interface is deliberately narrow so a PostgreSQL implementation can replace
it later (ADR-003).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.data_io.layout import DataLayout, WriteBoundaryError, _digest, _require_same_device, _sync_dir
from src.data_schema.contracts import SCHEMA_VERSION, ContractError, get_contract

LEDGER_RELATIVE_PATH = Path("manifests") / "ledger.sqlite3"
LEDGER_SCHEMA_VERSION = 1
RUN_STATUSES = ("running", "succeeded", "partial", "failed")
FINAL_RUN_STATUSES = ("succeeded", "partial", "failed")
_MANIFEST_LAYERS = ("bronze", "silver", "gold")
# SQLite holds short internal locks for every read and commit, including the
# read-only audit. Waiting at least this long keeps a concurrent reader from
# failing a commit even when writer_lock_timeout_seconds is 0.
MIN_BUSY_TIMEOUT_SECONDS = 5
_SHA256 = re.compile(r"[0-9a-f]{64}")

_SCHEMA = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    task_version TEXT NOT NULL,
    venue TEXT,
    dataset TEXT,
    range_start TEXT,
    range_end TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed')),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    code_version TEXT NOT NULL,
    config TEXT NOT NULL,
    parameters TEXT NOT NULL,
    requests INTEGER NOT NULL DEFAULT 0 CHECK (requests >= 0),
    rows_received INTEGER NOT NULL DEFAULT 0 CHECK (rows_received >= 0),
    rows_written INTEGER NOT NULL DEFAULT 0 CHECK (rows_written >= 0),
    rows_quarantined INTEGER NOT NULL DEFAULT 0 CHECK (rows_quarantined >= 0),
    error TEXT,
    record_path TEXT,
    CHECK ((status = 'running') = (finished_at IS NULL))
);
CREATE TABLE manifest_files (
    path TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    dataset TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    row_count INTEGER NOT NULL CHECK (row_count >= 0),
    min_event_time TEXT,
    max_event_time TEXT,
    min_sequence INTEGER,
    max_sequence INTEGER,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    primary_key_hash TEXT,
    validation TEXT NOT NULL,
    registered_at TEXT NOT NULL
);
CREATE INDEX manifest_files_run ON manifest_files(run_id);
CREATE TABLE checkpoints (
    checkpoint_key TEXT PRIMARY KEY,
    version INTEGER NOT NULL CHECK (version >= 1),
    cursor TEXT NOT NULL,
    watermark TEXT,
    last_file TEXT NOT NULL REFERENCES manifest_files(path),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    updated_at TEXT NOT NULL
);
CREATE TABLE checkpoint_history (
    checkpoint_key TEXT NOT NULL,
    version INTEGER NOT NULL,
    cursor TEXT NOT NULL,
    watermark TEXT,
    last_file TEXT NOT NULL REFERENCES manifest_files(path),
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (checkpoint_key, version)
);
"""


class LedgerError(RuntimeError):
    """A ledger operation was rejected or could not complete; the ledger is unchanged."""


@dataclass(frozen=True)
class FileFacts:
    """Facts about a data file that only its producer knows.

    The ledger computes the checksum and size itself and takes the schema
    version from the contract registry.
    """

    dataset: str
    row_count: int
    validation: str
    event_time_range: tuple[datetime, datetime] | None = None
    sequence_range: tuple[int, int] | None = None
    primary_key_hash: str | None = None


@dataclass(frozen=True)
class CheckpointAdvance:
    """Move ``key`` to ``cursor``; ``expected_version`` is 0 for a new checkpoint."""

    key: str
    cursor: Any
    expected_version: int
    watermark: datetime | None = None


def utc_text(value: datetime, name: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is not timezone.utc:
        raise LedgerError(f"{name} must be a datetime with tzinfo=datetime.timezone.utc")
    return value.isoformat()


def json_text(value: Any, name: str) -> str:
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise LedgerError(f"{name} must be JSON-serializable without NaN or Infinity: {exc}") from exc


def _count(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise LedgerError(f"{name} must be a nonnegative integer")
    return value


def _text(value: Any, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise LedgerError(f"{name} must be a non-empty string")
    return value


def _range(value: Any, name: str, convert: Any) -> tuple[Any, Any]:
    if value is None:
        return None, None
    if not isinstance(value, tuple) or len(value) != 2:
        raise LedgerError(f"{name} must be a (minimum, maximum) tuple or None")
    low, high = convert(value[0], name), convert(value[1], name)
    if value[0] > value[1]:
        raise LedgerError(f"{name} minimum is greater than its maximum")
    return low, high


def _sequence(value: Any, name: str) -> int:
    if type(value) is not int:
        raise LedgerError(f"{name} values must be integers")
    return value


def _row(cursor: sqlite3.Cursor, row: tuple) -> dict[str, Any]:
    return {column[0]: value for column, value in zip(cursor.description, row)}


def run_values(
    *,
    run_id: str,
    task: str,
    task_version: str,
    started_at: datetime,
    code_version: Mapping[str, Any],
    config: Mapping[str, Any],
    parameters: Mapping[str, Any],
    venue: str | None = None,
    dataset: str | None = None,
    range_start: datetime | None = None,
    range_end: datetime | None = None,
) -> tuple:
    """Validate run fields without touching the ledger; returns the row values."""
    for name, value in (("code_version", code_version), ("config", config), ("parameters", parameters)):
        if not isinstance(value, Mapping):
            raise LedgerError(f"{name} must be a mapping")
    values = (
        _text(run_id, "run_id"),
        _text(task, "task"),
        _text(task_version, "task_version"),
        _text(venue, "venue", optional=True),
        _text(dataset, "dataset", optional=True),
        None if range_start is None else utc_text(range_start, "range_start"),
        None if range_end is None else utc_text(range_end, "range_end"),
        utc_text(started_at, "started_at"),
        json_text(dict(code_version), "code_version"),
        json_text(dict(config), "config"),
        json_text(dict(parameters), "parameters"),
    )
    if range_start is not None and range_end is not None and range_start >= range_end:
        raise LedgerError("range_start must be earlier than range_end")
    return values


def commit_values(path: str | Path, facts: FileFacts, checkpoint: CheckpointAdvance | None) -> dict[str, Any]:
    """Validate a commit's arguments without touching the file or the ledger."""
    relative = Path(path)
    if not isinstance(facts, FileFacts):
        raise LedgerError("facts must be a FileFacts value")
    try:
        get_contract(facts.dataset)
    except (ContractError, TypeError) as exc:
        raise LedgerError(f"Unknown dataset contract: {facts.dataset!r}") from exc
    layer = facts.dataset.split(".", 1)[0]
    if layer not in _MANIFEST_LAYERS:
        raise LedgerError(f"Dataset layer cannot be registered in this ledger: {layer}")
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or len(relative.parts) < 2
        or relative.parts[0] != layer
        or relative.name.startswith(".partial-")
    ):
        raise LedgerError(f"{facts.dataset} file must be a root-relative path under {layer}/: {path}")
    row_count = _count(facts.row_count, "row_count")
    validation = _text(facts.validation, "validation")
    min_time, max_time = _range(facts.event_time_range, "event_time_range", utc_text)
    min_sequence, max_sequence = _range(facts.sequence_range, "sequence_range", _sequence)
    pk_hash = facts.primary_key_hash
    if pk_hash is not None and (not isinstance(pk_hash, str) or not _SHA256.fullmatch(pk_hash)):
        raise LedgerError("primary_key_hash must be a lowercase SHA-256 hex digest or None")
    if checkpoint is not None:
        if not isinstance(checkpoint, CheckpointAdvance):
            raise LedgerError("checkpoint must be a CheckpointAdvance value")
        checkpoint_key = _text(checkpoint.key, "checkpoint key")
        expected = _count(checkpoint.expected_version, "expected_version")
        cursor_text = json_text(checkpoint.cursor, "checkpoint cursor")
        watermark = None if checkpoint.watermark is None else utc_text(checkpoint.watermark, "watermark")
    else:
        checkpoint_key = expected = cursor_text = watermark = None
    return {
        "relative": relative,
        "row_count": row_count,
        "validation": validation,
        "times": (min_time, max_time),
        "sequences": (min_sequence, max_sequence),
        "pk_hash": pk_hash,
        "checkpoint": None
        if checkpoint is None
        else {"key": checkpoint_key, "expected": expected, "cursor": cursor_text, "watermark": watermark},
    }


class Ledger:
    """One connection to the ledger. Not shared across threads."""

    def __init__(self, root: Path, connection: sqlite3.Connection, *, read_only: bool) -> None:
        self.root = root
        self._connection = connection
        self.read_only = read_only

    @classmethod
    def open(cls, layout: DataLayout) -> Ledger:
        """Open or create the ledger of a prepared layout for writing."""
        path = layout.root / LEDGER_RELATIVE_PATH
        existed = cls._check_file(layout.root, path, required=False)
        try:
            connection = sqlite3.connect(
                str(path),
                timeout=max(layout.lock_timeout_seconds, MIN_BUSY_TIMEOUT_SECONDS),
                isolation_level=None,
                check_same_thread=True,
            )
        except sqlite3.Error as exc:
            raise LedgerError(f"Cannot open ledger {path}: {exc}") from exc
        ledger = cls(layout.root, connection, read_only=False)
        try:
            if not existed:
                _sync_dir(path.parent)
            ledger._configure()
            ledger._initialize()
        except BaseException:
            connection.close()
            raise
        return ledger

    @classmethod
    def open_read_only(cls, root: Path) -> Ledger | None:
        """Open an existing ledger for queries only; None if absent.

        A normal connection with ``query_only`` is used instead of ``mode=ro``:
        a ``mode=ro`` reader makes a concurrent writer fail with a misleading
        disk I/O error instead of waiting. Like any SQLite reader, it rolls back
        the journal of an interrupted, uncommitted transaction (SQLite's own
        crash recovery), so opening is refused while a journal file exists. A
        writer that crashes between that check and the first read can still be
        rolled back by this reader; run read-only commands while no writer is active.
        """
        path = root / LEDGER_RELATIVE_PATH
        if not cls._check_file(root, path, required=False):
            return None
        journal = path.with_name(path.name + "-journal")
        if journal.exists() or journal.is_symlink():
            # Opening would let SQLite roll back the journal, which is a write.
            raise LedgerError(
                f"Ledger has a rollback journal ({journal}): a write transaction is running or was interrupted. "
                "Run read-only commands when no writer is active; if no writer is running, the next write task "
                "lets SQLite roll back the interrupted transaction."
            )
        try:
            with path.open("rb") as handle:
                header = handle.read(20)
        except OSError as exc:
            raise LedgerError(f"Cannot read ledger header {path}: {exc}") from exc
        wal_files = [path.with_name(path.name + suffix) for suffix in ("-wal", "-shm")]
        # Bytes 18-19 are 2 in WAL mode; a WAL reader creates -wal/-shm files.
        if header[18:20] == b"\x02\x02" or any(item.exists() or item.is_symlink() for item in wal_files):
            raise LedgerError(
                f"Ledger {path} is in WAL mode or has WAL files; the ledger must use journal_mode=DELETE. "
                "A write task reopens it in DELETE mode."
            )
        try:
            # mode=rw never creates a missing file (unlike a plain path) and,
            # unlike mode=ro, lets concurrent writers wait normally.
            connection = sqlite3.connect(
                f"{path.as_uri()}?mode=rw", uri=True, timeout=MIN_BUSY_TIMEOUT_SECONDS, isolation_level=None
            )
            connection.execute("PRAGMA query_only = ON")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
        except sqlite3.Error as exc:
            raise LedgerError(f"Cannot open ledger {path} read-only: {exc}") from exc
        if version != LEDGER_SCHEMA_VERSION:
            connection.close()
            raise LedgerError(f"Unsupported ledger schema version {version} in {path}")
        return cls(root, connection, read_only=True)

    @staticmethod
    def _check_file(root: Path, path: Path, *, required: bool) -> bool:
        if path.parent.is_symlink():
            raise LedgerError(f"Ledger directory must not be a symbolic link: {path.parent}")
        if path.is_symlink():
            raise LedgerError(f"Ledger must not be a symbolic link: {path}")
        if not path.exists():
            if required:
                raise LedgerError(f"Ledger does not exist: {path}")
            return False
        if not path.is_file():
            raise LedgerError(f"Ledger must be a regular file: {path}")
        try:
            _require_same_device(root, path)
        except WriteBoundaryError as exc:
            raise LedgerError(str(exc)) from exc
        return True

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Ledger:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _configure(self) -> None:
        try:
            for pragma in ("PRAGMA foreign_keys = ON", "PRAGMA synchronous = FULL", "PRAGMA fullfsync = ON"):
                self._connection.execute(pragma)
            mode = self._connection.execute("PRAGMA journal_mode = DELETE").fetchone()[0]
        except sqlite3.Error as exc:
            raise LedgerError(f"Cannot configure ledger: {exc}") from exc
        if str(mode).lower() != "delete":
            raise LedgerError(f"Ledger journal mode must be DELETE, but SQLite kept {mode!r}")

    def _initialize(self) -> None:
        with self._transaction() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == LEDGER_SCHEMA_VERSION:
                return
            tables = connection.execute("SELECT count(*) FROM sqlite_master").fetchone()[0]
            if version != 0 or tables:
                raise LedgerError(f"Unsupported ledger schema version {version} with {tables} existing objects")
            for statement in _SCHEMA.split(";"):
                if statement.strip():
                    connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Run statements in one write transaction; roll back everything on any error."""
        if self.read_only:
            raise LedgerError("Ledger was opened read-only")
        connection = self._connection
        try:
            connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as exc:
            raise LedgerError(f"Cannot start ledger transaction: {exc}") from exc
        try:
            yield connection
        except BaseException as exc:
            # SQLite may already have rolled back by itself (e.g. disk full);
            # a second ROLLBACK would raise and hide the original cause.
            if connection.in_transaction:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error as rollback_exc:
                    raise LedgerError(
                        f"Ledger transaction failed ({exc}) and rollback also failed: {rollback_exc}"
                    ) from exc
            if isinstance(exc, sqlite3.Error):
                raise LedgerError(f"Ledger transaction failed and was rolled back: {exc}") from exc
            raise
        try:
            connection.execute("COMMIT")
        except sqlite3.Error as exc:
            if connection.in_transaction:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error as rollback_exc:
                    raise LedgerError(f"Ledger commit failed ({exc}) and rollback also failed: {rollback_exc}") from exc
            raise LedgerError(f"Ledger commit failed and was rolled back: {exc}") from exc

    # Runs -----------------------------------------------------------------

    def create_run(self, **fields: Any) -> None:
        """Register a running run; see ``run_values`` for the accepted fields."""
        values = run_values(**fields)
        run_id = values[0]
        with self._transaction() as connection:
            if connection.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone():
                raise LedgerError(f"Run already exists: {run_id}")
            connection.execute(
                "INSERT INTO runs (run_id, task, task_version, venue, dataset, range_start, range_end, status,"
                " started_at, code_version, config, parameters)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)",
                values,
            )

    def add_counts(self, run_id: str, *, requests: int = 0, rows_received: int = 0, rows_quarantined: int = 0) -> None:
        counts = (
            _count(requests, "requests"),
            _count(rows_received, "rows_received"),
            _count(rows_quarantined, "rows_quarantined"),
        )
        with self._transaction() as connection:
            self._require_running(connection, run_id)
            connection.execute(
                "UPDATE runs SET requests = requests + ?, rows_received = rows_received + ?,"
                " rows_quarantined = rows_quarantined + ? WHERE run_id = ?",
                (*counts, run_id),
            )

    def finish_run(self, run_id: str, *, status: str, finished_at: datetime, error: str | None = None) -> None:
        if status not in FINAL_RUN_STATUSES:
            raise LedgerError(f"Final run status must be one of {FINAL_RUN_STATUSES}")
        if status == "failed" and not error:
            raise LedgerError("A failed run requires an error description")
        finished = utc_text(finished_at, "finished_at")
        with self._transaction() as connection:
            self._require_running(connection, run_id)
            connection.execute(
                "UPDATE runs SET status = ?, finished_at = ?, error = ? WHERE run_id = ?",
                (status, finished, error, run_id),
            )

    def set_record_path(self, run_id: str, record_path: str) -> None:
        with self._transaction() as connection:
            run = self._fetch_run(connection, run_id)
            if run["status"] == "running":
                raise LedgerError(f"Run is still running: {run_id}")
            if run["record_path"] is not None:
                raise LedgerError(f"Run record path is already set: {run_id}")
            connection.execute("UPDATE runs SET record_path = ? WHERE run_id = ?", (record_path, run_id))

    @staticmethod
    def _fetch_run(connection: sqlite3.Connection, run_id: str) -> dict[str, Any]:
        cursor = connection.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = cursor.fetchone()
        if row is None:
            raise LedgerError(f"Unknown run: {run_id}")
        return _row(cursor, row)

    def require_running(self, run_id: str) -> None:
        """Raise LedgerError unless ``run_id`` is registered and still running."""
        status = self.get_run(run_id)["status"]
        if status != "running":
            raise LedgerError(f"Run {run_id} is already {status}")

    def _require_running(self, connection: sqlite3.Connection, run_id: str) -> None:
        status = self._fetch_run(connection, run_id)["status"]
        if status != "running":
            raise LedgerError(f"Run {run_id} is already {status}")

    # Manifest and checkpoint commit ----------------------------------------

    def commit(
        self, run_id: str, path: str | Path, facts: FileFacts, checkpoint: CheckpointAdvance | None = None
    ) -> dict[str, Any]:
        """Register a published file and optionally advance a checkpoint atomically.

        The caller must have durably published the file (``ScopedWriter``) and
        validated its contents; ``facts.validation`` states which checks ran.
        """
        prepared = commit_values(path, facts, checkpoint)
        relative = prepared["relative"]
        row_count, validation, pk_hash = prepared["row_count"], prepared["validation"], prepared["pk_hash"]
        min_time, max_time = prepared["times"]
        min_sequence, max_sequence = prepared["sequences"]
        if checkpoint is not None:
            checkpoint_key, expected = prepared["checkpoint"]["key"], prepared["checkpoint"]["expected"]
            cursor_text, watermark = prepared["checkpoint"]["cursor"], prepared["checkpoint"]["watermark"]
        target = self.root / relative
        try:
            if target.is_symlink() or not target.is_file() or target.resolve(strict=True) != target:
                raise LedgerError(f"Registered file must be a published regular file without symlinks: {relative}")
            # On case-insensitive filesystems "A.parquet" also opens "a.parquet".
            # Register only the exact directory entry names, so one file cannot
            # be registered twice under different spellings.
            parent = self.root
            for part in relative.parts:
                if part not in os.listdir(parent):
                    raise LedgerError(f"Registered path must match the file's exact name on disk: {relative}")
                parent = parent / part
            _require_same_device(self.root, target)
            checksum, size = _digest(target)
        except (OSError, WriteBoundaryError) as exc:
            raise LedgerError(f"Cannot read published file {relative}: {exc}") from exc
        entry = {
            "path": str(relative),
            "run_id": run_id,
            "dataset": facts.dataset,
            "schema_version": SCHEMA_VERSION,
            "row_count": row_count,
            "min_event_time": min_time,
            "max_event_time": max_time,
            "min_sequence": min_sequence,
            "max_sequence": max_sequence,
            "sha256": checksum,
            "size_bytes": size,
            "primary_key_hash": pk_hash,
            "validation": validation,
            "registered_at": None,
        }
        with self._transaction() as connection:
            # Timestamps are taken while holding the ledger lock so they follow commit order.
            now = entry["registered_at"] = utc_text(datetime.now(timezone.utc), "registered_at")
            self._require_running(connection, run_id)
            if connection.execute("SELECT 1 FROM manifest_files WHERE path = ?", (entry["path"],)).fetchone():
                raise LedgerError(f"File is already registered: {relative}")
            connection.execute(
                f"INSERT INTO manifest_files ({', '.join(entry)}) VALUES ({', '.join('?' for _ in entry)})",
                tuple(entry.values()),
            )
            connection.execute("UPDATE runs SET rows_written = rows_written + ? WHERE run_id = ?", (row_count, run_id))
            if checkpoint is not None:
                current = connection.execute(
                    "SELECT version, watermark FROM checkpoints WHERE checkpoint_key = ?", (checkpoint_key,)
                ).fetchone()
                current_version = 0 if current is None else current[0]
                if current is not None and current[1] is not None and (watermark is None or watermark < current[1]):
                    raise LedgerError(
                        f"Checkpoint {checkpoint_key} watermark cannot move backwards or be removed; "
                        "nothing was registered"
                    )
                if current_version != expected:
                    raise LedgerError(
                        f"Checkpoint {checkpoint_key} is at version {current_version}, expected {expected}; "
                        "nothing was registered"
                    )
                values = (checkpoint_key, expected + 1, cursor_text, watermark, entry["path"], run_id, now)
                connection.execute(
                    "INSERT OR REPLACE INTO checkpoints (checkpoint_key, version, cursor, watermark, last_file,"
                    " run_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
                connection.execute(
                    "INSERT INTO checkpoint_history (checkpoint_key, version, cursor, watermark, last_file,"
                    " run_id, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
        return entry

    # Queries ----------------------------------------------------------------

    def _query(self, sql: str, parameters: tuple = ()) -> list[dict[str, Any]]:
        try:
            cursor = self._connection.execute(sql, parameters)
            return [_row(cursor, row) for row in cursor.fetchall()]
        except sqlite3.Error as exc:
            raise LedgerError(f"Ledger query failed: {exc}") from exc

    def snapshot(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return (manifests, runs) read in one consistent transaction."""
        try:
            self._connection.execute("BEGIN")
            try:
                return self.manifests(), self.runs()
            finally:
                self._connection.execute("COMMIT")
        except sqlite3.Error as exc:
            raise LedgerError(f"Ledger query failed: {exc}") from exc

    def get_run(self, run_id: str) -> dict[str, Any]:
        rows = self._query("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        if not rows:
            raise LedgerError(f"Unknown run: {run_id}")
        return rows[0]

    def runs(self) -> list[dict[str, Any]]:
        return self._query("SELECT * FROM runs ORDER BY started_at, run_id")

    def manifests(self, run_id: str | None = None) -> list[dict[str, Any]]:
        if run_id is None:
            return self._query("SELECT * FROM manifest_files ORDER BY path")
        return self._query("SELECT * FROM manifest_files WHERE run_id = ? ORDER BY registered_at, path", (run_id,))

    def get_checkpoint(self, key: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM checkpoints WHERE checkpoint_key = ?", (key,))
        if not rows:
            return None
        row = rows[0]
        row["cursor"] = json.loads(row["cursor"])
        return row

    def checkpoint_history(self, run_id: str) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT * FROM checkpoint_history WHERE run_id = ? ORDER BY checkpoint_key, version", (run_id,)
        )
        for row in rows:
            row["cursor"] = json.loads(row["cursor"])
        return rows
