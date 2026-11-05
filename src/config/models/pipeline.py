"""Shared runtime configuration and task-specific data-root preflight checks."""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from src.config.errors import ConfigError
from src.config.loader import DEFAULT_CONFIG_DIR, load_environment, load_json_setting


def _parse_data_root(value: str) -> Path:
    if not value.strip():
        raise ConfigError("DATA_ROOT is required. Set it to an absolute data directory.")
    root = Path(value.strip()).expanduser()
    if not root.is_absolute():
        raise ConfigError(f"DATA_ROOT must be an absolute path: {value!r}")
    return root


def _parse_min_free_gib(value: int | str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.")
    try:
        minimum = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.") from exc
    if minimum < 0:
        raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.")
    return minimum


def _parse_log_level(value: str) -> str:
    level = value.strip().upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError("PIPELINE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
    return level


def _nearest_existing_directory(path: Path) -> Path:
    existing = path
    while not existing.exists():
        if existing == existing.parent:
            raise ConfigError(f"DATA_ROOT has no existing parent: {path}")
        existing = existing.parent
    if not existing.is_dir():
        raise ConfigError(f"DATA_ROOT is not a directory or has a non-directory parent: {existing}")
    return existing


@dataclass(frozen=True)
class PipelineConfig:
    """Shared, non-secret runtime settings used by every pipeline task."""

    data_root: Path
    min_free_gib: int
    log_level: str
    config_dir: Path

    def __post_init__(self) -> None:
        """校验所有构造入口的共享字段，不访问或修改磁盘。"""
        if not isinstance(self.data_root, Path) or not self.data_root.is_absolute():
            raise ConfigError("DATA_ROOT must be an absolute Path.")
        if "\x00" in str(self.data_root):
            raise ConfigError("DATA_ROOT must not contain NUL characters.")
        if type(self.min_free_gib) is not int or self.min_free_gib < 0:
            raise ConfigError("DATA_MIN_FREE_GIB must be a nonnegative integer.")
        if not isinstance(self.log_level, str):
            raise ConfigError("PIPELINE_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        if not isinstance(self.config_dir, Path) or not self.config_dir.is_absolute():
            raise ConfigError("PIPELINE_CONFIG_DIR must be an absolute Path.")
        if "\x00" in str(self.config_dir):
            raise ConfigError("PIPELINE_CONFIG_DIR must not contain NUL characters.")
        object.__setattr__(self, "log_level", _parse_log_level(self.log_level))

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
        if config_dir is not None:
            directory = config_dir
        elif raw_config_dir:
            directory = Path(raw_config_dir).expanduser()
        else:
            directory = DEFAULT_CONFIG_DIR
        if not isinstance(directory, Path) or not directory.is_absolute():
            raise ConfigError(f"PIPELINE_CONFIG_DIR must be an absolute path: {directory}")
        if "\x00" in str(directory):
            raise ConfigError("PIPELINE_CONFIG_DIR must not contain NUL characters.")

        default_minimum = load_json_setting(directory / "storage.json", "min_free_gib", int)
        default_log_level = load_json_setting(directory / "runtime.json", "log_level", str)
        raw_minimum = values.get("DATA_MIN_FREE_GIB", "").strip()
        raw_log_level = values.get("PIPELINE_LOG_LEVEL", "").strip()
        return cls(
            data_root=_parse_data_root(values.get("DATA_ROOT", "")),
            min_free_gib=_parse_min_free_gib(raw_minimum if raw_minimum else default_minimum),
            log_level=_parse_log_level(raw_log_level if raw_log_level else default_log_level),
            config_dir=directory.resolve(strict=True),
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PipelineConfig:
        """Load the default config files with optional environment overrides."""
        return cls.load(environ=environ)

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
        """Check free capacity and write access before a task writes data."""
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

        try:
            self.data_root.mkdir(parents=True, exist_ok=True)
            if not self.data_root.is_dir():
                raise OSError("path is not a directory")
            with tempfile.TemporaryFile(dir=self.data_root):
                pass
        except OSError as exc:
            raise ConfigError(f"DATA_ROOT is not writable: {self.data_root} ({exc})") from exc
        return self.data_root.resolve(strict=True)
