"""Run lifecycle: ledger rows, committed files, and published run records."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from src.config import PipelineConfig
from src.data_io import runs as runs_module
from src.data_io.layout import DataLayout, WriterRole
from src.data_io.ledger import CheckpointAdvance, FileFacts, Ledger, LedgerError
from src.data_io.runs import Run, RunSpec, code_version, new_run_id
from src.data_schema.contracts import SCHEMA_VERSION

FACTS = FileFacts(dataset="silver.trades", row_count=2, validation="contract per row")


def _setup(tmp_path: Path) -> tuple[DataLayout, PipelineConfig]:
    config = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "DATA_MIN_FREE_GIB": "0"})
    layout = DataLayout.create(config.validate_for_write(), lock_timeout_seconds=config.writer_lock_timeout_seconds)
    return layout, config


def test_successful_run_publishes_record_and_report(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    spec = RunSpec(task="mock_backfill", task_version="1", venue="mock", parameters={"page_size": 2})
    with Run.start(layout, config, spec) as run:
        run.add_counts(requests=1, rows_received=3, rows_quarantined=1)
        run.commit_file(WriterRole.NORMALIZER, "silver/trades/a.parquet", b"ab", FACTS, CheckpointAdvance("k", "p2", 0))
        record_path = run.finish("partial")
    record = json.loads(record_path.read_text())
    assert record_path == tmp_path / f"manifests/runs/{run.run_id}/record.json"
    assert record["run"]["status"] == "partial"
    assert record["run"]["config"] == config.effective_settings()
    assert record["run"]["parameters"] == {"page_size": 2}
    assert (record["run"]["requests"], record["run"]["rows_received"]) == (1, 3)
    assert (record["run"]["rows_written"], record["run"]["rows_quarantined"]) == (2, 1)
    assert record["rule_versions"]["data_contracts"] == SCHEMA_VERSION
    assert [m["path"] for m in record["manifests"]] == ["silver/trades/a.parquet"]
    assert record["checkpoints"][0]["cursor"] == "p2"
    report = record_path.with_name("report.md").read_text()
    assert "**partial**" in report and "silver/trades/a.parquet" in report
    with Ledger.open_read_only(tmp_path) as ledger:
        assert ledger.get_run(run.run_id)["record_path"] == str(record_path.relative_to(tmp_path))


def test_report_can_be_disabled(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec(task="t", task_version="1"), write_report=False)
    path = run.finish("succeeded")
    assert path.exists() and not path.with_name("report.md").exists()


def test_exception_marks_run_failed_and_keeps_error(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    with pytest.raises(RuntimeError, match="source down"), Run.start(layout, config, RunSpec("t", "1")) as run:
        raise RuntimeError("source down")
    record = json.loads((tmp_path / f"manifests/runs/{run.run_id}/record.json").read_text())
    assert record["run"]["status"] == "failed" and record["run"]["error"] == "RuntimeError: source down"


def test_exit_without_finish_is_recorded_as_failure(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    with (
        pytest.raises(LedgerError, match="without calling finish"),
        Run.start(layout, config, RunSpec("t", "1")) as run,
    ):
        pass
    with Ledger.open_read_only(tmp_path) as ledger:
        assert ledger.get_run(run.run_id)["status"] == "failed"


def test_no_commit_after_finish_and_no_double_finish(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))
    run.finish("succeeded")
    with pytest.raises(LedgerError, match="already finished"):
        run.commit_file(WriterRole.NORMALIZER, "silver/trades/a.parquet", b"x", FACTS)
    assert not (tmp_path / "silver/trades").exists()
    with pytest.raises(LedgerError, match="already finished"):
        run.finish("succeeded")
    with pytest.raises(LedgerError, match="already finished"):
        run.add_counts(requests=1)
    other = Run.start(layout, config, RunSpec("t", "1"))
    with pytest.raises(LedgerError, match="Final run status"):
        other.finish("running")
    other.finish("succeeded")


def test_invalid_finish_arguments_keep_run_open(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))
    with pytest.raises(LedgerError, match="error description"):
        run.finish("failed")
    with pytest.raises(LedgerError, match="error must be a string"):
        run.finish("failed", error=123)
    with pytest.raises(LedgerError, match="only allowed"):
        run.finish("succeeded", error="x")
    run.finish("failed", error="real reason")
    with Ledger.open_read_only(tmp_path) as ledger:
        assert ledger.get_run(run.run_id)["error"] == "real reason"


def test_unrecordable_exit_is_logged_and_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))

    def busy(*args: object, **kwargs: object) -> None:
        raise LedgerError("database is locked")

    monkeypatch.setattr(run._ledger, "finish_run", busy)
    with pytest.raises(LedgerError, match="could not be recorded"), run:
        pass
    assert any(getattr(r, "event", None) == "run.finish_failed" for r in caplog.records)
    with pytest.raises(RuntimeError, match="original"), Run.start(layout, config, RunSpec("t", "1")) as second:
        monkeypatch.setattr(second._ledger, "finish_run", busy)
        raise RuntimeError("original")


def test_invalid_start_has_no_side_effect(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    attempts = [
        ({"spec": RunSpec("t", "1", parameters={"bad": float("inf")})}, "JSON"),
        ({"spec": RunSpec("", "1")}, "task"),
        ({"spec": RunSpec("t", "1"), "write_report": "no"}, "write_report"),
        ({"spec": RunSpec("t", "1"), "run_id": ""}, "run_id"),
    ]
    attempts += [({"spec": RunSpec("t", "1"), "run_id": bad}, "run_id") for bad in ("Bad ID", "-lead", "caf\u00e9")]
    for kwargs, message in attempts:
        with pytest.raises(LedgerError, match=message):
            Run.start(layout, config, **kwargs)
    other_root = tmp_path / "other"
    other_root.mkdir()
    other = PipelineConfig.load(environ={"DATA_ROOT": str(other_root)})
    with pytest.raises(LedgerError, match="does not match the layout root"):
        Run.start(layout, other, RunSpec("t", "1"))
    waiting = PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS": "5"})
    with pytest.raises(LedgerError, match="lock timeout"):
        Run.start(layout, waiting, RunSpec("t", "1"))
    assert not (tmp_path / "manifests/ledger.sqlite3").exists()
    assert not (tmp_path / "manifests/runs").exists()


def test_invalid_commit_is_rejected_before_publishing(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))
    with pytest.raises(LedgerError, match="Unknown dataset"):
        run.commit_file(WriterRole.NORMALIZER, "silver/trades/a", b"x", FileFacts("silver.nope", 1, "checked"))
    with pytest.raises(LedgerError, match="under silver/"):
        run.commit_file(WriterRole.NORMALIZER, "gold/x", b"x", FACTS)
    assert not (tmp_path / "silver/trades").exists() and list((tmp_path / "gold").iterdir()) == []
    run.finish("failed", error="registration failed")


def test_registration_failure_after_publication_leaves_file_unregistered(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))
    with pytest.raises(LedgerError, match="expected 3"):
        run.commit_file(WriterRole.NORMALIZER, "silver/trades/a", b"x", FACTS, CheckpointAdvance("k", 1, 3))
    assert (tmp_path / "silver/trades/a").read_bytes() == b"x"
    run.finish("failed", error="stale checkpoint")


def test_record_publication_failure_is_reported(tmp_path: Path) -> None:
    layout, config = _setup(tmp_path)
    run = Run.start(layout, config, RunSpec("t", "1"))
    layout.writer(WriterRole.REGISTRY).write_new(f"manifests/runs/{run.run_id}/record.json", b"occupied")
    with pytest.raises(LedgerError, match="record was not published"):
        run.finish("succeeded")
    with Ledger.open_read_only(tmp_path) as ledger:
        row = ledger.get_run(run.run_id)
    assert row["status"] == "succeeded" and row["record_path"] is None


def test_run_id_and_code_version(monkeypatch: pytest.MonkeyPatch) -> None:
    assert re.fullmatch(r"\d{8}t\d{6}z-[0-9a-f]{12}", new_run_id())
    version = code_version()
    assert set(version) >= {"commit", "dirty"}

    def missing_git(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(runs_module.subprocess, "run", missing_git)
    assert code_version() == {"commit": None, "dirty": None, "unknown_reason": "git unavailable: FileNotFoundError"}
