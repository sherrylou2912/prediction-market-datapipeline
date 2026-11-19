"""Recovery and durability guarantees for cooperative local writers."""

from __future__ import annotations

import ast
import errno
import fcntl
import json
import logging
import os
import subprocess
import sys
import threading
import time
import warnings
from pathlib import Path

import pytest

from src.config import ConfigError, PipelineConfig
from src.config.loader import DEFAULT_CONFIG_DIR, PROJECT_ROOT
from src.data_io import layout as layout_module
from src.data_io.layout import DataLayout, ScopedWriter, WriteBoundaryError, WriterRole, open_write_layout


def test_same_receipt_retry_and_distinct_receipts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    writer = DataLayout.create(tmp_path).writer(WriterRole.COLLECTOR)
    with caplog.at_level(logging.INFO):
        first = writer.write_new("bronze/mock/receipt-1/record", b"same", receipt_id="receipt-1")
        assert writer.write_new("bronze/mock/receipt-1/record", b"same", receipt_id="receipt-1") == first
    second = writer.write_new("bronze/mock/receipt-2/record", b"same", receipt_id="receipt-2")
    assert first != second and first.read_bytes() == second.read_bytes()
    assert "Identical write retry" in caplog.text
    assert any(getattr(record, "event", None) == "writer.identical_retry" for record in caplog.records)
    assert not list((tmp_path / "recovery").rglob("*.bin"))
    with pytest.raises(WriteBoundaryError, match="receipt_id"):
        writer.write_new("bronze/mock/record", b"same")
    nested = "bronze/receipt-a/receipt-b/record"
    writer.write_new(nested, b"same", receipt_id="receipt-b")
    with pytest.raises(WriteBoundaryError, match="direct parent"):
        writer.write_new(nested, b"same", receipt_id="receipt-a")


def test_conflict_preserves_data_and_metadata(tmp_path: Path) -> None:
    writer = DataLayout.create(tmp_path).writer(WriterRole.COLLECTOR)
    target = writer.write_new("bronze/run-1/record", b"old", receipt_id="run-1")
    with pytest.raises(WriteBoundaryError, match="data preserved at"):
        writer.write_new("bronze/run-1/record", b"new", receipt_id="run-1")
    records = tmp_path / "recovery/conflicts/bronze/run-1/record"
    payload = next(records.glob("*.bin"))
    metadata = json.loads(payload.with_suffix(".json").read_text())
    assert payload.read_bytes() == b"new" and target.read_bytes() == b"old"
    assert metadata["original_target"] == "bronze/run-1/record"
    assert metadata["existing_size_bytes"] == metadata["new_size_bytes"] == 3
    assert metadata["existing_sha256"] != metadata["new_sha256"]
    assert metadata["recovery_path"] == str(payload.relative_to(tmp_path))
    assert metadata["completion_check"] == "payload_exists"


def test_held_lock_fails_immediately_and_preserves_partial(tmp_path: Path) -> None:
    DataLayout.create(tmp_path)
    partial = tmp_path / "silver/.partial-abandoned"
    partial.write_bytes(b"partial")
    with (tmp_path / ".writer.lock").open("r+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(WriteBoundaryError, match="lock is held"):
            DataLayout.create(tmp_path)
        assert partial.exists()
    DataLayout.create(tmp_path)
    assert not partial.exists()
    saved = next((tmp_path / "recovery/partials").rglob("*.bin"))
    info = json.loads(saved.with_suffix(".json").read_text())
    assert saved.read_bytes() == b"partial"
    assert info["original_path"] == "silver/.partial-abandoned"
    assert info["size_bytes"] == 7 and info["integrity"] == "unknown"


def test_layout_errors_and_symlink_replacement(tmp_path: Path) -> None:
    with pytest.raises(WriteBoundaryError):
        DataLayout.create(tmp_path / "missing")
    (tmp_path / "silver").write_bytes(b"not a directory")
    with pytest.raises(WriteBoundaryError):
        DataLayout.create(tmp_path)
    (tmp_path / "silver").unlink()
    layout = DataLayout.create(tmp_path)
    (tmp_path / "silver").rmdir()
    (tmp_path / "silver").symlink_to(tmp_path / "gold", target_is_directory=True)
    with pytest.raises(WriteBoundaryError, match="real directory"):
        layout.writer(WriterRole.NORMALIZER).write_new("silver/file", b"data")
    with pytest.raises(TypeError, match="payload"):
        layout.writer(WriterRole.NORMALIZER).write_new("silver/file", "wrong")  # type: ignore[arg-type]
    with pytest.raises(WriteBoundaryError, match="root-relative"):
        layout.writer(WriterRole.NORMALIZER).write_new("silver", b"data")


def test_published_parent_is_fsynced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    layout = DataLayout.create(tmp_path)
    from src.data_io import layout as layout_module

    seen: list[Path] = []
    original_sync = layout_module._sync_dir
    target = tmp_path / "silver/folder/file"

    def track_sync(path: Path) -> None:
        if target.exists():
            seen.append(path)
        original_sync(path)

    monkeypatch.setattr(layout_module, "_sync_dir", track_sync)
    result = layout.writer(WriterRole.NORMALIZER).write_new("silver/folder/file", b"ok")
    assert result == target and target.parent in seen


def test_directory_sync_failure_is_retried_before_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.data_io import layout as layout_module

    writer = DataLayout.create(tmp_path).writer(WriterRole.NORMALIZER)
    parent = tmp_path / "silver"
    target = parent / "newdir/file"
    original_sync = layout_module._sync_dir

    def fail_parent_sync(path: Path) -> None:
        if path == parent:
            raise OSError("parent sync failed")
        original_sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(layout_module, "_sync_dir", fail_parent_sync)
        for _ in range(2):
            with pytest.raises(WriteBoundaryError, match="parent sync failed"):
                writer.write_new("silver/newdir/file", b"data")
            assert not target.exists()
    assert target.parent.is_dir()

    calls = []

    def track_sync(path: Path) -> None:
        calls.append((path, target.exists()))
        original_sync(path)

    with monkeypatch.context() as patch:
        patch.setattr(layout_module, "_sync_dir", track_sync)
        assert writer.write_new("silver/newdir/file", b"data") == target
    assert (parent, False) in calls
    assert target.read_bytes() == b"data"


def test_missing_recovery_sidecar_is_rebuilt_with_unknown_integrity(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    DataLayout.create(tmp_path)
    orphan = tmp_path / "recovery/conflicts/silver/orphan/data.bin"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"preserved")
    with caplog.at_level(logging.WARNING):
        DataLayout.create(tmp_path)
    metadata = json.loads(orphan.with_suffix(".json").read_text())
    assert orphan.read_bytes() == b"preserved"
    assert metadata["integrity"] == "unknown"
    assert metadata["size_bytes"] == len(b"preserved")
    assert metadata["recovery_path"] == str(orphan.relative_to(tmp_path))
    assert any(getattr(record, "event", None) == "recovery.metadata_rebuilt" for record in caplog.records)


def test_failed_sidecar_creation_keeps_original_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    DataLayout.create(tmp_path)
    partial = tmp_path / "silver/.partial-evidence"
    partial.write_bytes(b"evidence")
    from src.data_io import layout as layout_module

    def fail_metadata(*args: object, **kwargs: object) -> None:
        raise OSError("metadata unavailable")

    with monkeypatch.context() as patch:
        patch.setattr(layout_module, "_write_metadata", fail_metadata)
        with pytest.raises(WriteBoundaryError, match="metadata unavailable"):
            DataLayout.create(tmp_path)
    assert partial.read_bytes() == b"evidence"
    DataLayout.create(tmp_path)
    saved = next((tmp_path / "recovery/partials").rglob("*.bin"))
    assert saved.read_bytes() == b"evidence"
    assert saved.with_suffix(".json").is_file()


def test_interrupted_metadata_repair_retries_without_partial_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.data_io import layout as layout_module

    DataLayout.create(tmp_path)
    orphan = tmp_path / "recovery/partials/silver/lost/payload.bin"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"preserved")

    def fail_sync(fd: int) -> None:
        raise OSError("interrupted metadata sync")

    with monkeypatch.context() as patch:
        patch.setattr(layout_module, "_sync_file", fail_sync)
        with pytest.raises(WriteBoundaryError, match="interrupted metadata sync"):
            DataLayout.create(tmp_path)
    assert not orphan.with_suffix(".json").exists()
    DataLayout.create(tmp_path)
    assert json.loads(orphan.with_suffix(".json").read_text())["integrity"] == "unknown"
    assert orphan.read_bytes() == b"preserved"


