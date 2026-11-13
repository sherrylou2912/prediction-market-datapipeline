"""Shared runtime configuration and task-specific data-root preflight checks."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any, ClassVar

from pydantic import PrivateAttr

from src.config.errors import ConfigError
from src.config.loader import DEFAULT_CONFIG_DIR, load_environment, load_json_object
from src.config.validation import AbsolutePath, ConfigModel, LogLevel, NonnegativeInteger


def _nearest_existing_directory(path: Path) -> Path:
    existing = path
    while not existing.exists():
        if existing == existing.parent:
            raise ConfigError(f"DATA_ROOT has no existing parent: {path}")
        existing = existing.parent
    if not existing.is_dir():
        raise ConfigError(f"DATA_ROOT is not a directory or has a non-directory parent: {existing}")
    return existing


def _sync_directory(path: Path) -> None:
    """Persist directory entries created or removed by the write preflight."""
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _check_macos_volume(path: Path) -> None:
    """Check volume components before following any aliases that could hide them."""
    if len(path.parts) >= 3 and path.parts[1].casefold() == "volumes" and ".." in path.parts:
        raise ConfigError("DATA_ROOT under /Volumes must not contain '..' path components")
    current = Path("/")
    remaining = deque(path.parts[1:])
    followed = 0
    while remaining:
        component = remaining.popleft()
        if component == "..":
            current = current.parent
            continue
        candidate = current / component
        if len(candidate.parts) == 3 and candidate.parts[1].casefold() == "volumes":
            try:
                mounted = not candidate.is_symlink() and candidate.exists() and os.path.ismount(candidate)
            except OSError as exc:
                raise ConfigError(f"Cannot verify DATA_ROOT volume is mounted: {candidate} ({exc})") from exc
            if not mounted:
                raise ConfigError(f"DATA_ROOT volume is not mounted: {candidate}")
        if candidate.is_symlink():
            followed += 1
            if followed > 40:
                raise ConfigError(f"Cannot resolve DATA_ROOT symbolic links: {path}")
            try:
                target = Path(os.readlink(candidate))
            except OSError as exc:
                raise ConfigError(f"Cannot resolve DATA_ROOT symbolic link: {candidate} ({exc})") from exc
            if target.is_absolute():
                current = Path("/")
                remaining.extendleft(reversed(target.parts[1:]))
            else:
                remaining.extendleft(reversed(target.parts))
        else:
            current = candidate


class _StorageDefaults(ConfigModel):
    _error_names: ClassVar[dict[str, str]] = {"min_free_gib": "DATA_MIN_FREE_GIB"}
    min_free_gib: NonnegativeInteger


class _RuntimeDefaults(ConfigModel):
    _error_names: ClassVar[dict[str, str]] = {"log_level": "PIPELINE_LOG_LEVEL"}
    log_level: LogLevel


class _ConfigDirectory(ConfigModel):
    _error_names: ClassVar[dict[str, str]] = {"config_dir": "PIPELINE_CONFIG_DIR"}
    config_dir: AbsolutePath


class PipelineConfig(ConfigModel):
    """Shared, non-secret runtime settings used by every pipeline task."""

    _error_names: ClassVar[dict[str, str]] = {
        "data_root": "DATA_ROOT",
        "min_free_gib": "DATA_MIN_FREE_GIB",
        "log_level": "PIPELINE_LOG_LEVEL",
        "config_dir": "PIPELINE_CONFIG_DIR",
    }
    data_root: AbsolutePath
    min_free_gib: NonnegativeInteger
    log_level: LogLevel
    config_dir: AbsolutePath
    # Where each effective value came from; set by load(), "direct" otherwise.
    # Immutable and picklable (field, source) pairs.
    _sources: tuple[tuple[str, str], ...] = PrivateAttr(default=())

    @classmethod
    def load(
        cls,
        *,
        config_dir: Path | None = None,
        environ: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> PipelineConfig:
        values = load_environment(environ, env_file)
        raw_config_dir = values.get("PIPELINE_CONFIG_DIR", "").strip()
        directory = (
            config_dir
            if config_dir is not None
            else Path(raw_config_dir).expanduser()
            if raw_config_dir
            else DEFAULT_CONFIG_DIR
        )
        directory = _ConfigDirectory(config_dir=directory).config_dir

        storage = _StorageDefaults(**load_json_object(directory / "storage.json"))
        runtime = _RuntimeDefaults(**load_json_object(directory / "runtime.json"))
        raw_root = values.get("DATA_ROOT", "").strip()
        if not raw_root:
            raise ConfigError("DATA_ROOT is required. Set it to an absolute data directory.")
        raw_minimum = values.get("DATA_MIN_FREE_GIB", "").strip()
        if raw_minimum and (not raw_minimum.isascii() or not raw_minimum.isdecimal()):
            raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer using decimal digits.")
        try:
            minimum = int(raw_minimum) if raw_minimum else storage.min_free_gib
        except ValueError as exc:
            raise ConfigError("DATA_MIN_FREE_GIB is too large to parse.") from exc
        raw_level = values.get("PIPELINE_LOG_LEVEL", "").strip()
        config = cls(
            data_root=Path(raw_root).expanduser(),
            min_free_gib=minimum,
            log_level=raw_level or runtime.log_level,
            config_dir=directory.resolve(strict=True),
        )
        sources = {
            "data_root": "environment:DATA_ROOT",
            "min_free_gib": "environment:DATA_MIN_FREE_GIB" if raw_minimum else "default:storage.json",
            "log_level": "environment:PIPELINE_LOG_LEVEL" if raw_level else "default:runtime.json",
            "config_dir": "argument:config_dir"
            if config_dir is not None
            else "environment:PIPELINE_CONFIG_DIR"
            if raw_config_dir
            else "default:src/config/defaults",
        }
        config._sources = tuple(sources.items())
        return config

    def effective_settings(self) -> dict[str, Any]:
        """Return every effective non-secret value, its source, and a hash of the values.

        PipelineConfig holds no secrets, so all fields are reported. The hash
        covers the values only, so the same settings from different sources match.
        """
        values = {name: str(getattr(self, name)) for name in type(self).model_fields}
        sources = dict(self._sources)
        digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()
        return {
            "settings": {
                name: {"value": value, "source": sources.get(name, "direct")} for name, value in values.items()
            },
            "sha256": digest,
        }

    def check_configured_root(self) -> Path:
        """Check path suitability without reading, creating, or writing data."""
        _nearest_existing_directory(self.data_root)
        return self.data_root.resolve(strict=True) if self.data_root.exists() else self.data_root

    def validate_for_read(self) -> Path:
        """Require an existing readable data directory without probing writes."""
        checked_root = self.check_configured_root()
        if not checked_root.exists():
            raise ConfigError(f"DATA_ROOT does not exist for a read-only job: {checked_root}")
        try:
            with os.scandir(checked_root) as entries:
                next(entries, None)
        except OSError as exc:
            raise ConfigError(f"DATA_ROOT is not readable: {checked_root} ({exc})") from exc
        return checked_root

    def validate_for_write(self) -> Path:
        """Check free capacity, write access, and hard-link support before writes."""
        if sys.platform == "darwin":
            _check_macos_volume(self.data_root)
        existing = _nearest_existing_directory(self.data_root)
        try:
            free_bytes = shutil.disk_usage(existing).free
        except OSError as exc:
            raise ConfigError(f"Cannot check free disk space for DATA_ROOT {self.data_root}: {exc}") from exc
        required_bytes = self.min_free_gib * 1024**3
        if free_bytes < required_bytes:
            free_gib = free_bytes / 1024**3
            raise ConfigError(
                f"DATA_ROOT {self.data_root} has {free_gib:.1f} GiB free; "
                f"DATA_MIN_FREE_GIB requires {self.min_free_gib} GiB."
            )

        created: list[Path] = []
        missing = []
        current = self.data_root
        while not current.exists():
            missing.append(current)
            current = current.parent
        try:
            for directory in reversed(missing):
                try:
                    directory.mkdir()
                    created.append(directory)
                except FileExistsError:
                    if not directory.is_dir():
                        raise
                # Also sync if a cooperating process created this directory
                # after our initial existence check.
                _sync_directory(directory.parent)
            if not self.data_root.is_dir():
                raise OSError("path is not a directory")
            with tempfile.TemporaryFile(dir=self.data_root):
                pass
            with tempfile.TemporaryDirectory(prefix=".hardlink-check-", dir=self.data_root) as probe:
                source = Path(probe) / "source"
                source.touch()
                try:
                    os.link(source, Path(probe) / "link")
                except OSError as exc:
                    raise ConfigError(f"DATA_ROOT does not support hard links: {self.data_root} ({exc})") from exc
        except (OSError, ConfigError) as exc:
            cleanup_errors = []
            for directory in reversed(created):
                try:
                    directory.rmdir()
                    _sync_directory(directory.parent)
                except OSError as cleanup_exc:
                    cleanup_errors.append(f"{directory}: {cleanup_exc}")
            suffix = f"; cannot remove newly created directories: {'; '.join(cleanup_errors)}" if cleanup_errors else ""
            if isinstance(exc, ConfigError):
                raise ConfigError(f"{exc}{suffix}") from exc
            raise ConfigError(f"DATA_ROOT is not writable: {self.data_root} ({exc}){suffix}") from exc
        return self.data_root.resolve(strict=True)
