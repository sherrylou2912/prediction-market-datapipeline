"""Load and execute the versioned, declarative row contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pyarrow as pa


class ContractError(ValueError):
    """A record does not satisfy its declared dataset contract."""


_ARROW_TYPES = {
    "str": pa.string(),
    "int": pa.int64(),
    "bool": pa.bool_(),
    "utc_datetime": pa.timestamp("us", tz="UTC"),
    "decimal": pa.decimal128(28, 10),
    "json": pa.string(),
    "binary": pa.binary(),
}
# Rule keys that name fields; shared with the schema documentation generator.
RULE_FIELDS = {
    "range": ("field",),
    "enum": ("field",),
    "compare": ("left", "right"),
    "difference": ("result", "left", "right"),
    "rounded_mean": ("result", "left", "right"),
    "zero_coverage_null": ("when", "field"),
    "zero_pair_null": ("left", "right", "field"),
    "exactly_one_present": ("left", "right"),
    "alignment": ("field",),
    "iso_date": ("field",),
    "string_array": ("field",),
    "book_levels": ("field",),
    "json_object": ("field",),
    "unique_json_keys": ("field",),
    "level_map": ("field",),
    "conditional_null": ("when", "field"),
    "conditional_value": ("when", "field"),
    "conditional_positive": ("when", "field"),
    "conditional_reason": ("when", "field", "reason"),
    "requires_present": ("field", "required"),
    "window_end": ("field", "start"),
    "day_start": ("field", "day"),
    "version": ("field",),
}
_RULE_KEYS = {
    "range": ({"type", "field"}, {"min", "max"}),
    "enum": ({"type", "field", "values"}, set()),
    "compare": ({"type", "left", "op", "right"}, set()),
    "difference": ({"type", "result", "left", "right"}, set()),
    "rounded_mean": ({"type", "result", "left", "right", "scale"}, set()),
    "zero_coverage_null": ({"type", "when", "field"}, set()),
    "zero_pair_null": ({"type", "left", "right", "field"}, set()),
    "exactly_one_present": ({"type", "left", "right"}, set()),
    "alignment": ({"type", "field", "unit"}, set()),
    "iso_date": ({"type", "field"}, set()),
    "string_array": ({"type", "field", "nonempty"}, set()),
    "book_levels": ({"type", "field"}, set()),
    "json_object": ({"type", "field"}, set()),
    "unique_json_keys": ({"type", "field"}, set()),
    "level_map": ({"type", "field", "max"}, set()),
    "conditional_null": ({"type", "when", "equals", "field"}, set()),
    "conditional_value": ({"type", "when", "equals", "field", "value"}, {"allow_null"}),
    "conditional_positive": ({"type", "when", "equals", "field"}, set()),
    "conditional_reason": ({"type", "when", "equals", "field", "reason"}, set()),
    "requires_present": ({"type", "field", "required"}, set()),
    "window_end": ({"type", "field", "start", "unit"}, set()),
    "day_start": ({"type", "field", "day"}, set()),
    "version": ({"type", "field"}, set()),
}


def _number(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise ValueError("must be a decimal number or string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("must be finite")
    return number


def validate_registry(registry: Any) -> None:
    """Reject malformed registry declarations before accepting any records."""
    if not isinstance(registry, dict) or set(registry) != {"version", "version_field", "datasets"}:
        raise ValueError("registry must contain version, version_field and datasets")
    if not isinstance(registry["version"], str) or not registry["version"].strip():
        raise ValueError("registry version must be nonempty")
    version_field = registry["version_field"]
    if not isinstance(version_field, str) or not version_field.strip():
        raise ValueError("registry version_field must be nonempty")
    datasets = registry["datasets"]
    if not isinstance(datasets, dict) or not datasets:
        raise ValueError("registry datasets must be nonempty")
    for dataset, contract in datasets.items():
        if not isinstance(dataset, str) or not dataset.strip() or not isinstance(contract, dict):
            raise ValueError("invalid dataset")
        if set(contract) != {"fields", "primary_key", "rules"}:
            raise ValueError(f"{dataset}: invalid contract keys")
        fields, pk, rules = contract["fields"], contract["primary_key"], contract["rules"]
        if (
            not isinstance(fields, dict)
            or not fields
            or not isinstance(pk, list)
            or not pk
            or not isinstance(rules, list)
        ):
            raise ValueError(f"{dataset}: invalid fields, primary key or rules")
        for name, spec in fields.items():
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(spec, dict)
                or set(spec) != {"type", "description"}
            ):
                raise ValueError(f"{dataset}: invalid field declaration")
            kind, description = spec["type"], spec["description"]
            if not isinstance(kind, str) or kind.removesuffix("?") not in _ARROW_TYPES or kind.count("?") > 1:
                raise ValueError(f"{dataset}.{name}: unknown type")
            if not isinstance(description, str) or not description.strip():
                raise ValueError(f"{dataset}.{name}: description required")
        if (
            any(not isinstance(k, str) for k in pk)
            or len(pk) != len(set(pk))
            or any(k not in fields or fields[k]["type"].endswith("?") for k in pk)
        ):
            raise ValueError(f"{dataset}: invalid primary key")
        if version_field not in fields or fields[version_field]["type"] != "str":
            raise ValueError(f"{dataset}: version field must be a required string")
        version_rules = [rule for rule in rules if isinstance(rule, dict) and rule.get("type") == "version"]
        if version_rules != [{"type": "version", "field": version_field}]:
            raise ValueError(f"{dataset}: exactly one version rule must target the declared version field")
        for rule in rules:
            if not isinstance(rule, dict) or not isinstance(rule.get("type"), str) or rule["type"] not in RULE_FIELDS:
                raise ValueError(f"{dataset}: unknown rule type")
            kind = rule["type"]
            required, optional = _RULE_KEYS[kind]
            if not required <= rule.keys() or rule.keys() - required - optional:
                raise ValueError(f"{dataset}: malformed {kind} rule")
            if any(not isinstance(rule[key], str) or rule[key] not in fields for key in RULE_FIELDS[kind]):
                raise ValueError(f"{dataset}: rule references unknown field")
            types = [fields[rule[k]]["type"].rstrip("?") for k in RULE_FIELDS[kind]]
            allowed = {
                "range": {"int", "decimal"},
                "enum": {"str"},
                "alignment": {"utc_datetime"},
                "iso_date": {"str"},
                "string_array": {"json"},
                "book_levels": {"json"},
                "json_object": {"json"},
                "unique_json_keys": {"json"},
                "level_map": {"json"},
                "version": {"str"},
            }
            if kind in allowed and types[0] not in allowed[kind]:
                raise ValueError(f"{dataset}: incompatible {kind} field")
            if kind in {"compare", "difference"} and (
                len(set(types)) != 1
                or types[0] not in {"utc_datetime", "int", "decimal"}
                or (kind == "difference" and types[0] not in {"int", "decimal"})
            ):
                raise ValueError(f"{dataset}: incompatible {kind} fields")
            if kind == "rounded_mean" and (
                types != ["decimal", "decimal", "decimal"]
                or type(rule["scale"]) is not int
                or not 0 <= rule["scale"] <= 28
            ):
                raise ValueError(f"{dataset}: incompatible rounded_mean fields or scale")
            if kind == "zero_coverage_null" and (
                types[0] not in {"int", "decimal"} or not fields[rule["field"]]["type"].endswith("?")
            ):
                raise ValueError(f"{dataset}: invalid zero_coverage_null rule")
            if kind == "zero_pair_null" and (
                types[0] not in {"int", "decimal"}
                or types[1] not in {"int", "decimal"}
                or not fields[rule["field"]]["type"].endswith("?")
            ):
                raise ValueError(f"{dataset}: invalid zero_pair_null rule")
            if kind == "exactly_one_present" and (
                rule["left"] == rule["right"]
                or any(not fields[rule[key]]["type"].endswith("?") for key in ("left", "right"))
            ):
                raise ValueError(f"{dataset}: invalid exactly_one_present rule")
            if kind == "window_end" and types != ["utc_datetime", "utc_datetime"]:
                raise ValueError(f"{dataset}: incompatible window_end fields")
            if kind == "day_start" and (
                types != ["utc_datetime", "str"] or {"type": "iso_date", "field": rule["day"]} not in rules
            ):
                raise ValueError(f"{dataset}: day_start needs a UTC datetime and an iso_date day field")
            try:
                if kind == "range":
                    if not ({"min", "max"} & rule.keys()):
                        raise ValueError("range has no bound")
                    bounds = [_number(rule[k]) for k in ("min", "max") if k in rule]
                    if len(bounds) == 2 and bounds[0] > bounds[1]:
                        raise ValueError("inverted range")
                if kind == "level_map" and rule["max"] is not None:
                    if _number(rule["max"]) < 0:
                        raise ValueError("negative maximum")
                if kind == "conditional_value":
                    _number(rule["value"])
            except (InvalidOperation, ValueError, TypeError) as exc:
                raise ValueError(f"{dataset}: invalid {kind} rule") from exc
            if kind == "enum" and (
                not isinstance(rule["values"], list)
                or not rule["values"]
                or any(not isinstance(v, str) or not v.strip() for v in rule["values"])
            ):
                raise ValueError(f"{dataset}: invalid enum")
            if kind == "compare" and rule["op"] not in {"<", "<="}:
                raise ValueError(f"{dataset}: invalid comparison")
            if kind == "alignment" and rule["unit"] not in {"second", "minute"}:
                raise ValueError(f"{dataset}: invalid alignment")
            if kind == "window_end" and rule["unit"] not in {"second", "minute"}:
                raise ValueError(f"{dataset}: invalid window_end unit")
            if kind == "conditional_value" and "allow_null" in rule and type(rule["allow_null"]) is not bool:
                raise ValueError(f"{dataset}: invalid allow_null")
            if kind == "string_array" and type(rule["nonempty"]) is not bool:
                raise ValueError(f"{dataset}: invalid string_array")
            if kind.startswith("conditional_") and (
                not (
                    types[0] == "str"
                    and isinstance(rule["equals"], str)
                    and bool(rule["equals"].strip())
                    or types[0] == "int"
                    and type(rule["equals"]) is int
                )
                or (kind in {"conditional_value", "conditional_positive"} and types[1] not in {"int", "decimal"})
                or (kind == "conditional_reason" and types[2] != "str")
            ):
                raise ValueError(f"{dataset}: invalid conditional rule")


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, item in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = item
    return result


def _reject_json_constant(token: str) -> None:
    raise ValueError(f"Nonstandard JSON constant: {token}")


def load_registry(path: Path) -> dict[str, Any]:
    """Read and validate a registry without silently overwriting duplicate keys."""
    registry = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_object,
        parse_constant=_reject_json_constant,
    )
    validate_registry(registry)
    return registry


_registry = load_registry(Path(__file__).with_name("schema_registry.json"))
SCHEMA_REGISTRY = _freeze(_registry)
del _registry
SCHEMA_VERSION: str = SCHEMA_REGISTRY["version"]


def get_contract(dataset: str) -> Mapping[str, Any]:
    try:
        return SCHEMA_REGISTRY["datasets"][dataset]
    except KeyError as exc:
        raise ContractError(f"Unknown dataset contract: {dataset}") from exc


def arrow_schema(dataset: str) -> pa.Schema:
    fields = []
    for name, spec in get_contract(dataset)["fields"].items():
        kind = spec["type"]
        fields.append(pa.field(name, _ARROW_TYPES[kind.rstrip("?")], nullable=kind.endswith("?")))
    return pa.schema(fields, metadata={b"schema_version": SCHEMA_VERSION.encode(), b"dataset": dataset.encode()})


def _parse_json(value: str, field: str, *, unique_keys: bool) -> Any:
    try:
        options = {"object_pairs_hook": _unique_json_object} if unique_keys else {}
        return json.loads(value, parse_float=Decimal, parse_constant=_reject_json_constant, **options)
    except (TypeError, ValueError, InvalidOperation, RecursionError) as exc:
        raise ContractError(f"{field} must contain valid JSON text: {exc}") from exc


def parse_json_strict(value: str, field: str) -> Any:
    """Parse JSON without accepting duplicate object keys or nonstandard constants."""
    return _parse_json(value, field, unique_keys=True)


def _check_rule(dataset: str, rule: Mapping[str, Any], row: Mapping[str, Any], parsed: Mapping[str, Any]) -> None:
    kind = rule["type"]
    field = rule.get("field")
    value = row[field] if field else None
    prefix = f"{dataset}.{field}"
    if kind == "version":
        if value != SCHEMA_VERSION:
            raise ContractError(f"{prefix} must be {SCHEMA_VERSION}")
    elif kind == "conditional_null":
        if row[rule["when"]] == rule["equals"] and value is not None:
            raise ContractError(f"{prefix} must be null when {rule['when']} is {rule['equals']}")
    elif kind == "conditional_value":
        if (
            row[rule["when"]] == rule["equals"]
            and not (value is None and rule.get("allow_null", False))
            and value != _number(rule["value"])
        ):
            raise ContractError(f"{prefix} must be {rule['value']} when {rule['when']} is {rule['equals']}")
    elif kind == "requires_present":
        if value is not None and row[rule["required"]] is None:
            raise ContractError(f"{prefix} requires {rule['required']} to be present")
    elif kind == "window_end":
        start = row[rule["start"]]
        if value is not None and start is not None:
            duration = timedelta(seconds=1) if rule["unit"] == "second" else timedelta(minutes=1)
            try:
                end = start + duration
            except OverflowError as exc:
                raise ContractError(f"{dataset}.{rule['start']} cannot represent the window end") from exc
            if value < end:
                raise ContractError(f"{prefix} must be at or after the {rule['unit']} window end")
    elif kind == "day_start":
        day = row[rule["day"]]
        if value is not None and day is not None:
            try:
                start = datetime.combine(date.fromisoformat(day), time(), tzinfo=timezone.utc)
            except (TypeError, ValueError) as exc:
                raise ContractError(f"{dataset}.{rule['day']} must be an ISO calendar date") from exc
            if value < start:
                raise ContractError(f"{prefix} must not be before the start of UTC day {day} ({rule['day']})")
    elif kind == "conditional_positive":
        if row[rule["when"]] == rule["equals"] and value is not None and value <= 0:
            raise ContractError(f"{prefix} must be positive when {rule['when']} is {rule['equals']}")
    elif kind == "conditional_reason":
        if row[rule["when"]] == rule["equals"] and value is None and row[rule["reason"]] is None:
            raise ContractError(f"{dataset}.{rule['reason']} is required when {field} is unavailable")
    elif kind == "compare":
        left, right = row[rule["left"]], row[rule["right"]]
        if left is not None and right is not None and not (left <= right if rule["op"] == "<=" else left < right):
            raise ContractError(f"{dataset}: {rule['left']} must be {rule['op']} {rule['right']}")
    elif kind == "difference":
        result, left, right = (row[rule[k]] for k in ("result", "left", "right"))
        # Fraction converts Decimal and int exactly, without inheriting the
        # caller's Decimal precision, rounding, or signal traps.
        if all(v is not None for v in (result, left, right)) and Fraction(result) != Fraction(left) - Fraction(right):
            raise ContractError(f"{dataset}.{rule['result']} must equal {rule['left']} - {rule['right']}")
    elif kind == "rounded_mean":
        result, left, right = (row[rule[k]] for k in ("result", "left", "right"))
        if all(v is not None for v in (result, left, right)):
            factor = 10 ** rule["scale"]
            if Fraction(result) * factor != round((Fraction(left) + Fraction(right)) * factor / 2):
                raise ContractError(f"{dataset}.{rule['result']} must be the half-even rounded mean of its inputs")
    elif kind == "zero_coverage_null":
        if row[rule["when"]] == 0 and value is not None:
            raise ContractError(f"{prefix} must be null when {rule['when']} is zero")
    elif kind == "zero_pair_null":
        if row[rule["left"]] == 0 and row[rule["right"]] == 0 and value is not None:
            raise ContractError(f"{prefix} must be null when both {rule['left']} and {rule['right']} are zero")
    elif kind == "exactly_one_present":
        if (row[rule["left"]] is None) == (row[rule["right"]] is None):
            raise ContractError(f"{dataset}: exactly one of {rule['left']} and {rule['right']} must be present")
    elif value is None:
        return
    elif kind == "range":
        low, high = rule.get("min"), rule.get("max")
        if low is not None and value < _number(low) or high is not None and value > _number(high):
            raise ContractError(
                f"{prefix} must be between {low} and {high}" if high is not None else f"{prefix} must be nonnegative"
            )
    elif kind == "enum" and value not in rule["values"]:
        raise ContractError(f"{prefix} must be one of {', '.join(rule['values'])}")
    elif kind == "alignment" and (value.microsecond != 0 or rule["unit"] == "minute" and value.second != 0):
        raise ContractError(f"{prefix} must align to a UTC {rule['unit']}")
    elif kind == "iso_date":
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("not an ISO date")
        except ValueError as exc:
            raise ContractError(f"{prefix} must be an ISO calendar date") from exc
    elif kind == "string_array":
        items = parsed[field]
        if (
            not isinstance(items, list)
            or any(not isinstance(i, str) or not i.strip() for i in items)
            or rule["nonempty"]
            and not items
        ):
            raise ContractError(f"{prefix} must contain at least one nonempty manifest ID in a JSON array")
    elif kind == "json_object" and not isinstance(parsed[field], dict):
        raise ContractError(f"{prefix} must be a JSON object")
    elif kind == "unique_json_keys":
        parse_json_strict(value, prefix)
    elif kind == "book_levels":
        levels = parsed[field]
        try:
            if not isinstance(levels, list):
                raise ValueError("expected array")
            for level in levels:
                if (
                    not isinstance(level, dict)
                    or set(level) != {"price", "quantity"}
                    or not 0 <= _number(level["price"]) <= 1
                    or _number(level["quantity"]) < 0
                ):
                    raise ValueError("invalid level")
                for name in ("price", "quantity"):
                    pa.scalar(_number(level[name]), type=_ARROW_TYPES["decimal"])
        except (ValueError, TypeError, InvalidOperation, pa.ArrowInvalid, pa.ArrowTypeError, OverflowError) as exc:
            raise ContractError(f"{prefix} must be an array of valid price/quantity levels") from exc
    elif kind == "level_map":
        levels = parsed[field]
        try:
            if not isinstance(levels, dict):
                raise ValueError("expected object")
            for index, amount in levels.items():
                if (
                    not index.isascii()
                    or not index.isdigit()
                    or index.startswith("0")
                    or not isinstance(amount, str)
                    or _number(amount) < 0
                    or rule["max"] is not None
                    and _number(amount) > _number(rule["max"])
                ):
                    raise ValueError("invalid level")
                pa.scalar(_number(amount), type=_ARROW_TYPES["decimal"])
        except (ValueError, TypeError, InvalidOperation, pa.ArrowInvalid, pa.ArrowTypeError, OverflowError) as exc:
            raise ContractError(f"{prefix} must be an object of positive level keys and valid decimal strings") from exc


def validate_record(dataset: str, record: Mapping[str, Any]) -> None:
    contract = get_contract(dataset)
    fields = contract["fields"]
    if any(not isinstance(key, str) for key in record):
        raise ContractError(f"{dataset} field names must be strings")
    missing, extra = set(fields) - set(record), set(record) - set(fields)
    if missing or extra:
        raise ContractError(f"{dataset} has missing fields {sorted(missing)} or unknown fields {sorted(extra)}")
    parsed = {}
    for name, spec in fields.items():
        value, kind = record[name], spec["type"]
        if value is None:
            if kind.endswith("?"):
                continue
            raise ContractError(f"{dataset}.{name} is required")
        kind = kind.rstrip("?")
        if kind in {"str", "json"}:
            if not isinstance(value, str):
                raise ContractError(f"{dataset}.{name} must be a string")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ContractError(f"{dataset}.{name} must be UTF-8 encodable for Arrow storage") from exc
            if kind == "str" and not value.strip():
                raise ContractError(f"{dataset}.{name} must be nonempty")
            if kind == "json":
                parsed[name] = _parse_json(value, name, unique_keys=False)
        elif kind == "int":
            if type(value) is not int:
                raise ContractError(f"{dataset}.{name} must be an integer")
            if not -(2**63) <= value < 2**63:
                raise ContractError(f"{dataset}.{name} exceeds Arrow int64")
        elif kind == "bool" and type(value) is not bool:
            raise ContractError(f"{dataset}.{name} must be a boolean")
        elif kind == "binary" and type(value) is not bytes:
            raise ContractError(f"{dataset}.{name} must be bytes")
        elif kind == "utc_datetime" and (not isinstance(value, datetime) or value.tzinfo is not timezone.utc):
            raise ContractError(f"{dataset}.{name} must be a timezone-aware UTC datetime using timezone.utc")
        elif kind == "decimal":
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ContractError(f"{dataset}.{name} must be a finite Decimal")
            try:
                pa.scalar(value, type=_ARROW_TYPES["decimal"])
            except (pa.ArrowInvalid, pa.ArrowTypeError, ValueError) as exc:
                raise ContractError(f"{dataset}.{name} exceeds decimal128(28, 10)") from exc
    for rule in contract["rules"]:
        _check_rule(dataset, rule, record, parsed)