def test_full_fsync_io_error_preserves_partial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import errno

    from src.data_io import layout as layout_module

    layout = DataLayout.create(tmp_path)
    monkeypatch.setattr(layout_module.fcntl, "F_FULLFSYNC", 123456, raising=False)

    def fail_full_sync(fd: int, operation: int) -> None:
        raise OSError(errno.EIO, "device I/O failure")

    with monkeypatch.context() as patch:
        patch.setattr(layout_module.fcntl, "fcntl", fail_full_sync)
        with pytest.raises(WriteBoundaryError, match="device I/O failure"):
            layout.writer(WriterRole.NORMALIZER).write_new("silver/file", b"evidence")
    assert not (tmp_path / "silver/file").exists()
    partial = next((tmp_path / "silver").glob(".partial-*"))
    assert partial.read_bytes() == b"evidence"
    DataLayout.create(tmp_path)
    assert next((tmp_path / "recovery/partials").rglob("*.bin")).read_bytes() == b"evidence"


def test_recovery_syncs_partial_before_moving_and_preserves_it_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.data_io import layout as layout_module

    root = DataLayout.create(tmp_path).root
    partial = root / "silver/.partial-unsynced"
    partial.write_bytes(b"evidence")
    inode = partial.stat().st_ino
    original_sync = layout_module._sync_file
    synced: list[int] = []

    def fail_partial(fd: int) -> None:
        if os.fstat(fd).st_ino == inode:
            raise OSError("partial sync failed")
        original_sync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(layout_module, "_sync_file", fail_partial)
        with pytest.raises(WriteBoundaryError, match="partial sync failed"):
            DataLayout.create(root)
    assert partial.read_bytes() == b"evidence"
    assert not list((root / "recovery/partials").rglob("*.bin"))

    def track_sync(fd: int) -> None:
        synced.append(os.fstat(fd).st_ino)
        original_sync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(layout_module, "_sync_file", track_sync)
        DataLayout.create(root)
    assert inode in synced
    assert next((root / "recovery/partials").rglob("*.bin")).read_bytes() == b"evidence"


def test_interrupted_payload_move_leaves_identifiable_incomplete_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from src.data_io import layout as layout_module

    root = DataLayout.create(tmp_path).root
    partial = root / "silver/.partial-evidence"
    partial.write_bytes(b"evidence")
    original_rename = os.rename

    def fail_payload_rename(source: object, target: object) -> None:
        if Path(source) == partial:  # type: ignore[arg-type]
            raise OSError("interrupted payload move")
        original_rename(source, target)  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(layout_module.os, "rename", fail_payload_rename)
        with pytest.raises(WriteBoundaryError, match="interrupted payload move"):
            DataLayout.create(root)
    assert partial.read_bytes() == b"evidence"
    orphan = next((root / "recovery/partials").rglob("*.json"))
    metadata = json.loads(orphan.read_text())
    assert metadata["completion_check"] == "payload_exists"
    assert not (root / metadata["recovery_path"]).exists()

    with caplog.at_level(logging.WARNING):
        DataLayout.create(root)
    assert orphan.exists()
    assert any(getattr(record, "event", None) == "recovery.missing_payload" for record in caplog.records)
    assert any(getattr(record, "event", None) == "recovery.partial_saved" for record in caplog.records)
    assert len(list((root / "recovery/partials").rglob("*.json"))) == 2
    assert next((root / "recovery/partials").rglob("*.bin")).read_bytes() == b"evidence"


def test_nul_target_is_rejected_before_any_temporary_write(tmp_path: Path) -> None:
    layout = DataLayout.create(tmp_path)
    writer = layout.writer(WriterRole.NORMALIZER)
    with pytest.raises(WriteBoundaryError, match="NUL"):
        writer.write_new("silver/invalid\x00name", b"evidence")
    assert not list((tmp_path / "silver").iterdir())
    assert not list((tmp_path / "recovery").rglob("*.bin"))


