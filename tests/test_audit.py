"""Read-only audit: reports every ledger/file mismatch and never writes."""

from __future__ import annotations

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


def _snapshot(root: Path) -> dict[str, tuple[int, int]]:
    result = {}
    for current, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(current) / name
            info = path.lstat()
            result[str(path.relative_to(root))] = (info.st_size, info.st_mtime_ns)
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
