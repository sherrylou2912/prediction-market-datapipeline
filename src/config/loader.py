"""Read raw pipeline configuration from JSON files and the environment."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

from src.config.errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "defaults"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def load_json_setting(path: Path, expected_key: str, expected_type: type) -> Any:
    """Read a one-setting JSON file and reject ambiguous contents."""
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
    return value


def load_environment(
    environ: Mapping[str, str] | None,
    env_file: Path | None,
) -> dict[str, str]:
    """Read a local env file, then overlay the supplied process environment."""
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