def test_partial_symlink_is_skipped_with_distinct_event(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    root = DataLayout.create(tmp_path).root
    evidence = root / "silver/evidence"
    evidence.write_bytes(b"keep")
    partial = root / "silver/.partial-link"
    partial.symlink_to(evidence)
    with caplog.at_level(logging.WARNING):
        DataLayout.create(root)
    assert partial.is_symlink() and evidence.read_bytes() == b"keep"
    assert any(getattr(record, "event", None) == "recovery.partial_skipped" for record in caplog.records)


@pytest.mark.parametrize("receipt", ["A", "Run-1", "é", "e\u0301", "_bad", "a.b", "a b", ""])
def test_receipt_id_rejects_case_unicode_and_noncanonical_spellings(tmp_path: Path, receipt: str) -> None:
    root = DataLayout.create(tmp_path).root
    writer = DataLayout(root).writer(WriterRole.COLLECTOR)
    with pytest.raises(WriteBoundaryError, match="receipt_id"):
        writer.write_new(Path("bronze") / receipt / "record", b"data", receipt_id=receipt)
    assert not list((root / "bronze").rglob(".partial-*"))
    assert not list((root / "bronze").rglob("record"))


def test_receipt_id_lowercase_ascii_supports_exact_retry(tmp_path: Path) -> None:
    writer = DataLayout.create(tmp_path).writer(WriterRole.COLLECTOR)
    target = writer.write_new("bronze/source/a0_b-c/file", b"data", receipt_id="a0_b-c")
    assert writer.write_new("bronze/source/a0_b-c/file", b"data", receipt_id="a0_b-c") == target
    assert target.read_bytes() == b"data"


def test_nested_device_is_rejected_before_partial_and_during_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = DataLayout.create(tmp_path).root
    mounted = root / "silver/mounted"
    mounted.mkdir()
    partial = mounted / ".partial-preserve"
    partial.write_bytes(b"preserve")
    original_stat = Path.stat

    class OtherDevice:
        def __init__(self, original: os.stat_result) -> None:
            self.original = original
            self.st_dev = original.st_dev + 1

        def __getattr__(self, name: str) -> object:
            return getattr(self.original, name)

    def altered_stat(path: Path, *args: object, **kwargs: object) -> object:
        result = original_stat(path, *args, **kwargs)  # type: ignore[arg-type]
        return OtherDevice(result) if path == mounted else result

    with monkeypatch.context() as patch:
        patch.setattr(Path, "stat", altered_stat)
        writer = DataLayout(root).writer(WriterRole.NORMALIZER)
        with pytest.raises(WriteBoundaryError, match="Cross-device"):
            writer.write_new("silver/mounted/new-file", b"incoming")
        assert not (mounted / "new-file").exists()
        assert [p.name for p in mounted.iterdir()] == [".partial-preserve"]
        with pytest.raises(WriteBoundaryError, match="Cross-device"):
            DataLayout.create(root)
    assert partial.read_bytes() == b"preserve"
    assert not list((root / "recovery/partials").rglob("*.bin"))


@pytest.mark.parametrize(
    "corruption", ["invalid_json", "not_object", "duplicate", "path", "origin", "sha256", "size", "mixed_checksums"]
)
def test_corrupt_recovery_metadata_is_reported_without_modifying_evidence(tmp_path: Path, corruption: str) -> None:
    root = DataLayout.create(tmp_path).root
    writer = DataLayout(root).writer(WriterRole.NORMALIZER)
    writer.write_new("silver/record", b"old")
    with pytest.raises(WriteBoundaryError, match="data preserved"):
        writer.write_new("silver/record", b"new")
    saved = next((root / "recovery/conflicts").rglob("*.bin"))
    sidecar = saved.with_suffix(".json")
    metadata = json.loads(sidecar.read_text())
    if corruption == "invalid_json":
        altered = "{"
    elif corruption == "not_object":
        altered = "[]"
    elif corruption == "duplicate":
        altered = '{"reason":"one","reason":"two"}'
    else:
        if corruption == "path":
            metadata["recovery_path"] = "recovery/wrong.bin"
        elif corruption == "origin":
            metadata["original_target"] = "silver/other"
        elif corruption == "sha256":
            metadata["new_sha256"] = "0" * 64
        elif corruption == "mixed_checksums":
            metadata["sha256"] = metadata["new_sha256"]
            metadata["size_bytes"] = metadata["new_size_bytes"]
            metadata["new_sha256"] = "0" * 64
        else:
            metadata["new_size_bytes"] += 1
        altered = json.dumps(metadata)
    sidecar.write_text(altered, encoding="utf-8")
    with pytest.raises(WriteBoundaryError, match="Invalid recovery metadata"):
        DataLayout.create(root)
    assert sidecar.read_text() == altered
    assert saved.read_bytes() == b"new"
    assert (root / "silver/record").read_bytes() == b"old"


@pytest.mark.parametrize("kind", ["conflicts", "partials"])
@pytest.mark.parametrize("missing", ["recovery_path", "completion_check"])
def test_recovery_metadata_requires_path_and_completion_check(tmp_path: Path, kind: str, missing: str) -> None:
    root = DataLayout.create(tmp_path).root
    if kind == "conflicts":
        writer = DataLayout(root).writer(WriterRole.NORMALIZER)
        writer.write_new("silver/record", b"old")
        with pytest.raises(WriteBoundaryError, match="data preserved"):
            writer.write_new("silver/record", b"new")
    else:
        (root / "silver/.partial-legacy").write_bytes(b"new")
        DataLayout.create(root)
    saved = next((root / "recovery" / kind).rglob("*.bin"))
    sidecar = saved.with_suffix(".json")
    metadata = json.loads(sidecar.read_text())
    del metadata[missing]
    altered = json.dumps(metadata)
    sidecar.write_text(altered)
    with pytest.raises(WriteBoundaryError, match="Invalid recovery metadata"):
        DataLayout.create(root)
    assert saved.read_bytes() == b"new"
    assert sidecar.read_text() == altered


def test_corrupt_recovery_payload_is_reported_without_overwriting_metadata(tmp_path: Path) -> None:
    root = DataLayout.create(tmp_path).root
    (root / "silver/.partial-corrupt").write_bytes(b"before")
    DataLayout.create(root)
    payload = next((root / "recovery/partials").rglob("*.bin"))
    sidecar = payload.with_suffix(".json")
    original_metadata = sidecar.read_bytes()
    payload.write_bytes(b"after")
    with pytest.raises(WriteBoundaryError, match="payload checksum or size does not match"):
        DataLayout.create(root)
    assert payload.read_bytes() == b"after"
    assert sidecar.read_bytes() == original_metadata


@pytest.mark.parametrize(
    "corruption", ["missing_integrity", "invalid_integrity", "missing_modified", "invalid_modified"]
)
def test_corrupt_partial_metadata_is_rejected_without_modifying_evidence(tmp_path: Path, corruption: str) -> None:
    root = DataLayout.create(tmp_path).root
    (root / "silver/.partial-corrupt").write_bytes(b"evidence")
    DataLayout.create(root)
    payload = next((root / "recovery/partials").rglob("*.bin"))
    sidecar = payload.with_suffix(".json")
    metadata = json.loads(sidecar.read_text())
    if corruption == "missing_integrity":
        del metadata["integrity"]
    elif corruption == "invalid_integrity":
        metadata["integrity"] = "valid"
    elif corruption == "missing_modified":
        del metadata["modified_at"]
    else:
        metadata["modified_at"] = "not a timestamp"
    altered = json.dumps(metadata)
    sidecar.write_text(altered, encoding="utf-8")
    with pytest.raises(WriteBoundaryError, match="Invalid recovery metadata"):
        DataLayout.create(root)
    assert sidecar.read_text() == altered
    assert payload.read_bytes() == b"evidence"


def _hold_lock(root: Path):
    handle = (root / ".writer.lock").open("r+")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


@pytest.mark.parametrize("value", [-1, 3601, True, 1.5, "1"])
def test_invalid_lock_timeout_rejected_for_layout_and_writer(tmp_path: Path, value: object) -> None:
    layout = DataLayout.create(tmp_path)
    with pytest.raises(WriteBoundaryError, match="lock_timeout_seconds"):
        DataLayout.create(tmp_path, lock_timeout_seconds=value)
    writer = ScopedWriter(root=layout.root, role=WriterRole.NORMALIZER, lock_timeout_seconds=value)
    with pytest.raises(WriteBoundaryError, match="lock_timeout_seconds"):
        writer.write_new("silver/x", b"x")
    assert not (tmp_path / "silver/x").exists()


def test_create_waits_for_lock_then_fails_without_change(tmp_path: Path) -> None:
    DataLayout.create(tmp_path)
    partial = tmp_path / "silver/.partial-abandoned"
    partial.write_bytes(b"partial")
    handle = _hold_lock(tmp_path)
    try:
        start = time.monotonic()
        with pytest.raises(WriteBoundaryError, match="waited 1s"):
            DataLayout.create(tmp_path, lock_timeout_seconds=1)
        assert 0.9 <= time.monotonic() - start < 3
        assert partial.read_bytes() == b"partial"
        assert not list((tmp_path / "recovery").rglob("*.bin"))
        timer = threading.Timer(0.2, lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        timer.start()
        layout = DataLayout.create(tmp_path, lock_timeout_seconds=2)
        timer.join()
    finally:
        handle.close()
    assert not partial.exists()
    assert layout.writer(WriterRole.NORMALIZER).lock_timeout_seconds == 2


def test_write_waits_for_lock_then_fails_or_succeeds(tmp_path: Path) -> None:
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=1).writer(WriterRole.NORMALIZER)
    handle = _hold_lock(tmp_path)
    try:
        start = time.monotonic()
        with pytest.raises(WriteBoundaryError, match="waited 1s"):
            writer.write_new("silver/trades/a", b"data")
        assert 0.9 <= time.monotonic() - start < 3
        assert list((tmp_path / "silver").iterdir()) == []
        timer = threading.Timer(0.2, lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        timer.start()
        assert writer.write_new("silver/trades/a", b"data").read_bytes() == b"data"
        timer.join()
    finally:
        handle.close()


@pytest.mark.parametrize("value", ["-1", "3601", "abc", "1.5", "\uff11", "9" * 5000])
def test_invalid_lock_timeout_environment_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(ConfigError, match="PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS"):
        PipelineConfig.load(environ={"DATA_ROOT": str(tmp_path), "PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS": value})


@pytest.mark.parametrize(
    ("value", "expected"), [("0" * 5000 + "5", 5), ("0" * 5000, 0)], ids=["zero_padded_5", "all_zeros"]
)
def test_long_zero_padded_lock_timeout_is_parsed_without_long_int_conversion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str, expected: int
) -> None:
    import src.config.models.pipeline as pipeline_module

    def limited_int(text: object, *args: object) -> int:
        # Python 3.11+ rejects int() of strings longer than 4300 digits.
        if isinstance(text, str) and len(text) > 4300:
            raise ValueError("Exceeds the limit for integer string conversion")
        return int(text, *args)

    monkeypatch.setattr(pipeline_module, "int", limited_int, raising=False)
    environ = {"DATA_ROOT": str(tmp_path), "PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS": value}
    assert PipelineConfig.load(environ=environ).writer_lock_timeout_seconds == expected


def test_lock_timeout_sources(tmp_path: Path) -> None:
    environ = {"DATA_ROOT": str(tmp_path)}
    loaded = PipelineConfig.load(environ=environ)
    assert loaded.writer_lock_timeout_seconds == 0
    assert loaded.effective_settings()["settings"]["writer_lock_timeout_seconds"]["source"] == "default:runtime.json"
    override = PipelineConfig.load(environ={**environ, "PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS": " 0030 "})
    assert override.writer_lock_timeout_seconds == 30
    assert (
        override.effective_settings()["settings"]["writer_lock_timeout_seconds"]["source"]
        == "environment:PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS"
    )
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "storage.json").write_text('{"min_free_gib": 0}', encoding="utf-8")
    (config_dir / "runtime.json").write_text('{"log_level": "INFO"}', encoding="utf-8")
    missing = PipelineConfig.load(config_dir=config_dir, environ=environ)
    assert missing.writer_lock_timeout_seconds == 0
    assert missing.effective_settings()["settings"]["writer_lock_timeout_seconds"]["source"] == "default:model"
    (config_dir / "runtime.json").write_text(
        '{"log_level": "INFO", "writer_lock_timeout_seconds": 7}', encoding="utf-8"
    )
    assert PipelineConfig.load(config_dir=config_dir, environ=environ).writer_lock_timeout_seconds == 7
    for invalid in ("-1", "3601", "true", "1.5", '"1"'):
        (config_dir / "runtime.json").write_text(
            f'{{"log_level": "INFO", "writer_lock_timeout_seconds": {invalid}}}', encoding="utf-8"
        )
        with pytest.raises(ConfigError, match="PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS"):
            PipelineConfig.load(config_dir=config_dir, environ=environ)


