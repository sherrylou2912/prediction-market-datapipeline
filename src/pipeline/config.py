"""Readable, non-secret configuration loaded from JSON and environment sources."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from src.pipeline.config_validation import (
    ConfigError,
    parse_data_root,
    parse_log_level,
    parse_min_free_gib,
    validate_data_root,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "config"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def _read_json_settings(path: Path, expected_key: str, expected_type: type) -> dict[str, Any]:
    try:
        contents = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing configuration file: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read configuration file {path}: {exc}") from exc
    if not isinstance(contents, dict) or set(contents) != {expected_key}:
        raise ConfigError(f"{path} must contain only the {expected_key!r} setting.")
    value = contents[expected_key]
    if type(value) is not expected_type:
        raise ConfigError(f"{path}:{expected_key} must be {expected_type.__name__}.")
    return contents


def _read_environment(
    environ: Mapping[str, str] | None,
    env_file: Path | None,
) -> dict[str, str]:
    path = DEFAULT_ENV_FILE if environ is None and env_file is None else env_file
    values: dict[str, str] = {}
    if path is not None:
        if env_file is not None and not path.is_file():
            raise ConfigError(f"Environment file does not exist: {path}")
        if path.is_file():
            try:
                values.update({key: value for key, value in dotenv_values(path).items() if value is not None})
            except (OSError, UnicodeError) as exc:
                raise ConfigError(f"Cannot read environment file {path}: {exc}") from exc
    values.update(os.environ if environ is None else environ)
    return values


@dataclass(frozen=True)
class PipelineConfig:
    data_root: Path
    min_free_gib: int
    log_level: str
    config_dir: Path

    @classmethod
    def load(
        cls,
        *,
        config_dir: Path | None = None,
        environ: Mapping[str, str] | None = None,
        env_file: Path | None = None,
    ) -> PipelineConfig:
        values = _read_environment(environ, env_file)
        raw_config_dir = values.get("PIPELINE_CONFIG_DIR", "").strip()
        directory = config_dir or (Path(raw_config_dir).expanduser() if raw_config_dir else DEFAULT_CONFIG_DIR)
        if not directory.is_absolute():
            raise ConfigError(f"PIPELINE_CONFIG_DIR must be an absolute path: {directory}")
        storage = _read_json_settings(directory / "storage.json", "min_free_gib", int)
        runtime = _read_json_settings(directory / "runtime.json", "log_level", str)

        raw_minimum = values.get("DATA_MIN_FREE_GIB", "").strip()
        raw_level = values.get("PIPELINE_LOG_LEVEL", "").strip()
        return cls(
            data_root=parse_data_root(values.get("DATA_ROOT", "")),
            min_free_gib=parse_min_free_gib(raw_minimum if raw_minimum else storage["min_free_gib"]),
            log_level=parse_log_level(raw_level if raw_level else runtime["log_level"]),
            config_dir=directory.resolve(strict=True),
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> PipelineConfig:
        """Keep the original PR 1 API while loading the split configuration files."""
        return cls.load(environ=environ)

    def validate_startup(self) -> Path:
        return validate_data_root(self.data_root, self.min_free_gib)
