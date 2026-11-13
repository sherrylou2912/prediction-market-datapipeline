"""Scoped, append-only writes and recovery under the configured data root.

The advisory lock coordinates cooperating writers on the same host. It is held
while recovering abandoned partials or writing and publishing a file.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import logging
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class WriterRole(str, Enum):
    IMPORTER = "imports"
    COLLECTOR = "bronze"
    NORMALIZER = "silver"
    PRODUCT = "gold"
    VALIDATOR = "quarantine"
    REGISTRY = "manifests"


class WriteBoundaryError(ValueError):
    """A scoped write, layout operation, or recovery operation failed."""


def _sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_file(fd: int) -> None:
    os.fsync(fd)
    # macOS offers a stronger flush through the device cache. Some external
    # filesystems do not support it; surface that limitation in the logs.
    full_sync = getattr(fcntl, "F_FULLFSYNC", None)
    if full_sync is not None:
        try:
            fcntl.fcntl(fd, full_sync)
        except OSError as exc:
            if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOTTY, errno.ENOSYS}:
                raise
            logger.warning(
                "F_FULLFSYNC unavailable after fsync: %s", exc, extra={"event": "writer.full_fsync_unavailable"}
            )


def _require_same_device(root: Path, path: Path) -> None:
    """Keep writer data and recovery on the root's filesystem."""
    if root.stat().st_dev != path.stat().st_dev:
        raise WriteBoundaryError(f"Cross-device data path is not supported: {path}")


def _mkdir(parent: Path, name: str) -> Path:
    path = parent / name
    try:
        path.mkdir()
    except FileExistsError:
        pass
    if path.is_symlink() or not path.is_dir():
        raise WriteBoundaryError(f"Data directory must be a real directory: {path}")
    # A previous mkdir may have succeeded even though syncing its parent failed.
    # Retry the sync before treating either a new or existing directory as safe.
    _sync_dir(parent)
    return path