def test_json_default_matches_model_default() -> None:
    runtime = json.loads((DEFAULT_CONFIG_DIR / "runtime.json").read_text(encoding="utf-8"))
    assert runtime["writer_lock_timeout_seconds"] == PipelineConfig.model_fields["writer_lock_timeout_seconds"].default


def _waiter_threads() -> list[threading.Thread]:
    return [thread for thread in threading.enumerate() if thread.name == "writer-lock-waiter"]


def _join_waiters(timeout: float = 5) -> None:
    for thread in _waiter_threads():
        thread.join(timeout)
    assert not _waiter_threads()


def _lock_is_free(root: Path) -> bool:
    with (root / ".writer.lock").open("r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        return True


def test_zero_timeout_fails_immediately_without_waiter_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = DataLayout.create(tmp_path).writer(WriterRole.NORMALIZER)

    def no_waiter(*args: object) -> None:
        raise AssertionError("timeout 0 must not start a waiter")

    monkeypatch.setattr(layout_module, "_wait_for_lock", no_waiter)
    handle = _hold_lock(tmp_path)
    try:
        start = time.monotonic()
        with pytest.raises(WriteBoundaryError, match="lock is held.*waited 0s"):
            writer.write_new("silver/trades/a", b"data")
        assert time.monotonic() - start < 0.5
    finally:
        handle.close()
    assert list((tmp_path / "silver").iterdir()) == []


def test_waiter_that_gave_up_releases_lock_as_soon_as_it_gets_it(tmp_path: Path) -> None:
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=1).writer(WriterRole.NORMALIZER)
    handle = _hold_lock(tmp_path)
    try:
        with pytest.raises(WriteBoundaryError, match="waited 1s"):
            writer.write_new("silver/trades/a", b"data")
        # The abandoned waiter is still blocked in flock while the lock is held.
        assert len(_waiter_threads()) == 1
        assert list((tmp_path / "silver").iterdir()) == []
    finally:
        handle.close()
    # Releasing the lock wakes the abandoned waiter, which must release it at once.
    _join_waiters()
    assert _lock_is_free(tmp_path)
    assert writer.write_new("silver/trades/a", b"data").read_bytes() == b"data"
    assert not _waiter_threads()


def test_successful_wait_leaves_no_thread_or_lock_behind(tmp_path: Path) -> None:
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=2).writer(WriterRole.NORMALIZER)
    handle = _hold_lock(tmp_path)
    try:
        timer = threading.Timer(0.2, lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        timer.start()
        start = time.monotonic()
        writer.write_new("silver/trades/a", b"data")
        assert time.monotonic() - start < 1.5
        timer.join()
    finally:
        handle.close()
    _join_waiters()
    assert _lock_is_free(tmp_path)


def _lock_key(root: Path) -> tuple[int, int]:
    info = (root / ".writer.lock").stat()
    return info.st_dev, info.st_ino


def _assert_no_waiter_state() -> None:
    _join_waiters()
    assert not layout_module._WAITER_HANDLES
    assert not layout_module._IDLE_WAITERS


class _InterruptingEvent:
    """Stands in for the waiter's event: ``wait`` raises as if Ctrl-C arrived."""

    def __init__(self, real: threading.Event) -> None:
        self._real = real

    def wait(self, timeout: float | None = None) -> bool:
        raise KeyboardInterrupt

    def set(self) -> None:
        self._real.set()

    def is_set(self) -> bool:
        return self._real.is_set()


class _InterruptedStart:
    """Stands in for the waiter's thread: ``start`` starts it, then raises as if Ctrl-C arrived."""

    def __init__(self, real: threading.Thread) -> None:
        self._real = real

    def start(self) -> None:
        self._real.start()
        raise KeyboardInterrupt

    def is_alive(self) -> bool:
        return self._real.is_alive()


_REAL_LOCK_WAITER = layout_module._LockWaiter


def _patch_waiter(monkeypatch: pytest.MonkeyPatch, change: object) -> None:
    """Make each new waiter pass through ``change`` right after it is created."""

    class PatchedWaiter(_REAL_LOCK_WAITER):
        def __init__(self, path: Path, key: tuple[int, int]) -> None:
            super().__init__(path, key)
            change(self)

    monkeypatch.setattr(layout_module, "_LockWaiter", PatchedWaiter)


def test_interrupted_wait_does_not_leave_the_lock_held(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)

    def interrupt_wait(waiter: layout_module._LockWaiter) -> None:
        waiter.finished = _InterruptingEvent(waiter.finished)

    _patch_waiter(monkeypatch, interrupt_wait)
    # Interrupted before the waiter got the lock: it releases the lock once it gets it.
    handle = _hold_lock(tmp_path)
    try:
        with pytest.raises(KeyboardInterrupt):
            layout_module._wait_for_lock(path, key, 5, [])
        assert len(_waiter_threads()) == 1
    finally:
        handle.close()
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)
    # Interrupted after the waiter got the lock: the handle is already in the
    # caller's list, and the caller (``_lock``) closes it.
    obtained = threading.Event()
    delivered: list[list[int]] = []

    def interrupt_after_lock(waiter: layout_module._LockWaiter) -> None:
        real = waiter.finished

        class AfterLock(_InterruptingEvent):
            def wait(self, timeout: float | None = None) -> bool:
                assert real.wait(5)
                delivered.append(list(waiter.claim or []))
                obtained.set()
                raise KeyboardInterrupt

        waiter.finished = AfterLock(real)

    _patch_waiter(monkeypatch, interrupt_after_lock)
    handle = _hold_lock(tmp_path)
    try:
        timer = threading.Timer(0.2, lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        timer.start()
        with pytest.raises(KeyboardInterrupt), layout_module._lock(tmp_path, 5):
            pass
        timer.join()
    finally:
        handle.close()
    assert obtained.is_set()
    assert len(delivered[0]) == 1
    with pytest.raises(OSError):
        os.fstat(delivered[0][0])
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)


