"""Environment-driven startup configuration for the v1 pipeline."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """A startup setting or data-root precondition is invalid."""


@dataclass(frozen=True)
class PipelineConfig:
    data_root: Path
    min_free_gib: int = 200
    log_level: str = "INFO"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PipelineConfig:
        values = os.environ if environ is None else environ
        raw_root = values.get("DATA_ROOT", "").strip()
        if not raw_root:
            raise ConfigError("DATA_ROOT is required. Set it to an absolute, writable data directory.")
        root = Path(raw_root).expanduser()
        if not root.is_absolute():
            raise ConfigError(f"DATA_ROOT must be an absolute path: {raw_root!r}")

        raw_minimum = values.get("DATA_MIN_FREE_GIB", "200").strip()
        try:
            minimum = int(raw_minimum)
        except ValueError as exc:
            raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.") from exc
        if minimum < 0:
            raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.")

        log_level = values.get("PIPELINE_LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigError("PIPELINE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        return cls(data_root=root, min_free_gib=minimum, log_level=log_level)

    def validate_startup(self) -> Path:
        root = self.data_root
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
        required_bytes = self.min_free_gib * 1024**3
        if free_bytes < required_bytes:
            free_gib = free_bytes / 1024**3
            raise ConfigError(
                f"DATA_ROOT {root} has {free_gib:.1f} GiB free; DATA_MIN_FREE_GIB requires {self.min_free_gib} GiB."
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