@contextmanager
def _lock(root: Path) -> Iterator[None]:
    path = root / ".writer.lock"
    fd = None
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        if not stat.S_ISREG(os.fstat(fd).st_mode) or path.is_symlink():
            raise WriteBoundaryError(f"Writer lock must be a regular file: {path}")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise WriteBoundaryError(f"Writer lock is held by another process: {path}") from exc
        yield
    finally:
        if fd is not None:
            os.close(fd)


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _write_metadata(path: Path, metadata: dict) -> None:
    """Publish an entire sidecar atomically; an interrupted temp is not a sidecar."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=".metadata-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(metadata, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            _sync_file(handle.fileno())
        if path.exists() or path.is_symlink():
            raise WriteBoundaryError(f"Recovery metadata already exists: {path}")
        os.rename(temporary, path)
        _sync_dir(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _recover(root: Path, source: Path, kind: str, relative: Path, metadata: dict) -> Path:
    _require_same_device(root, source)
    destination = root
    for component in ("recovery", kind, *relative.parts):
        destination = _mkdir(destination, component)
        _require_same_device(root, destination)
    name = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')}-{uuid.uuid4().hex}"
    saved = destination / f"{name}.bin"
    metadata_path = destination / f"{name}.json"
    # Persist the explanation before moving the payload. If preparation fails,
    # the original partial remains in the layer and can be recovered later.
    # A sidecar may survive an interruption before the rename. Its referenced
    # payload must exist before the recovery can be treated as completed.
    _write_metadata(
        metadata_path,
        {**metadata, "recovery_path": str(saved.relative_to(root)), "completion_check": "payload_exists"},
    )
    # Rename within DATA_ROOT; never copy or delete the only preserved payload.
    os.rename(source, saved)
    _sync_dir(destination)
    _sync_dir(source.parent)
    return saved


def _validate_recovery_metadata(root: Path, sidecar: Path, payload: Path) -> None:
    """Check recovery sidecars without modifying evidence."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    def valid_digest(value: object) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None

    def reject_constant(value: str) -> None:
        raise ValueError(f"invalid JSON constant {value}")

    try:
        metadata = json.loads(
            sidecar.read_text(encoding="utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant
        )
        if not isinstance(metadata, dict):
            raise ValueError("metadata is not an object")
        if not isinstance(metadata.get("reason"), str) or not metadata["reason"].strip():
            raise ValueError("missing recovery reason")
        timestamp = metadata.get("recovered_at")
        if not isinstance(timestamp, str) or datetime.fromisoformat(timestamp).utcoffset() is None:
            raise ValueError("invalid recovery timestamp")
        recovery_path = str(payload.relative_to(root))
        if metadata.get("recovery_path") != recovery_path:
            raise ValueError("recovery path is missing or does not match payload")
        if metadata.get("completion_check") != "payload_exists":
            raise ValueError("completion check is missing or invalid")
        relative = payload.relative_to(root / "recovery")
        if len(relative.parts) < 3 or relative.parts[0] not in {"partials", "conflicts"}:
            raise ValueError("invalid recovery location")
        origin_key = "original_path" if relative.parts[0] == "partials" else "original_target"
        origin = metadata.get(origin_key)
        if origin is not None and origin != str(Path(*relative.parts[1:-1])):
            raise ValueError("original path does not match recovery location")
        if origin is None and metadata["reason"] != "recovery metadata missing; original context unknown":
            raise ValueError("missing original path")
        repaired = metadata["reason"] == "recovery metadata missing; original context unknown"
        if repaired or relative.parts[0] == "partials":
            if metadata.get("integrity") != "unknown":
                raise ValueError("partial or rebuilt payload integrity must be unknown")
            if not repaired:
                modified = metadata.get("modified_at")
                if not isinstance(modified, str) or datetime.fromisoformat(modified).utcoffset() is None:
                    raise ValueError("invalid partial modification timestamp")
            sha_key, size_key = "sha256", "size_bytes"
            if "new_sha256" in metadata or "new_size_bytes" in metadata:
                raise ValueError("unexpected conflict checksum or size")
        else:
            sha_key, size_key = "new_sha256", "new_size_bytes"
            if "sha256" in metadata or "size_bytes" in metadata:
                raise ValueError("unexpected partial checksum or size")
        expected_sha, expected_size = metadata.get(sha_key), metadata.get(size_key)
        if not valid_digest(expected_sha) or type(expected_size) is not int or expected_size < 0:
            raise ValueError("invalid payload checksum or size")
        if "existing_sha256" in metadata or "existing_size_bytes" in metadata:
            old_sha, old_size = metadata.get("existing_sha256"), metadata.get("existing_size_bytes")
            if not (
                old_sha is None
                and old_size is None
                or valid_digest(old_sha)
                and type(old_size) is int
                and old_size >= 0
            ):
                raise ValueError("invalid existing checksum or size")
        if payload.is_symlink():
            raise ValueError("payload is a symbolic link")
        if payload.exists():
            if not payload.is_file():
                raise ValueError("payload is not a regular file")
            _require_same_device(root, payload)
            checksum, size = _digest(payload)
            if checksum != expected_sha or size != expected_size:
                raise ValueError("payload checksum or size does not match")
    except (ValueError, OSError, UnicodeError, TypeError) as exc:
        raise WriteBoundaryError(f"Invalid recovery metadata {sidecar}: {exc}") from exc


def _repair_recovery_metadata(root: Path) -> None:
    """Mark orphaned recovery payloads as unknown without inventing provenance."""

    def fail_on_scan_error(error: OSError) -> None:
        raise error

    recovery = root / "recovery"
    for current, dirs, files in os.walk(recovery, followlinks=False, onerror=fail_on_scan_error):
        current_path = Path(current)
        _require_same_device(root, current_path)
        dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
        for name in dirs:
            _require_same_device(root, current_path / name)
        for name in files:
            payload = current_path / name
            if name.endswith(".json"):
                if payload.is_symlink() or not payload.is_file():
                    raise WriteBoundaryError(f"Recovery metadata must be a regular file: {payload}")
                expected_payload = payload.with_suffix(".bin")
                _require_same_device(root, payload)
                _validate_recovery_metadata(root, payload, expected_payload)
                if not expected_payload.is_file() or expected_payload.is_symlink():
                    logger.warning(
                        "Recovery metadata has no matching payload: %s",
                        payload,
                        extra={"event": "recovery.missing_payload"},
                    )
                continue
            if not name.endswith(".bin") or payload.is_symlink() or not payload.is_file():
                continue
            _require_same_device(root, payload)
            sidecar = payload.with_suffix(".json")
            if sidecar.exists() or sidecar.is_symlink():
                continue
            checksum, size = _digest(payload)
            metadata = {
                "reason": "recovery metadata missing; original context unknown",
                "integrity": "unknown",
                "recovery_path": str(payload.relative_to(root)),
                "completion_check": "payload_exists",
                "sha256": checksum,
                "size_bytes": size,
                "recovered_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_metadata(sidecar, metadata)
            logger.warning(
                "Rebuilt missing recovery metadata for %s; integrity unknown",
                payload,
                extra={"event": "recovery.metadata_rebuilt"},
            )


def _recover_partials(root: Path) -> None:
    def fail_on_scan_error(error: OSError) -> None:
        raise error

    for role in WriterRole:
        layer = root / role.value
        for current, dirs, files in os.walk(layer, followlinks=False, onerror=fail_on_scan_error):
            current_path = Path(current)
            _require_same_device(root, current_path)
            dirs[:] = [name for name in dirs if not (current_path / name).is_symlink()]
            for name in dirs:
                _require_same_device(root, current_path / name)
            for name in files:
                if not name.startswith(".partial-"):
                    continue
                source = current_path / name
                if source.is_symlink() or not source.is_file():
                    logger.warning(
                        "Skipping non-regular partial: %s", source, extra={"event": "recovery.partial_skipped"}
                    )
                    continue
                _require_same_device(root, source)
                # The interrupted writer may not have synced this file before
                # exiting. Sync its existing bytes before recording recovery.
                with source.open("rb") as handle:
                    _sync_file(handle.fileno())
                checksum, size = _digest(source)
                modified = datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat()
                relative = source.relative_to(root)
                saved = _recover(
                    root,
                    source,
                    "partials",
                    relative,
                    {
                        "original_path": str(relative),
                        "size_bytes": size,
                        "modified_at": modified,
                        "sha256": checksum,
                        "integrity": "unknown",
                        "recovered_at": datetime.now(timezone.utc).isoformat(),
                        "reason": "abandoned partial",
                    },
                )
                logger.warning(
                    "Recovered abandoned partial %s to %s", relative, saved, extra={"event": "recovery.partial_saved"}
                )


@dataclass(frozen=True)
class DataLayout:
    root: Path

    @classmethod
    def create(cls, root: Path) -> DataLayout:
        try:
            resolved_root = root.resolve(strict=True)
            if not resolved_root.is_dir():
                raise WriteBoundaryError(f"Data root is not a directory: {resolved_root}")
            with _lock(resolved_root):
                for role in WriterRole:
                    _require_same_device(resolved_root, _mkdir(resolved_root, role.value))
                _require_same_device(resolved_root, _mkdir(resolved_root, "recovery"))
                _repair_recovery_metadata(resolved_root)
                _recover_partials(resolved_root)
            return cls(root=resolved_root)
        except OSError as exc:
            raise WriteBoundaryError(f"Cannot create data layout at {root}: {exc}") from exc

    def writer(self, role: WriterRole) -> ScopedWriter:
        if not isinstance(role, WriterRole):
            raise TypeError("Writer role must be a WriterRole value.")
        return ScopedWriter(root=self.root, role=role)


@dataclass(frozen=True)
class ScopedWriter:
    root: Path
    role: WriterRole

    def write_new(self, path: str | Path, payload: bytes, *, receipt_id: str | None = None) -> Path:
        # Boundary checks protect cooperative processes, not hostile concurrent
        # directory swaps. The lock coordinates all cooperating writers.
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        relative = Path(path)
        if "\x00" in str(relative):
            raise WriteBoundaryError("Writer path must not contain NUL characters")
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2:
            raise WriteBoundaryError(f"Writer path must be a root-relative file path: {path}")
        if relative.name.startswith(".partial-"):
            raise WriteBoundaryError("Target name is reserved for incomplete writes")
        if relative.parts[0] != self.role.value:
            raise WriteBoundaryError(f"{self.role.name} writer may only write under {self.role.value}/: {path}")
        if self.role == WriterRole.COLLECTOR:
            if (
                not isinstance(receipt_id, str)
                or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", receipt_id) is None
                or len(relative.parts) < 3
                or receipt_id != relative.parts[-2]
            ):
                raise WriteBoundaryError(
                    "Bronze receipt_id must use lowercase ASCII letters, digits, _ or -, start with a letter or digit, "
                    "and be the file's direct parent directory"
                )
        try:
            with _lock(self.root):
                return self._write_locked(relative, payload)
        except OSError as exc:
            raise WriteBoundaryError(f"Write failed for {relative}: {exc}") from exc

    def _write_locked(self, relative: Path, payload: bytes) -> Path:
        layer = self.root / self.role.value
        if layer.is_symlink() or not layer.is_dir() or layer.resolve(strict=True) != layer:
            raise WriteBoundaryError(f"Writer layer is not a real directory: {layer}")
        _require_same_device(self.root, layer)
        parent = layer
        for component in relative.parts[1:-1]:
            if (parent / component).is_symlink():
                raise WriteBoundaryError(f"Writer path contains a symbolic link: {relative}")
            parent = _mkdir(parent, component)
            _require_same_device(self.root, parent)
        target = parent / relative.parts[-1]
        descriptor, temporary_name = tempfile.mkstemp(prefix=".partial-", dir=parent)
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            _sync_file(handle.fileno())
        try:
            os.link(temporary, target, follow_symlinks=False)
        except OSError as exc:
            if isinstance(exc, FileExistsError) and not target.is_symlink() and target.is_file():
                with target.open("rb") as existing:
                    identical = existing.read() == payload
                if identical:
                    temporary.unlink()
                    _sync_dir(parent)
                    logger.info(
                        "Identical write retry succeeded for %s", target, extra={"event": "writer.identical_retry"}
                    )
                    return target
            new_checksum, new_size = _digest(temporary)
            old_checksum, old_size = (None, None)
            if not target.is_symlink() and target.is_file():
                old_checksum, old_size = _digest(target)
            reason = "conflicting target" if isinstance(exc, FileExistsError) else "publication failed"
            saved = _recover(
                self.root,
                temporary,
                "conflicts",
                relative,
                {
                    "original_target": str(relative),
                    "recovered_at": datetime.now(timezone.utc).isoformat(),
                    "reason": reason,
                    "publication_error": str(exc),
                    "new_sha256": new_checksum,
                    "new_size_bytes": new_size,
                    "existing_sha256": old_checksum,
                    "existing_size_bytes": old_size,
                },
            )
            raise WriteBoundaryError(f"Cannot replace or publish {target}; data preserved at {saved}: {exc}") from exc
        _sync_dir(parent)
        temporary.unlink()
        _sync_dir(parent)
        return target