def test_interrupt_right_after_waiter_starts_does_not_leave_the_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ctrl-C between starting the waiter thread and waiting on it (B1-R5-4)."""
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=1).writer(WriterRole.NORMALIZER)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)

    def interrupt_start(waiter: layout_module._LockWaiter) -> None:
        waiter.thread = _InterruptedStart(waiter.thread)

    _patch_waiter(monkeypatch, interrupt_start)
    handle = _hold_lock(tmp_path)
    try:
        with pytest.raises(KeyboardInterrupt):
            layout_module._wait_for_lock(path, key, 5, [])
        # The started waiter was handed back as unclaimed. ``start`` raised, so the wait
        # cannot tell whether it runs; it is not reused and cleans up after itself.
        assert len(_waiter_threads()) == 1
        assert not layout_module._IDLE_WAITERS
    finally:
        handle.close()
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)
    monkeypatch.undo()
    assert writer.write_new("silver/trades/a", b"data").read_bytes() == b"data"


def test_waiter_thread_that_cannot_start_opens_no_handle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=1).writer(WriterRole.NORMALIZER)
    opened: list[int] = []
    real_open = layout_module._open_lock_file

    def recording_open(path: Path) -> int:
        opened.append(real_open(path))
        return opened[-1]

    class NoThread:
        def start(self) -> None:
            raise RuntimeError("can't start new thread")

    def no_thread(waiter: layout_module._LockWaiter) -> None:
        waiter.thread = NoThread()

    _patch_waiter(monkeypatch, no_thread)
    monkeypatch.setattr(layout_module, "_open_lock_file", recording_open)
    handle = _hold_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="can't start new thread"):
            writer.write_new("silver/trades/a", b"data")
        # Only the caller's own first try opened a handle (and closed it); the waiter
        # opens its handle in its thread, which never ran.
        assert len(opened) == 1
        with pytest.raises(OSError):
            os.fstat(opened[0])
        assert not layout_module._WAITER_HANDLES
        assert not layout_module._IDLE_WAITERS
    finally:
        handle.close()
    assert list((tmp_path / "silver").iterdir()) == []


class _StartRaisesAfterRunning:
    """Stands in for the waiter's thread: ``start`` starts it, lets it block in ``flock``,
    then raises ``RuntimeError``, as CPython's ``Thread.start`` can when a signal handler
    raises while it waits for the new thread to report in."""

    def __init__(self, real: threading.Thread) -> None:
        self._real = real

    def start(self) -> None:
        self._real.start()
        deadline = time.monotonic() + 5
        while not layout_module._WAITER_HANDLES and time.monotonic() < deadline:
            time.sleep(0.005)
        time.sleep(0.05)  # the waiter is now blocked in flock on its handle
        raise RuntimeError("release unlocked lock")

    def is_alive(self) -> bool:
        return self._real.is_alive()


def test_start_that_raises_after_the_waiter_runs_neither_hangs_nor_closes_its_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1-R7-1: the caller must not close a handle that a running waiter owns. On macOS
    that close blocks behind the waiter's flock, ignoring the timeout; the waiter then
    closes the same number again, possibly another file's by then."""
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    thread_errors: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: thread_errors.append(args.exc_value))

    def start_raises(waiter: layout_module._LockWaiter) -> None:
        waiter.thread = _StartRaisesAfterRunning(waiter.thread)

    _patch_waiter(monkeypatch, start_raises)
    outcome: list[object] = []
    held: list[int] = []

    def call() -> None:
        started = time.monotonic()
        try:
            layout_module._wait_for_lock(path, key, 1, held)
        except RuntimeError as exc:
            outcome.append(exc)
        outcome.append(time.monotonic() - started)

    handle = _hold_lock(tmp_path)
    caller = threading.Thread(target=call, daemon=True)  # daemon: a hang must not hang pytest
    victim = None
    try:
        caller.start()
        caller.join(3)
        assert not caller.is_alive(), "the wait blocked closing the running waiter's handle"
        assert str(outcome[0]) == "release unlocked lock" and outcome[1] < 1
        assert held == []
        # The running waiter keeps its handle, is not reused, and gives the lock up itself.
        assert len(_waiter_threads()) == 1
        assert len(layout_module._WAITER_HANDLES) == 1
        assert not layout_module._IDLE_WAITERS
        victim = os.open(tmp_path / "victim", os.O_CREAT | os.O_RDWR, 0o600)
    finally:
        handle.close()
        caller.join(5)
    try:
        _assert_no_waiter_state()
        assert thread_errors == []  # e.g. no EBADF from closing the same number twice
        os.fstat(victim)  # a file opened meanwhile is still open
    finally:
        if victim is not None:
            os.close(victim)
    assert _lock_is_free(tmp_path)


class _MutexCheckingEvent(threading.Event):
    """Records, on each ``set``, whether another thread could take the waiter mutex then."""

    def __init__(self, record: list[bool]) -> None:
        super().__init__()
        self._record = record

    def set(self) -> None:
        free: list[bool] = []

        def probe() -> None:
            mutex = layout_module._WAITERS_MUTEX
            free.append(mutex.acquire(timeout=1))
            if free[0]:
                mutex.release()

        prober = threading.Thread(target=probe)
        prober.start()
        prober.join()
        self._record.append(free[0])
        super().set()


def test_waiter_signals_the_caller_outside_the_mutex(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B1-R7-3: ``Event.set`` takes the event's own lock, so the waiter calls it after
    leaving the shared mutex."""
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    free_on_set: list[bool] = []

    def checking_event(waiter: layout_module._LockWaiter) -> None:
        waiter.finished = _MutexCheckingEvent(free_on_set)

    _patch_waiter(monkeypatch, checking_event)
    handle = _hold_lock(tmp_path)
    try:
        assert not layout_module._wait_for_lock(path, key, 0.05, [])  # abandoned wait
    finally:
        handle.close()
    _assert_no_waiter_state()
    handle = _hold_lock(tmp_path)
    try:
        timer = threading.Timer(0.2, lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        timer.start()
        with layout_module._lock(tmp_path, 5):  # successful wait
            pass
        timer.join()
    finally:
        handle.close()
    _assert_no_waiter_state()
    assert free_on_set == [True, True]


def test_repeated_abandoned_waits_reuse_one_waiter_and_handle(tmp_path: Path) -> None:
    """Retrying in one process must not pile up threads and open files (B1-R5-2)."""
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=1).writer(WriterRole.NORMALIZER)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    handle = _hold_lock(tmp_path)
    try:
        for _ in range(2):
            with pytest.raises(WriteBoundaryError, match="waited 1s"):
                writer.write_new("silver/trades/a", b"data")
        threads = _waiter_threads()
        assert len(threads) == 1
        for _ in range(10):
            assert not layout_module._wait_for_lock(path, key, 0.02, [])
        assert _waiter_threads() == threads
        assert len(layout_module._WAITER_HANDLES) == 1
        assert len(layout_module._IDLE_WAITERS[key]) == 1
        assert list((tmp_path / "silver").iterdir()) == []
    finally:
        handle.close()
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)
    assert writer.write_new("silver/trades/a", b"data").read_bytes() == b"data"


def test_reused_waiter_hands_the_lock_to_the_next_wait(tmp_path: Path) -> None:
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    handle = _hold_lock(tmp_path)
    try:
        assert not layout_module._wait_for_lock(path, key, 0.05, [])
        threads = _waiter_threads()
        assert len(threads) == 1
        timer = threading.Timer(0.2, lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN))
        timer.start()
        start = time.monotonic()
        held: list[int] = []
        assert layout_module._wait_for_lock(path, key, 5, held)
        assert len(held) == 1 and time.monotonic() - start < 2
        timer.join()
    finally:
        handle.close()
    try:
        threads[0].join(5)
        assert not _waiter_threads()  # the same thread delivered the lock; no new one was started
        assert not _lock_is_free(tmp_path)
    finally:
        os.close(held[0])
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)


def test_waiters_are_bounded_by_waits_in_progress_at_the_same_time(tmp_path: Path) -> None:
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    handle = _hold_lock(tmp_path)
    try:
        results: list[bool] = []
        waits = [
            threading.Thread(target=lambda: results.append(layout_module._wait_for_lock(path, key, 0.3, [])))
            for _ in range(3)
        ]
        for wait in waits:
            wait.start()
        for wait in waits:
            wait.join(5)
        assert results == [False, False, False]
        assert len(_waiter_threads()) == 3
        for _ in range(10):
            assert not layout_module._wait_for_lock(path, key, 0.02, [])
        assert len(_waiter_threads()) == 3
        assert len(layout_module._WAITER_HANDLES) == 3
    finally:
        handle.close()
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)


class _PausingMutex:
    """Wraps the waiter mutex; a chosen thread pauses right after it leaves the mutex
    with a waiter handed back to the idle table, i.e. right after its hand-back."""

    def __init__(self, real: object, thread_name: str) -> None:
        self._real = real
        self._thread_name = thread_name
        self.left = threading.Event()
        self.resume = threading.Event()

    def acquire(self, *args: object, **kwargs: object) -> bool:
        return self._real.acquire(*args, **kwargs)

    def release(self) -> None:
        self._real.release()

    def __enter__(self) -> _PausingMutex:
        self._real.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._real.release()
        if threading.current_thread().name == self._thread_name and layout_module._IDLE_WAITERS:
            self.left.set()
            assert self.resume.wait(10)


def test_wait_that_hands_back_its_waiter_never_takes_the_lock_meant_for_the_next_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1-R6-1: wait A times out and hands its waiter back; before A returns, wait B
    reuses the waiter and gets the lock. Only B may report the lock as obtained."""
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    mutex = _PausingMutex(layout_module._WAITERS_MUTEX, "wait-A")
    monkeypatch.setattr(layout_module, "_WAITERS_MUTEX", mutex)
    results: dict[str, tuple[bool, list[int]]] = {}

    def wait(name: str, timeout: float) -> None:
        held: list[int] = []
        results[name] = (layout_module._wait_for_lock(path, key, timeout, held), held)

    handle = _hold_lock(tmp_path)
    wait_a = threading.Thread(target=wait, args=("wait-A", 0.2), name="wait-A")
    wait_b = threading.Thread(target=wait, args=("wait-B", 5), name="wait-B")
    try:
        wait_a.start()
        # A timed out and handed its waiter back; it is paused before returning.
        assert mutex.left.wait(5)
        assert len(layout_module._IDLE_WAITERS[key]) == 1
        wait_b.start()
        deadline = time.monotonic() + 5
        while key in layout_module._IDLE_WAITERS:  # B took the waiter over
            assert time.monotonic() < deadline
            time.sleep(0.01)
        handle.close()  # the reused waiter gets the lock and hands it to B
        wait_b.join(5)
        assert not wait_b.is_alive()
    finally:
        handle.close()
        mutex.resume.set()
        for thread in (wait_a, wait_b):
            if thread.ident is not None:
                thread.join(5)
    try:
        assert results["wait-A"] == (False, [])
        obtained, held_b = results["wait-B"]
        assert obtained and len(held_b) == 1
        assert not _lock_is_free(tmp_path)
    finally:
        for fd in results.get("wait-B", (False, []))[1]:
            os.close(fd)
    monkeypatch.undo()
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)


