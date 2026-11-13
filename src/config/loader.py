"""Read raw pipeline configuration from JSON files and the environment."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from dotenv.parser import parse_stream
from dotenv.variables import parse_variables

from src.config.errors import ConfigError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent / "defaults"
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


def load_json_object(path: Path) -> dict[str, Any]:
    """Read a JSON object; its model validates the allowed fields and values."""

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key!r}")
            result[key] = value
        return result

    try:
        contents = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing configuration file: {path}") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigError(f"Cannot read configuration file {path}: {exc}") from exc
    if not isinstance(contents, dict):
        raise ConfigError(f"{path} must contain a JSON object.")
    return contents


def load_environment(
    environ: Mapping[str, str] | None,
    env_file: Path | None,
) -> dict[str, str]:
    """Read a local env file, then overlay the supplied process environment."""
    path = DEFAULT_ENV_FILE if environ is None and env_file is None else env_file
    values: dict[str, str] = {}
    supplied = dict(os.environ if environ is None else environ)
    if path is not None:
        try:
            seen: set[str] = set()
            with path.open(encoding="utf-8") as handle:
                for binding in parse_stream(handle):
                    if binding.error:
                        raise ConfigError(f"Cannot parse environment file {path} at line {binding.original.line}")
                    key, value = binding.key, binding.value
                    if key is None:
                        continue
                    if key in seen:
                        raise ConfigError(f"Duplicate environment key {key!r} in {path}")
                    seen.add(key)
                    if value is not None:
                        scope = {**values, **supplied}
                        values[key] = "".join(atom.resolve(scope) for atom in parse_variables(value))
        except FileNotFoundError as exc:
            if env_file is not None:
                raise ConfigError(f"Environment file does not exist: {path}") from exc
            try:
                path.lstat()
            except FileNotFoundError:
                pass  # The optional default file is truly absent.
            except OSError as stat_exc:
                raise ConfigError(f"Cannot inspect environment file {path}: {stat_exc}") from stat_exc
            else:
                raise ConfigError(f"Cannot read environment file {path}: {exc}") from exc
        except (OSError, UnicodeError) as exc:
            raise ConfigError(f"Cannot read environment file {path}: {exc}") from exc
    values.update(supplied)
    return values
