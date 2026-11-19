"""Scoped, append-only writes and recovery under the configured data root.

The advisory lock coordinates cooperating writers on the same host. It is held
while recovering abandoned partials or writing and publishing a file. A writer
with a non-zero timeout waits with a blocking ``flock`` so it is woken when the
lock is released; this was verified only on macOS. A wait that gives up leaves
its background thread and lock-file handle blocked until the lock is free; a
later wait on the same lock reuses them, and a forked child closes its copies.

Write tasks obtain their layout through ``open_write_layout(config)``.
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
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from src.config import PipelineConfig
from src.config.validation import MAX_LOCK_TIMEOUT_SECONDS

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


def _open_lock_file(path: Path) -> int:
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode) or path.is_symlink():
            raise WriteBoundaryError(f"Writer lock must be a regular file: {path}")
    except BaseException:
        os.close(fd)
        raise
    return fd


# Waiter state shared by every thread in this process; all of it is guarded by
# ``_WAITERS_MUTEX``. ``_IDLE_WAITERS`` holds, per lock file, waiters whose
# caller gave up while their thread is still blocked in ``flock``; a later wait
# for the same file reuses one instead of starting another thread and handle.
# ``_WAITER_HANDLES`` holds the handles still owned by waiter threads; a forked
# child closes its copies so it never keeps the lock held.
#
# The mutex is reentrant only as damage control: on CPython 3.9 a
# KeyboardInterrupt can land between the end of a ``with`` body and the release,
# leaving the mutex held. The interrupted thread's own cleanup can then still
# enter it instead of deadlocking against itself; other threads (and waiter
# threads, which then keep any lock they obtain) block on it until the process
# exits. Nothing here acquires it re-entrantly by design. Its critical sections
# only do short operations, including a waiter thread opening the lock file (a
# brief system call); none of them waits for the lock itself.
_WAITERS_MUTEX = threading.RLock()
_IDLE_WAITERS: dict[tuple[int, int], list[_LockWaiter]] = {}
_WAITER_HANDLES: set[int] = set()


class _LockWaiter:
    """Wait for the writer lock with a blocking ``flock`` in a background thread.

    The kernel wakes a blocked waiter as soon as the holder releases the lock,
    so a writer that releases and immediately re-acquires it rarely keeps the
    waiter out, unlike fixed-interval polling. This is not a strict queue, and
    it was verified only on macOS. The calling thread enforces the timeout.

    ``claim`` is the handle list of the one wait that currently owns this
    waiter, or ``None`` while nobody does. When ``flock`` returns, the thread
    appends its handle to that list, so the lock can only go to the current
    owner and is in the owner's list the moment it is obtained. If nobody owns
    the waiter then, the thread closes the handle at once, releasing the lock.

    The thread opens its handle itself and is the only code that closes it (a
    forked child closes only its own copy). A caller therefore never has to
    guess whether the thread started: ``Thread.start`` can raise after the
    thread is already running, e.g. when a signal handler raises in it.
    Created and started only through ``_wait_for_lock``.
    """

    def __init__(self, path: Path, key: tuple[int, int]) -> None:
        self.path = path
        self.key = key
        self.claim: list[int] | None = None
        self.done = False
        self.error: Exception | None = None
        self.finished = threading.Event()
        self.thread = threading.Thread(target=self._wait, name="writer-lock-waiter", daemon=True)

    def _wait(self) -> None:
        fd: int | None = None
        error: Exception | None = None
        try:
            with _WAITERS_MUTEX:  # registered at once, so a fork never sees an unregistered handle
                fd = _open_lock_file(self.path)
                _WAITER_HANDLES.add(fd)
            fcntl.flock(fd, fcntl.LOCK_EX)
        except Exception as exc:  # OSError, or WriteBoundaryError for a non-regular lock file
            error = exc
        with _WAITERS_MUTEX:
            _forget_idle(self)
            self.done = True
            claim = self.claim
            if fd is not None:
                _WAITER_HANDLES.discard(fd)
                if claim is not None and error is None:
                    claim.append(fd)  # the owning wait now holds the lock
                else:
                    os.close(fd)  # releases the lock if nobody is waiting for it any more
            if claim is not None:
                self.error = error  # reported by the owning wait
        # Outside the mutex: Event.set takes the event's own lock.
        self.finished.set()
        if error is not None and claim is None:
            logger.warning(
                "Abandoned writer lock wait ended with an error: %s",
                error,
                extra={"event": "writer.lock_wait_error"},
            )


def _forget_idle(waiter: _LockWaiter) -> None:
    idle = _IDLE_WAITERS.get(waiter.key, [])
    if waiter in idle:
        idle.remove(waiter)
    if not idle:
        _IDLE_WAITERS.pop(waiter.key, None)


def _take_idle_waiter(key: tuple[int, int]) -> _LockWaiter | None:
    """Pop a reusable waiter for ``key``; call with ``_WAITERS_MUTEX`` held."""
    idle = _IDLE_WAITERS.get(key, [])
    found = None
    while idle and found is None:
        candidate = idle.pop()
        # Defensive: drop a waiter whose thread is no longer running (one whose
        # start failed is never made idle, so this only guards unexpected deaths).
        if candidate.thread.is_alive():
            found = candidate
    if not idle:
        _IDLE_WAITERS.pop(key, None)
    return found


def _wait_for_lock(path: Path, key: tuple[int, int], timeout: float, held: list[int]) -> bool:
    """Wait up to ``timeout`` seconds for the lock; return whether it was obtained.

    On success the waiter thread has appended the handle that holds the lock to
    ``held``. The caller owns ``held`` and closes every handle in it, also when
    this function raises, so the held handle is never only in a local variable.

    Reuses a waiter that an earlier, abandoned wait on the same lock file left
    blocked, so a process never has more waiter threads (and handles) for a
    lock file than the most waits it had in progress on it at the same time;
    a single thread that retries keeps at most one. Before returning or
    raising, the wait either finds the waiter finished (its handle is then in
    ``held``, or its error is raised here) or hands it back as unowned under
    the mutex; after that it never reads the waiter again, because another
    wait may already own it.

    Python delivers ``KeyboardInterrupt`` (or an exception from a signal
    handler) between bytecodes, so a few-instruction gap remains in which an
    interruption can leave one waiter that is no longer reused or, if the
    waiter is still owned, a waiter that keeps the lock once it gets it. An
    exception from ``Thread.start`` only leaves a waiter that is not reused.
    See ``_lock`` for the documented limitation.
    """
    deadline = time.monotonic() + max(timeout, 0)
    waiter: _LockWaiter | None = None
    created = started = False
    obtained = False
    error: Exception | None = None
    try:
        # ``with`` on the C lock: an interruption that arrives while blocked here is
        # delivered only after the block is set up, so it cannot leave the mutex held.
        # (``acquire(timeout=...)`` followed by ``try`` measured far worse: the
        # interruption lands between the two and leaves the mutex held.)
        with _WAITERS_MUTEX:
            waiter = _take_idle_waiter(key)
            if waiter is None:
                created = True
                waiter = _LockWaiter(path, key)
            waiter.claim = held
        if created:
            waiter.thread.start()
            started = True
        waiter.finished.wait(max(deadline - time.monotonic(), 0))
    finally:
        if waiter is not None:
            with _WAITERS_MUTEX:
                # Decide the outcome here; once handed back, the waiter belongs to whoever reuses it.
                if waiter.done:
                    # Finished while this wait owned it: its handle is in ``held``, or this is its error.
                    error = waiter.error
                    obtained = error is None
                else:
                    waiter.claim = None
                    if started or not created:
                        _IDLE_WAITERS.setdefault(key, []).append(waiter)
                    # Otherwise ``start`` was not reached or raised, possibly after the thread
                    # began running. Such a waiter is not reused; if it is running, it closes
                    # its own handle once ``flock`` returns, as for any unowned waiter.
    if error is not None:
        raise error
    return obtained


def _close_waiter_handles_in_child() -> None:
    """After ``fork``: the child has no waiter threads, so close their inherited handles."""
    global _WAITERS_MUTEX
    # The child is single-threaded; a fresh mutex is free even if the parent's was left held.
    _WAITERS_MUTEX = threading.RLock()
    for fd in _WAITER_HANDLES:
        os.close(fd)
    _WAITER_HANDLES.clear()
    _IDLE_WAITERS.clear()


if hasattr(os, "register_at_fork"):
    # Holding the mutex across fork keeps the waiter state consistent in the child.
    os.register_at_fork(
        before=lambda: _WAITERS_MUTEX.acquire(),
        after_in_parent=lambda: _WAITERS_MUTEX.release(),
        after_in_child=_close_waiter_handles_in_child,
    )


@contextmanager
def _lock(root: Path, timeout_seconds: int = 0) -> Iterator[None]:
    """Hold ``root/.writer.lock`` for the ``with`` body, waiting up to ``timeout_seconds``.

    Release first unlocks the handle and then closes it, in nested ``finally``
    blocks, so one interruption during release still releases the lock. Only
    the process that took the lock unlocks it: a child forked inside the body
    that unwinds the same ``with`` only closes its copy. Python can still
    deliver an interruption (Ctrl-C, or an exception raised by a signal handler)
    at other bytecode boundaries; if the program catches it and keeps running,
    the lock can stay held until the process exits: a later wait in this process
    then fails at its timeout and, especially on CPython 3.9, a wait or ``fork``
    in another thread of this process can hang. After
    Ctrl-C, let the process exit; the operating system then releases the lock.
    """
    # Checked here so direct DataLayout/ScopedWriter construction is covered too.
    if type(timeout_seconds) is not int or not 0 <= timeout_seconds <= MAX_LOCK_TIMEOUT_SECONDS:
        raise WriteBoundaryError(f"lock_timeout_seconds must be an integer from 0 to {MAX_LOCK_TIMEOUT_SECONDS}")
    path = root / ".writer.lock"
    held = f"Writer lock is held by another process: {path} (waited {timeout_seconds}s)"
    deadline = time.monotonic() + timeout_seconds
    owner = os.getpid()
    handles = [_open_lock_file(path)]  # at most one handle at any time
    try:
        try:
            fcntl.flock(handles[0], fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if timeout_seconds == 0:
                raise WriteBoundaryError(held) from exc
            info = os.fstat(handles[0])
            os.close(handles.pop())  # the waiter thread opens its own handle
            if not _wait_for_lock(path, (info.st_dev, info.st_ino), deadline - time.monotonic(), handles):
                raise WriteBoundaryError(held) from exc
        yield
    finally:
        try:
            if os.getpid() == owner:
                for handle in handles:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            for handle in handles:
                os.close(handle)


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
    lock_timeout_seconds: int = 0

    @classmethod
    def create(cls, root: Path, *, lock_timeout_seconds: int = 0) -> DataLayout:
        try:
            resolved_root = root.resolve(strict=True)
            if not resolved_root.is_dir():
                raise WriteBoundaryError(f"Data root is not a directory: {resolved_root}")
            with _lock(resolved_root, lock_timeout_seconds):
                for role in WriterRole:
                    _require_same_device(resolved_root, _mkdir(resolved_root, role.value))
                _require_same_device(resolved_root, _mkdir(resolved_root, "recovery"))
                _repair_recovery_metadata(resolved_root)
                _recover_partials(resolved_root)
            return cls(root=resolved_root, lock_timeout_seconds=lock_timeout_seconds)
        except OSError as exc:
            raise WriteBoundaryError(f"Cannot create data layout at {root}: {exc}") from exc

    def writer(self, role: WriterRole) -> ScopedWriter:
        if not isinstance(role, WriterRole):
            raise TypeError("Writer role must be a WriterRole value.")
        return ScopedWriter(root=self.root, role=role, lock_timeout_seconds=self.lock_timeout_seconds)


def open_write_layout(config: PipelineConfig) -> DataLayout:
    """The entry point for write tasks: write preflight first, then the layout with the configured lock timeout.

    A test scans ``src/`` and rejects any other ``DataLayout.create`` or direct
    ``DataLayout(...)``/``ScopedWriter(...)`` construction, so every write task
    runs ``validate_for_write`` before any directory is created, recovers
    abandoned partials, and waits ``writer_lock_timeout_seconds``.
    """
    if not isinstance(config, PipelineConfig):
        raise TypeError("config must be a PipelineConfig value")
    root = config.validate_for_write()
    return DataLayout.create(root, lock_timeout_seconds=config.writer_lock_timeout_seconds)


@dataclass(frozen=True)
class ScopedWriter:
    root: Path
    role: WriterRole
    lock_timeout_seconds: int = 0

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
        if (
            len(relative.parts) == 2
            and relative.parts[0] == "manifests"
            and relative.name.casefold().startswith("ledger.sqlite3")
        ):
            raise WriteBoundaryError(f"Target name is reserved for the ledger: {path}")
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
            with _lock(self.root, self.lock_timeout_seconds):
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