class _InterruptedRelease:
    """Wraps the waiter mutex; the first ``with`` block raises on exit without releasing,
    as when Ctrl-C lands between the end of the block and the release (CPython 3.9)."""

    def __init__(self, real: object) -> None:
        self._real = real
        self.leaked = False

    def acquire(self, *args: object, **kwargs: object) -> bool:
        return self._real.acquire(*args, **kwargs)

    def release(self) -> None:
        self._real.release()

    def __enter__(self) -> _InterruptedRelease:
        self._real.acquire()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if not self.leaked:
            self.leaked = True
            raise KeyboardInterrupt
        self._real.release()


def test_wait_interrupted_before_releasing_the_waiter_mutex_does_not_deadlock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1-R6-2: the interrupted wait's own cleanup must still hand its waiter back
    (or drop a waiter it never started) instead of deadlocking on the mutex it
    failed to release."""
    DataLayout.create(tmp_path)
    path, key = tmp_path / ".writer.lock", _lock_key(tmp_path)
    real = layout_module._WAITERS_MUTEX
    outcome: list[str] = []

    def interrupted_wait() -> None:
        monkeypatch.setattr(layout_module, "_WAITERS_MUTEX", _InterruptedRelease(real))
        try:
            layout_module._wait_for_lock(path, key, 5, [])
        except KeyboardInterrupt:
            outcome.append(f"idle={len(layout_module._IDLE_WAITERS.get(key, []))}")
            outcome.append(f"handles={len(layout_module._WAITER_HANDLES)}")
            real.release()  # what an interrupted program cannot do; here it lets the test clean up
        finally:
            monkeypatch.undo()

    def run(target: object) -> None:
        thread = threading.Thread(target=target, daemon=True)  # daemon: a deadlock must not hang pytest
        thread.start()
        thread.join(5)
        assert not thread.is_alive(), "the interrupted wait deadlocked on the waiter mutex"

    handle = _hold_lock(tmp_path)
    try:
        # No waiter to reuse: the new waiter was never started, so it never opened a handle.
        run(interrupted_wait)
        assert outcome == ["idle=0", "handles=0"]
        assert not _waiter_threads()
        # A started, abandoned waiter is reused, then handed back again.
        assert not layout_module._wait_for_lock(path, key, 0.05, [])
        threads = _waiter_threads()
        outcome.clear()
        run(interrupted_wait)
        assert outcome == ["idle=1", "handles=1"]
        assert _waiter_threads() == threads
    finally:
        handle.close()
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)


def test_release_still_frees_the_lock_when_interrupted_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """B1-R6-2: release unlocks and then closes; an interruption in the first step still closes."""
    DataLayout.create(tmp_path)
    real_flock = fcntl.flock
    opened: list[int] = []
    real_open = layout_module._open_lock_file

    def recording_open(path: Path) -> int:
        opened.append(real_open(path))
        return opened[-1]

    def interrupted_unlock(fd: int, operation: int) -> None:
        if operation == fcntl.LOCK_UN:
            raise KeyboardInterrupt
        real_flock(fd, operation)

    monkeypatch.setattr(layout_module, "_open_lock_file", recording_open)
    monkeypatch.setattr(fcntl, "flock", interrupted_unlock)
    with pytest.raises(KeyboardInterrupt), layout_module._lock(tmp_path, 0):
        assert not _lock_is_free(tmp_path)
    monkeypatch.undo()
    with pytest.raises(OSError):
        os.fstat(opened[0])
    assert _lock_is_free(tmp_path)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available")
def test_fork_while_holding_the_lock(tmp_path: Path) -> None:
    """A child forked inside a locked section never releases the parent's lock; the
    parent's release frees the lock even while a child still has a copy of the handle."""
    DataLayout.create(tmp_path)
    report_read, report_write = os.pipe()
    finish_read, finish_write = os.pipe()
    children: list[int] = []
    parent = os.getpid()

    def fork() -> int:
        with warnings.catch_warnings():
            # Python 3.12+ warns about fork in a multi-threaded process.
            warnings.simplefilter("ignore", DeprecationWarning)
            pid = os.fork()
        if pid:
            children.append(pid)
        return pid

    try:
        with layout_module._lock(tmp_path, 0):
            # Child 1 leaves the same locked section, as raw os.fork code would.
            unwinding = fork()
            if unwinding:
                assert os.read(report_read, 1) == b"1"  # child 1 saw the lock still held after leaving
                # Child 2 keeps its copy of the handle, as a multiprocessing worker would.
                if fork() == 0:
                    os.read(finish_read, 1)
                    os._exit(0)
        if unwinding == 0:
            try:
                os.write(report_write, b"0" if _lock_is_free(tmp_path) else b"1")
            finally:
                os._exit(0)
        assert _lock_is_free(tmp_path)  # child 2 is still running with its copy
    finally:
        if os.getpid() != parent:
            os._exit(1)  # a child must never return into pytest
        if children:
            os.write(finish_write, b"x")
        for pid in children:
            _, status = os.waitpid(pid, 0)
            assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        for fd in (report_read, report_write, finish_read, finish_write):
            os.close(fd)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available")
