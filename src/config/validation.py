"""Reusable configuration value constraints and public error conversion."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, ValidationError
from pydantic_core import PydanticCustomError

from src.config.errors import ConfigError


def _absolute_path(value: Any) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise PydanticCustomError("config_absolute_path", "must be an absolute Path")
    if "\x00" in str(value):
        raise PydanticCustomError("config_path_nul", "must not contain NUL characters")
    return value


def _nonnegative_integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise PydanticCustomError("config_nonnegative_integer", "must be a nonnegative integer")
    return value


def _log_level(value: Any) -> str:
    if not isinstance(value, str) or value.strip().upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise PydanticCustomError("config_log_level", "must be DEBUG, INFO, WARNING, ERROR, or CRITICAL")
    return value.strip().upper()


AbsolutePath = Annotated[Path, BeforeValidator(_absolute_path)]
NonnegativeInteger = Annotated[int, BeforeValidator(_nonnegative_integer)]
LogLevel = Annotated[str, AfterValidator(_log_level)]

_SAFE_ERROR_MESSAGES = {
    "config_absolute_path": "must be an absolute Path",
    "config_path_nul": "must not contain NUL characters",
    "config_nonnegative_integer": "must be a nonnegative integer",
    "config_log_level": "must be DEBUG, INFO, WARNING, ERROR, or CRITICAL",
    "extra_forbidden": "unknown configuration field",
    "missing": "is required",
    "model_type": "must be a valid dictionary or model",
    "model_attributes_type": "must be a valid dictionary or model",
    "int_type": "must be an integer",
    "string_type": "must be a string",
    "union_tag_invalid": "has an invalid type tag",
    "union_tag_not_found": "is missing a type tag",
    "json_invalid": "must be valid JSON",
}


class _SanitizedConfigError(ConfigError):
    """A message assembled solely from declared fields and fixed text."""


def config_error(exc: ValidationError, model: type[BaseModel]) -> ConfigError:
    """Translate validation errors without exposing input values or secrets."""
    names = getattr(model, "_error_names", {})
    messages = []
    for error in exc.errors(include_input=False, include_url=False):
        # Nested locations may contain mapping keys supplied by the caller.
        # Only a top-level field declared on this model is safe to report.
        location = error["loc"]
        field = location[0] if location and location[0] in model.model_fields else ""
        label = names.get(field, field)
        # Pydantic may wrap our own already-sanitized ConfigError when one
        # ConfigModel validates another or model_validate invokes __init__.
        wrapped = error.get("ctx", {}).get("error")
        if type(wrapped) is _SanitizedConfigError:
            messages.append(f"{label} has an invalid value" if label else str(wrapped))
            continue
        # Pydantic puts unknown keys from the input in loc. They can themselves
        # contain sensitive text and must not be echoed in an error or traceback.
        if error["type"] == "extra_forbidden":
            messages.append("unknown configuration field")
            continue
        # Even Pydantic's built-in messages can contain input (e.g. union tags).
        # Never interpolate its msg or context into the public exception.
        message = _SAFE_ERROR_MESSAGES.get(error["type"], "has an invalid value")
        messages.append(f"{label} {message}".strip())
    return _SanitizedConfigError("; ".join(messages))


class ConfigModel(BaseModel):
    """Immutable, strict configuration model with a stable public exception."""

    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    def __init__(self, **data: Any) -> None:
        error: ConfigError | None = None
        try:
            super().__init__(**data)
        except ValidationError as exc:
            error = config_error(exc, type(self))
        # Raise outside the handler so Python does not retain the original
        # ValidationError (which contains input values) in the exception chain.
        if error is not None:
            raise error

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> ConfigModel:
        error: ConfigError | None = None
        try:
            return super().model_validate(obj, **kwargs)
        except ValidationError as exc:
            error = config_error(exc, cls)
        raise error

    @classmethod
    def model_validate_json(cls, json_data: str | bytes | bytearray, **kwargs: Any) -> ConfigModel:
        error: ConfigError | None = None
        try:
            return super().model_validate_json(json_data, **kwargs)
        except ValidationError as exc:
            error = config_error(exc, cls)
        raise error

    @classmethod
    def model_validate_strings(cls, obj: Any, **kwargs: Any) -> ConfigModel:
        error: ConfigError | None = None
        try:
            return super().model_validate_strings(obj, **kwargs)
        except ValidationError as exc:
            error = config_error(exc, cls)
        raise error
