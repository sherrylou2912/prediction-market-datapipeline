"""Read-only audit: reports every ledger/file mismatch and never writes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.cli import main
from src.config import PipelineConfig
from src.data_io.audit import audit
from src.data_io.layout import DataLayout, WriterRole
from src.data_io.ledger import FileFacts, Ledger
from src.data_io.runs import Run, RunSpec

FACTS = FileFacts(dataset="silver.trades", row_count=1, validation="contract per row")


def _snapshot(root: Path) -> dict[str, tuple]:
    """Every entry with size, mtime and, for regular files, the content hash."""
    result = {}
    for current, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(current) / name
            info = path.lstat()
            content = (
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() and not path.is_symlink() else None
            )
            result[str(path.relative_to(root))] = (info.st_size, info.st_mtime_ns, content)
    return result


def _clean_run(tmp_path: Path) -> tuple[DataLayout, Run]:
    config = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"})
    layout = DataLayout.create(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))
    run.commit_file(WriterRole.NORMALIZER, "silver/trades/a", b"a", FACTS)
    run.finish("succeeded")
    return layout, run


def _kinds(report: dict) -> list[str]:
    return sorted(issue["kind"] for issue in report["issues"])


def test_clean_layout_passes_and_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _clean_run(tmp_path)
    report = audit(tmp_path)
    assert report["ok"] and report["registered_files"] == 1 and report["runs"] == 1
    assert main(["audit"], environ={"DATA_ROOT": str(tmp_path)}) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    (tmp_path / "silver/trades/a").write_bytes(b"changed")
    assert main(["audit"], environ={"DATA_ROOT": str(tmp_path)}) == 1
    assert main(["audit"], environ={"DATA_ROOT": str(tmp_path / "missing")}) == 2
    assert "pipeline audit failed" in capsys.readouterr().err


def test_every_mismatch_is_reported_without_writes(tmp_path: Path) -> None:
    layout, _ = _clean_run(tmp_path)
    config = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"})
    unfinished = Run.start(layout, config, RunSpec("t", "1"))
    unfinished.commit_file(WriterRole.NORMALIZER, "silver/trades/b", b"b", FACTS)
    layout.writer(WriterRole.NORMALIZER).write_new("silver/trades/orphan", b"o")
    (tmp_path / "silver/trades/a").write_bytes(b"tampered")
    (tmp_path / "silver/trades/b").unlink()
    (tmp_path / "bronze/.partial-x").write_bytes(b"p")
    (tmp_path / "gold/link").symlink_to(tmp_path / "silver/trades/orphan")
    (tmp_path / "recovery/conflicts").mkdir(parents=True)
    (tmp_path / "recovery/conflicts/x.bin").write_bytes(b"r")
    finished_without_record = Run.start(layout, config, RunSpec("t", "1"))
    with Ledger.open(layout) as ledger:
        ledger.finish_run(finished_without_record.run_id, status="succeeded", finished_at=_now())
    before = _snapshot(tmp_path)
    report = audit(tmp_path)
    assert _snapshot(tmp_path) == before
    assert not report["ok"]
    assert _kinds(report) == [
        "manifest_file_changed",
        "manifest_file_missing",
        "partial_file",
        "recovery_pending",
        "run_record_missing",
        "run_unfinished",
        "unexpected_symlink",
        "unregistered_file",
    ]
    assert report["unregistered_files"] == 1


def test_absent_ledger_reports_unregistered_files_and_creates_nothing(tmp_path: Path) -> None:
    DataLayout.create(tmp_path).writer(WriterRole.COLLECTOR).write_new("bronze/r1/x", b"x", receipt_id="r1")
    before = _snapshot(tmp_path)
    report = audit(tmp_path)
    assert report["ledger"] == "absent" and _kinds(report) == ["unregistered_file"]
    assert _snapshot(tmp_path) == before
    empty = tmp_path / "empty"
    empty.mkdir()
    assert audit(empty)["ok"] and list(empty.iterdir()) == []


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def test_cli_writes_nothing_and_reports_absent_ledger(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _clean_run(tmp_path)
    (tmp_path / "silver/trades/a").write_bytes(b"changed")
    before = _snapshot(tmp_path)
    assert main(["audit"], environ={"DATA_ROOT": str(tmp_path)}) == 1
    assert _snapshot(tmp_path) == before
    capsys.readouterr()
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["audit"], environ={"DATA_ROOT": str(empty)}) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ledger"] == "absent" and list(empty.iterdir()) == []


def test_rollback_journal_is_refused_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _clean_run(tmp_path)
    (tmp_path / "manifests/ledger.sqlite3-journal").write_bytes(b"\xd9\xd5\x05\xf9\x20\xa1\x63\xd7" + b"\0" * 504)
    before = _snapshot(tmp_path)
    assert main(["audit"], environ={"DATA_ROOT": str(tmp_path)}) == 2
    assert "rollback journal" in capsys.readouterr().err
    assert _snapshot(tmp_path) == before


def test_symlinks_are_reported_not_followed(tmp_path: Path) -> None:
    layout, _ = _clean_run(tmp_path)
    outside = tmp_path / "outside"
    (outside / "trades").mkdir(parents=True)
    (outside / "trades/a").write_bytes(b"a")
    (outside / "x").write_bytes(b"x")
    gold = tmp_path / "gold"
    gold.rmdir()
    gold.symlink_to(outside)
    silver_trades = tmp_path / "silver/trades"
    silver_trades.rename(tmp_path / "silver/real-trades")
    silver_trades.symlink_to(outside / "trades")
    report = audit(tmp_path)
    assert {"kind": "unexpected_symlink", "path": "gold"} in report["issues"]
    assert {"kind": "manifest_file_not_regular", "path": "silver/trades/a"} in report["issues"]
    assert not any(issue.get("path", "").startswith("gold/") for issue in report["issues"])


def test_recovery_partials_and_unreadable_files_are_reported(tmp_path: Path) -> None:
    _clean_run(tmp_path)
    recovery = tmp_path / "recovery/conflicts/silver"
    recovery.mkdir(parents=True)
    (recovery / "paired.bin").write_bytes(b"b")
    (recovery / "paired.json").write_text("{}")
    (recovery / "orphan.json").write_text("{}")
    (recovery / "notes.txt").write_text("?")
    (tmp_path / "manifests/.partial-x").write_bytes(b"p")
    registered = tmp_path / "silver/trades/a"
    registered.chmod(0)
    try:
        if os.access(registered, os.R_OK):
            pytest.skip("running with privileges that ignore file permissions")
        report = audit(tmp_path)
    finally:
        registered.chmod(0o644)
    assert _kinds(report) == [
        "manifest_file_unreadable",
        "partial_file",
        "recovery_metadata_without_payload",
        "recovery_pending",
        "recovery_unexpected_file",
    ]


def test_wal_mode_ledger_is_refused_without_writing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import sqlite3

    _clean_run(tmp_path)
    connection = sqlite3.connect(tmp_path / "manifests/ledger.sqlite3")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.close()
    for name in ("ledger.sqlite3-wal", "ledger.sqlite3-shm"):
        (tmp_path / "manifests" / name).unlink(missing_ok=True)
    before = _snapshot(tmp_path)
    assert main(["audit"], environ={"DATA_ROOT": str(tmp_path)}) == 2
    assert "WAL" in capsys.readouterr().err
    assert _snapshot(tmp_path) == before


def test_read_only_open_never_creates_a_missing_ledger(tmp_path: Path) -> None:
    import sqlite3

    from src.data_io.ledger import LedgerError

    (tmp_path / "manifests").mkdir()
    ledger = tmp_path / "manifests/ledger.sqlite3"
    with pytest.raises(sqlite3.OperationalError):
        sqlite3.connect(f"{ledger.as_uri()}?mode=rw", uri=True)
    assert not ledger.exists()
    manifests = tmp_path / "elsewhere"
    (tmp_path / "manifests").rename(manifests)
    (tmp_path / "manifests").symlink_to(manifests)
    with pytest.raises(LedgerError, match="directory must not be a symbolic link"):
        Ledger.open_read_only(tmp_path)


def test_unreadable_directory_is_reported_and_audit_continues(tmp_path: Path) -> None:
    _clean_run(tmp_path)
    blocked = tmp_path / "bronze/blocked"
    blocked.mkdir()
    (tmp_path / "gold/orphan").write_bytes(b"o")
    blocked.chmod(0)
    try:
        if os.access(blocked, os.R_OK):
            pytest.skip("running with privileges that ignore directory permissions")
        report = audit(tmp_path)
    finally:
        blocked.chmod(0o755)
    assert _kinds(report) == ["scan_error", "unregistered_file"]
    assert report["issues"][0]["path"] == "bronze/blocked"


def test_leftover_shm_after_returning_to_delete_mode_is_allowed(tmp_path: Path) -> None:
    import sqlite3

    layout, _ = _clean_run(tmp_path)
    connection = sqlite3.connect(tmp_path / "manifests/ledger.sqlite3")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.close()
    Ledger.open(layout).close()  # the write path switches back to DELETE mode
    shm = tmp_path / "manifests/ledger.sqlite3-shm"
    if not shm.exists():
        shm.write_bytes(b"\0" * 32768)  # SQLite on some platforms leaves it behind
    assert not (tmp_path / "manifests/ledger.sqlite3-wal").exists()
    before = _snapshot(tmp_path)
    report = audit(tmp_path)
    assert report["ok"] and report["ledger"] == "present"
    assert _snapshot(tmp_path) == before
