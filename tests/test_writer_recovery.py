"""Recovery and durability guarantees for cooperative local writers."""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path

import pytest

from src.data_io.layout import DataLayout, WriteBoundaryError, WriterRole


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