def test_forked_child_does_not_keep_an_abandoned_waiter_lock(tmp_path: Path) -> None:
    """A child forked after an abandoned wait must not hold the lock (B1-R5-3)."""
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=1).writer(WriterRole.NORMALIZER)
    handle = _hold_lock(tmp_path)
    child_ready_read, child_ready_write = os.pipe()
    release_child_read, release_child_write = os.pipe()
    pid = None
    try:
        with pytest.raises(WriteBoundaryError, match="waited 1s"):
            writer.write_new("silver/trades/a", b"data")
        assert len(layout_module._WAITER_HANDLES) == 1
        with warnings.catch_warnings():
            # Python 3.12+ warns about fork in a multi-threaded process; that is the case under test.
            warnings.simplefilter("ignore", DeprecationWarning)
            pid = os.fork()
        if pid == 0:
            status = 1
            try:
                handle.close()  # the test's own holder; the fork hook must close the waiter's handle
                clean = not layout_module._WAITER_HANDLES and not layout_module._IDLE_WAITERS
                usable = layout_module._WAITERS_MUTEX.acquire(timeout=1)
                os.write(child_ready_write, b"1" if clean and usable else b"0")
                os.read(release_child_read, 1)
                status = 0
            finally:
                os._exit(status)
        assert os.read(child_ready_read, 1) == b"1"
        handle.close()  # the lock is free now unless the child kept the waiter's handle
        _join_waiters()
        assert _lock_is_free(tmp_path)
        assert writer.write_new("silver/trades/a", b"data").read_bytes() == b"data"
    finally:
        handle.close()
        if pid:
            os.write(release_child_write, b"x")
            _, status = os.waitpid(pid, 0)
            assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        for fd in (child_ready_read, child_ready_write, release_child_read, release_child_write):
            os.close(fd)
    _assert_no_waiter_state()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available")
def test_fork_while_a_waiter_is_opening_its_handle_leaves_the_child_without_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B1-R8-2: the waiter opens and registers its handle in one mutex section, so a fork
    between the waiter's start and the registration still gives the child no copy."""
    DataLayout.create(tmp_path)
    key = _lock_key(tmp_path)
    real_open = layout_module._open_lock_file
    opened, may_return = threading.Event(), threading.Event()

    def pausing_open(path: Path) -> int:
        fd = real_open(path)
        if threading.current_thread().name == "writer-lock-waiter":
            opened.set()
            may_return.wait(5)  # the handle is open but not yet registered
        return fd

    monkeypatch.setattr(layout_module, "_open_lock_file", pausing_open)
    outcome: list[object] = []

    def wait_for_lock() -> None:
        try:
            with layout_module._lock(tmp_path, 5):
                outcome.append("obtained")
        except Exception as exc:  # reported through ``outcome``
            outcome.append(exc)

    handle = _hold_lock(tmp_path)
    caller = threading.Thread(target=wait_for_lock, daemon=True)
    parent, pid = os.getpid(), None
    try:
        caller.start()
        assert opened.wait(5)
        assert not layout_module._WAITER_HANDLES  # the waiter is inside its open
        # The open returns while fork waits for the mutex; a fork without the mutex happens first.
        threading.Timer(0.3, may_return.set).start()
        with warnings.catch_warnings():
            # Python 3.12+ warns about fork in a multi-threaded process; that is the case under test.
            warnings.simplefilter("ignore", DeprecationWarning)
            pid = os.fork()
        if pid == 0:
            copies = 100
            try:
                copies = 0
                for name in os.listdir("/dev/fd"):  # count handles to the lock file besides the holder's
                    fd = int(name)
                    try:
                        info = os.fstat(fd)
                    except OSError:
                        continue
                    if fd != handle.fileno() and (info.st_dev, info.st_ino) == key:
                        copies += 1
            finally:
                os._exit(min(copies, 100))
        deadline = time.monotonic() + 10
        while (waited := os.waitpid(pid, os.WNOHANG))[0] == 0 and time.monotonic() < deadline:
            time.sleep(0.01)
        if waited[0] == 0:
            os.kill(pid, 9)
            os.waitpid(pid, 0)
            pytest.fail("forked child hung")
        status = waited[1]
        assert os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0, "the child kept a copy of the waiter's handle"
    finally:
        if os.getpid() != parent:
            os._exit(1)  # a child must never return into pytest
        may_return.set()
        handle.close()
        caller.join(5)
    assert outcome == ["obtained"]
    _assert_no_waiter_state()
    assert _lock_is_free(tmp_path)


def test_waiter_lock_error_is_reported_without_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=2).writer(WriterRole.NORMALIZER)
    handle = _hold_lock(tmp_path)
    real_flock = fcntl.flock

    def failing_blocking_flock(fd: int, operation: int) -> None:
        if operation == fcntl.LOCK_EX:
            raise OSError(errno.ENOLCK, "No locks available")
        real_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", failing_blocking_flock)
    try:
        start = time.monotonic()
        with pytest.raises(WriteBoundaryError, match="No locks available"):
            writer.write_new("silver/trades/a", b"data")
        assert time.monotonic() - start < 1.5
    finally:
        handle.close()
    _join_waiters()
    assert list((tmp_path / "silver").iterdir()) == []


@pytest.mark.parametrize(
    ("failure", "reported"),
    [
        (
            lambda path: OSError(errno.EMFILE, "Too many open files"),
            "Write failed for silver/trades/a: .*Too many open",
        ),
        (lambda path: WriteBoundaryError(f"Writer lock must be a regular file: {path}"), "must be a regular file"),
    ],
    ids=["emfile", "not_a_regular_file"],
)
def test_waiter_that_cannot_open_the_lock_file_fails_at_once_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, failure: object, reported: str
) -> None:
    """B1-R8-1: the waiter thread opens its own handle. If that open fails while another
    holder has the lock, the caller gets that error at once instead of waiting out the
    timeout or, worse, taking a lock it does not hold, and nothing is left behind."""
    writer = DataLayout.create(tmp_path, lock_timeout_seconds=3).writer(WriterRole.NORMALIZER)
    real_open = layout_module._open_lock_file

    def open_fails_in_waiter(path: Path) -> int:
        if threading.current_thread().name == "writer-lock-waiter":
            raise failure(path)
        return real_open(path)

    thread_errors: list[BaseException | None] = []
    monkeypatch.setattr(threading, "excepthook", lambda args: thread_errors.append(args.exc_value))
    monkeypatch.setattr(layout_module, "_open_lock_file", open_fails_in_waiter)
    handle = _hold_lock(tmp_path)
    try:
        start = time.monotonic()
        with caplog.at_level(logging.WARNING), pytest.raises(WriteBoundaryError, match=reported) as raised:
            writer.write_new("silver/trades/a", b"data")
        assert time.monotonic() - start < 1.5  # not the 3 s timeout
        assert "waited" not in str(raised.value)  # the open failure, not "held by another process"
        _assert_no_waiter_state()  # waiter thread ended, no handle registered, nothing idle
        assert not _lock_is_free(tmp_path)  # the other holder still has the lock
    finally:
        handle.close()
    assert thread_errors == []
    assert not [record for record in caplog.records if getattr(record, "event", None) == "writer.lock_wait_error"]
    assert list((tmp_path / "silver").iterdir()) == []
    assert _lock_is_free(tmp_path)


_BACK_TO_BACK_WRITER = """
import sys, time
from pathlib import Path
from src.data_io.layout import DataLayout, WriterRole

root, ready, stop = (Path(arg) for arg in sys.argv[1:4])
writer = DataLayout.create(root, lock_timeout_seconds=30).writer(WriterRole.NORMALIZER)
deadline = time.monotonic() + 30
count = 0
while not stop.exists() and time.monotonic() < deadline:
    writer.write_new(f"silver/a/{count}", b"x")
    count += 1
    if count == 20:
        ready.touch()
print(count)
"""


