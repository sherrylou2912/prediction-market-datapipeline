"""SQLite ledger: manifest registration and checkpoint advancement are atomic."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.data_io.layout import DataLayout, WriteBoundaryError, WriterRole
from src.data_io.ledger import LEDGER_SCHEMA_VERSION, CheckpointAdvance, FileFacts, Ledger, LedgerError
from src.data_schema.contracts import SCHEMA_VERSION

T0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)


def _start(tmp_path: Path, run_id: str = "run-1") -> tuple[DataLayout, Ledger]:
    layout = DataLayout.create(tmp_path)
    ledger = Ledger.open(layout)
    ledger.create_run(
        run_id=run_id,
        task="test",
        task_version="1",
        started_at=T0,
        code_version={"commit": None},
        config={"sha256": "x"},
        parameters={},
    )
    return layout, ledger


def _facts(**overrides: object) -> FileFacts:
    values = {"dataset": "silver.trades", "row_count": 3, "validation": "contract 7.0.0 per row"}
    values.update(overrides)
    return FileFacts(**values)


def _publish(layout: DataLayout, path: str = "silver/trades/a.parquet", payload: bytes = b"abc") -> str:
    layout.writer(WriterRole.NORMALIZER).write_new(path, payload)
    return path


def _tables(ledger: Ledger) -> tuple[int, int, int]:
    return (
        len(ledger.manifests()),
        len(ledger._query("SELECT * FROM checkpoints")),
        ledger.get_run("run-1")["rows_written"],
    )


def test_commit_registers_manifest_and_advances_checkpoint(tmp_path: Path) -> None:
    layout, ledger = _start(tmp_path)
    path = _publish(layout)
    entry = ledger.commit(
        "run-1",
        path,
        _facts(event_time_range=(T0, T0 + timedelta(minutes=1)), sequence_range=(1, 3)),
        CheckpointAdvance("mock/trades", {"cursor": "p2"}, expected_version=0, watermark=T0),
    )
    assert entry["sha256"] == hashlib.sha256(b"abc").hexdigest() and entry["size_bytes"] == 3
    assert entry["schema_version"] == SCHEMA_VERSION
    checkpoint = ledger.get_checkpoint("mock/trades")
    assert checkpoint["version"] == 1 and checkpoint["cursor"] == {"cursor": "p2"} and checkpoint["last_file"] == path
    path2 = _publish(layout, "silver/trades/b.parquet")
    ledger.commit("run-1", path2, _facts(), CheckpointAdvance("mock/trades", 5, expected_version=1))
    assert ledger.get_checkpoint("mock/trades")["version"] == 2
    assert [row["version"] for row in ledger.checkpoint_history("run-1")] == [1, 2]
    assert ledger.get_run("run-1")["rows_written"] == 6


def test_stale_checkpoint_version_registers_nothing(tmp_path: Path) -> None:
    layout, ledger = _start(tmp_path)
    ledger.commit("run-1", _publish(layout), _facts(), CheckpointAdvance("k", 1, expected_version=0))
    before = _tables(ledger)
    with pytest.raises(LedgerError, match="expected 0"):
        ledger.commit(
            "run-1",
            _publish(layout, "silver/trades/b.parquet"),
            _facts(),
            CheckpointAdvance("k", 2, expected_version=0),
        )
    assert _tables(ledger) == before
    assert ledger.get_checkpoint("k")["cursor"] == 1


@pytest.mark.parametrize(
    ("path", "facts", "message"),
    [
        ("silver/trades/missing", _facts(), "Cannot read|published regular file"),
        ("gold/x/a.parquet", _facts(), "under silver/"),
        ("../a", _facts(), "root-relative"),
        ("silver/trades/a.parquet", _facts(dataset="silver.unknown"), "Unknown dataset"),
        ("silver/trades/a.parquet", _facts(row_count=-1), "row_count"),
        ("silver/trades/a.parquet", _facts(row_count=True), "row_count"),
        ("silver/trades/a.parquet", _facts(validation=" "), "validation"),
        ("silver/trades/a.parquet", _facts(event_time_range=(T0, T0 - timedelta(1))), "greater"),
        ("silver/trades/a.parquet", _facts(event_time_range=(T0.replace(tzinfo=None), T0)), "timezone.utc"),
        ("silver/trades/a.parquet", _facts(sequence_range=(1.0, 2)), "integers"),
        ("silver/trades/a.parquet", _facts(primary_key_hash="ABC"), "primary_key_hash"),
    ],
)
def test_invalid_commit_is_rejected_without_change(tmp_path: Path, path: str, facts: FileFacts, message: str) -> None:
    layout, ledger = _start(tmp_path)
    _publish(layout)
    with pytest.raises(LedgerError, match=message):
        ledger.commit("run-1", path, facts, CheckpointAdvance("k", 1, expected_version=0))
    assert _tables(ledger) == (0, 0, 0)


def test_invalid_checkpoint_cursor_and_symlinked_file_rejected(tmp_path: Path) -> None:
    layout, ledger = _start(tmp_path)
    path = _publish(layout)
    with pytest.raises(LedgerError, match="JSON"):
        ledger.commit("run-1", path, _facts(), CheckpointAdvance("k", float("nan"), expected_version=0))
    (tmp_path / "silver/trades/link").symlink_to(tmp_path / path)
    with pytest.raises(LedgerError, match="symlinks"):
        ledger.commit("run-1", "silver/trades/link", _facts())
    assert _tables(ledger) == (0, 0, 0)


def test_duplicate_registration_and_finished_run_rejected(tmp_path: Path) -> None:
    layout, ledger = _start(tmp_path)
    path = _publish(layout)
    ledger.commit("run-1", path, _facts())
    with pytest.raises(LedgerError, match="already registered"):
        ledger.commit("run-1", path, _facts())
    with pytest.raises(LedgerError, match="error description"):
        ledger.finish_run("run-1", status="failed", finished_at=T0)
    ledger.finish_run("run-1", status="partial", finished_at=T0)
    with pytest.raises(LedgerError, match="already partial"):
        ledger.commit("run-1", _publish(layout, "silver/trades/b.parquet"), _facts())
    with pytest.raises(LedgerError, match="already partial"):
        ledger.add_counts("run-1", requests=1)
    with pytest.raises(LedgerError, match="already partial"):
        ledger.finish_run("run-1", status="succeeded", finished_at=T0)
    with pytest.raises(LedgerError, match="Unknown run"):
        ledger.add_counts("run-2", requests=1)


def test_run_creation_validation(tmp_path: Path) -> None:
    _, ledger = _start(tmp_path)
    base = {
        "run_id": "run-2",
        "task": "t",
        "task_version": "1",
        "started_at": T0,
        "code_version": {},
        "config": {},
        "parameters": {},
    }
    with pytest.raises(LedgerError, match="already exists"):
        ledger.create_run(**{**base, "run_id": "run-1"})
    with pytest.raises(LedgerError, match="JSON"):
        ledger.create_run(**{**base, "parameters": {"x": object()}})
    with pytest.raises(LedgerError, match="earlier"):
        ledger.create_run(**{**base, "range_start": T0, "range_end": T0})
    with pytest.raises(LedgerError, match="timezone.utc"):
        ledger.create_run(**{**base, "started_at": T0.replace(tzinfo=None)})
    assert [run["run_id"] for run in ledger.runs()] == ["run-1"]


def test_ledger_persists_and_rejects_unknown_schema_or_symlink(tmp_path: Path) -> None:
    layout, ledger = _start(tmp_path)
    ledger.close()
    with Ledger.open(layout) as reopened:
        assert reopened.get_run("run-1")["status"] == "running"
    ledger_file = tmp_path / "manifests/ledger.sqlite3"
    connection = sqlite3.connect(ledger_file)
    connection.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION + 1}")
    connection.close()
    with pytest.raises(LedgerError, match="Unsupported ledger schema"):
        Ledger.open(layout)
    with pytest.raises(LedgerError, match="Unsupported ledger schema"):
        Ledger.open_read_only(tmp_path)
    other = tmp_path / "elsewhere.sqlite3"
    ledger_file.rename(other)
    ledger_file.symlink_to(other)
    with pytest.raises(LedgerError, match="symbolic link"):
        Ledger.open(layout)


def test_read_only_ledger_cannot_write_and_absent_ledger_is_none(tmp_path: Path) -> None:
    assert Ledger.open_read_only(tmp_path) is None
    assert not (tmp_path / "manifests").exists()
    _start(tmp_path)[1].close()
    with Ledger.open_read_only(tmp_path) as ledger:
        assert ledger.get_run("run-1")["task"] == "test"
        with pytest.raises(LedgerError, match="read-only"):
            ledger.add_counts("run-1", requests=1)


def test_registry_writer_cannot_create_ledger_files(tmp_path: Path) -> None:
    writer = DataLayout.create(tmp_path).writer(WriterRole.REGISTRY)
    for name in ("manifests/ledger.sqlite3", "manifests/ledger.sqlite3-journal"):
        with pytest.raises(WriteBoundaryError, match="reserved for the ledger"):
            writer.write_new(name, b"x")


def test_held_ledger_lock_fails_without_change(tmp_path: Path) -> None:
    layout, ledger = _start(tmp_path)
    path = _publish(layout)
    blocker = sqlite3.connect(tmp_path / "manifests/ledger.sqlite3", isolation_level=None)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(LedgerError, match="locked"):
            ledger.commit("run-1", path, _facts())
    finally:
        blocker.execute("ROLLBACK")
        blocker.close()
    assert _tables(ledger) == (0, 0, 0)
    ledger.commit("run-1", path, _facts())
