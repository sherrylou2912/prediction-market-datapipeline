"""Validation of pipeline settings and startup storage preconditions."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


class ConfigError(ValueError):
    """A configuration value or startup storage precondition is invalid."""


def parse_data_root(value: str) -> Path:
    if not value.strip():
        raise ConfigError("DATA_ROOT is required. Set it to an absolute, writable data directory.")
    root = Path(value.strip()).expanduser()
    if not root.is_absolute():
        raise ConfigError(f"DATA_ROOT must be an absolute path: {value!r}")
    return root


def parse_min_free_gib(value: int | str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.")
    try:
        minimum = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.") from exc
    if minimum < 0:
        raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.")
    return minimum


def parse_log_level(value: str) -> str:
    level = value.strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("PIPELINE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
    return level


def validate_data_root(root: Path, min_free_gib: int) -> Path:
    existing = root
    while not existing.exists():
        if existing == existing.parent:
            raise ConfigError(f"DATA_ROOT has no existing parent: {root}")
        existing = existing.parent
    if not existing.is_dir():
        raise ConfigError(f"DATA_ROOT is not a directory or has a non-directory parent: {existing}")

    try:
        free_bytes = shutil.disk_usage(existing).free
    except OSError as exc:
        raise ConfigError(f"Cannot check free disk space for DATA_ROOT {root}: {exc}") from exc
    required_bytes = min_free_gib * 1024**3
    if free_bytes < required_bytes:
        free_gib = free_bytes / 1024**3
        raise ConfigError(
            f"DATA_ROOT {root} has {free_gib:.1f} GiB free; DATA_MIN_FREE_GIB requires {min_free_gib} GiB."
        )

    try:
        root.mkdir(parents=True, exist_ok=True)
        if not root.is_dir():
            raise OSError("path is not a directory")
        with tempfile.TemporaryFile(dir=root):
            pass
    except OSError as exc:
        raise ConfigError(f"DATA_ROOT is not writable: {root} ({exc})") from exc
    return root.resolve(strict=True)