def test_waiting_writer_gets_lock_while_another_process_writes_back_to_back(tmp_path: Path) -> None:
    """Task A publishes files back to back; task B must still get the lock within its timeout."""
    root = tmp_path / "data"
    root.mkdir()
    DataLayout.create(root)
    ready, stop = tmp_path / "ready", tmp_path / "stop"
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME"}}
    task_a = subprocess.Popen(
        [sys.executable, "-c", _BACK_TO_BACK_WRITER, str(root), str(ready), str(stop)],
        cwd=PROJECT_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 30
        while not ready.exists():
            assert task_a.poll() is None, task_a.communicate()[1]
            assert time.monotonic() < deadline, "task A did not start writing"
            time.sleep(0.01)
        writer_b = DataLayout.create(root, lock_timeout_seconds=2).writer(WriterRole.NORMALIZER)
        a_files = root / "silver/a"
        for attempt in range(5):
            written_before = len(list(a_files.iterdir()))
            start = time.monotonic()
            writer_b.write_new(f"silver/b/{attempt}", b"b")
            assert time.monotonic() - start < 2
            time.sleep(0.05)
            # Task A kept writing back to back around B's write.
            assert len(list(a_files.iterdir())) > written_before
            assert task_a.poll() is None
    finally:
        stop.touch()
        output, errors = task_a.communicate(timeout=60)
    assert task_a.returncode == 0, errors
    assert int(output) == len(list((root / "silver/a").iterdir()))
    assert sorted(path.name for path in (root / "silver/b").iterdir()) == [str(n) for n in range(5)]


def test_open_write_layout_uses_configured_timeout(tmp_path: Path) -> None:
    root = tmp_path / "data"
    environ = {"DATA_ROOT": str(root), "DATA_MIN_FREE_GIB": "0", "PIPELINE_WRITER_LOCK_TIMEOUT_SECONDS": "3"}
    config = PipelineConfig.load(environ=environ)
    layout = open_write_layout(config)
    assert layout.root == root.resolve()
    assert layout.lock_timeout_seconds == 3
    assert layout.writer(WriterRole.NORMALIZER).lock_timeout_seconds == 3
    assert (root / "silver").is_dir() and (root / "recovery").is_dir()
    with pytest.raises(TypeError, match="PipelineConfig"):
        open_write_layout(root)


def test_open_write_layout_runs_write_preflight_before_layout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "data"
    # Real preflight failure: not enough free space. Nothing may be created.
    too_much = PipelineConfig.load(environ={"DATA_ROOT": str(root), "DATA_MIN_FREE_GIB": str(10**9)})
    with pytest.raises(ConfigError, match="DATA_MIN_FREE_GIB"):
        open_write_layout(too_much)
    assert not root.exists()
    # Order: validate_for_write must finish before DataLayout.create starts.
    calls: list[str] = []
    real_validate, real_create = PipelineConfig.validate_for_write, DataLayout.create.__func__

    def validate(self: PipelineConfig) -> Path:
        calls.append("validate_for_write")
        return real_validate(self)

    def create(cls: type, path: Path, *, lock_timeout_seconds: int = 0) -> DataLayout:
        calls.append("create")
        return real_create(cls, path, lock_timeout_seconds=lock_timeout_seconds)

    monkeypatch.setattr(PipelineConfig, "validate_for_write", validate)
    monkeypatch.setattr(DataLayout, "create", classmethod(create))
    open_write_layout(PipelineConfig.load(environ={"DATA_ROOT": str(root), "DATA_MIN_FREE_GIB": "0"}))
    assert calls == ["validate_for_write", "create"]


_LAYOUT_CLASSES = frozenset({"DataLayout", "ScopedWriter"})
# The only places in src/ that may reference these classes other than in type annotations.
_ALLOWED_LAYOUT_REFERENCES = {
    ("src/data_io/layout.py", "open_write_layout", "DataLayout"),
    ("src/data_io/layout.py", "writer", "ScopedWriter"),
}


def _layout_bypasses(source: str, filename: str) -> list[tuple[str, int, str | None, str]]:
    """Find code that could create a layout or writer without ``open_write_layout``.

    Flags every reference to ``DataLayout`` or ``ScopedWriter`` that is not a
    type annotation, an ``isinstance``/``issubclass`` class argument, or a
    plain import: calls such as ``DataLayout(...)`` or ``layout.DataLayout.create(...)``,
    aliases such as ``make = DataLayout.create``, and ``getattr(DataLayout, ...)``.
    Renamed imports (``import DataLayout as X``) are flagged at the import.
    Returns ``(filename, line, enclosing function, name)`` for each finding.
    """
    tree = ast.parse(source, filename=filename)
    skipped: set[int] = set()
    for node in ast.walk(tree):
        annotations: list[ast.AST | None] = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg]
            annotations += [argument.annotation for argument in every if argument is not None]
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"isinstance", "issubclass"}
            and len(node.args) == 2
        ):
            annotations.append(node.args[1])
        for annotation in annotations:
            if annotation is not None:
                skipped.update(id(child) for child in ast.walk(annotation))
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]

    def enclosing(line: int) -> str | None:
        names = [function.name for function in functions if function.lineno <= line <= (function.end_lineno or line)]
        return names[-1] if names else None

    found = []
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        name = None
        if isinstance(node, ast.Name) and node.id in _LAYOUT_CLASSES:
            name = node.id
        elif isinstance(node, ast.Attribute) and node.attr in _LAYOUT_CLASSES:
            name = node.attr
        elif isinstance(node, ast.alias) and node.name.rsplit(".", 1)[-1] in _LAYOUT_CLASSES and node.asname:
            name = f"{node.name} as {node.asname}"
        if name is not None:
            line = getattr(node, "lineno", None) or next(
                parent.lineno for parent in ast.walk(tree) if node in getattr(parent, "names", ())
            )
            found.append((filename, line, enclosing(line), name))
    return found


@pytest.mark.parametrize(
    "source",
    [
        "from src.data_io.layout import DataLayout\nDataLayout.create(root)",
        "from src.data_io import layout as L\nL.DataLayout.create(root)",
        "import src.data_io.layout\nsrc.data_io.layout.DataLayout.create(root)",
        "from src.data_io.layout import DataLayout as Layout\nLayout.create(root)",
        "from src.data_io.layout import ScopedWriter as Writer",
        "from src.data_io.layout import DataLayout\nDataLayout(root=root).writer(role)",
        "from src.data_io.layout import ScopedWriter\nScopedWriter(root=root, role=role)",
        "from src.data_io import layout\nlayout.ScopedWriter(root=root, role=role)",
        "from src.data_io.layout import DataLayout\nmake = DataLayout.create\nmake(root)",
        "from src.data_io.layout import DataLayout\ngetattr(DataLayout, 'create')(root)",
        "import functools\nfrom src.data_io.layout import ScopedWriter\nfunctools.partial(ScopedWriter, root=root)",
    ],
    ids=[
        "create",
        "module_alias_create",
        "full_module_path_create",
        "renamed_import",
        "renamed_writer_import",
        "direct_layout",
        "direct_writer",
        "module_writer",
        "aliased_create",
        "getattr",
        "partial",
    ],
)
def test_layout_bypass_scan_catches_bypasses(source: str) -> None:
    assert _layout_bypasses(source, "src/probe.py")


def test_layout_bypass_scan_allows_annotations_type_checks_and_the_entry_point() -> None:
    source = """
from src.data_io.layout import DataLayout, ScopedWriter, open_write_layout

def run(layout: DataLayout, *writers: ScopedWriter, **named: ScopedWriter) -> DataLayout:
    current: DataLayout = open_write_layout(config)
    if isinstance(layout, DataLayout) and isinstance(current, (DataLayout, ScopedWriter)):
        return layout.writer(role)
"""
    assert _layout_bypasses(source, "src/probe.py") == []


def test_layout_bypass_scan_reports_location() -> None:
    source = "from src.data_io import layout\n\ndef task(root):\n    return layout.DataLayout.create(root)\n"
    assert _layout_bypasses(source, "src/probe.py") == [("src/probe.py", 4, "task", "DataLayout")]


def test_only_open_write_layout_creates_layouts_in_src() -> None:
    """Write tasks must not bypass the write preflight, partial recovery, or the configured lock timeout."""
    found = []
    for path in sorted((PROJECT_ROOT / "src").rglob("*.py")):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for _, line, function, name in _layout_bypasses(path.read_text(encoding="utf-8"), relative):
            if (relative, function, name) not in _ALLOWED_LAYOUT_REFERENCES:
                found.append(f"{relative}:{line} ({function}): {name}")
    assert found == []
    # The sanctioned references still exist, so the allow-list cannot go stale unnoticed.
    layout_source = (PROJECT_ROOT / "src/data_io/layout.py").read_text(encoding="utf-8")
    sanctioned = {
        (file, function, name) for file, _, function, name in _layout_bypasses(layout_source, "src/data_io/layout.py")
    }
    assert sanctioned == _ALLOWED_LAYOUT_REFERENCES
