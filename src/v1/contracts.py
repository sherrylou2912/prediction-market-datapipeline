"""Row-level validation for the version 2 Bronze, Silver, and Gold contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa

SCHEMA_REGISTRY = json.loads(Path(__file__).with_name("schema_registry.json").read_text(encoding="utf-8"))
SCHEMA_VERSION: str = SCHEMA_REGISTRY["version"]

_ARROW_TYPES = {
    "str": pa.string(),
    "int": pa.int64(),
    "bool": pa.bool_(),
    "utc_datetime": pa.timestamp("us", tz="UTC"),
    "decimal": pa.decimal128(28, 10),
    "json": pa.string(),
}
_PROBABILITIES = {
    "price",
    "payout",
    "best_bid",
    "best_ask",
    "mid",
    "microprice",
    "last_trade_price",
    "label",
}
_NONNEGATIVE = {
    "record_index",
    "bronze_record_index",
    "sequence",
    "source_sequence",
    "quantity",
    "volume",
    "trade_count",
    "rolling_volume",
    "update_count",
    "book_age_ms",
    "receive_latency_ms",
    "bid_depth_top_n",
    "ask_depth_top_n",
    "depth_top_n",
    "spread",
}


class ContractError(ValueError):
    """A record does not satisfy its declared dataset contract."""


def get_contract(dataset: str) -> Mapping[str, Any]:
    try:
        return SCHEMA_REGISTRY["datasets"][dataset]
    except KeyError as exc:
        raise ContractError(f"Unknown dataset contract: {dataset}") from exc


def arrow_schema(dataset: str) -> pa.Schema:
    contract = get_contract(dataset)
    fields = []
    for name, spec in contract["fields"].items():
        nullable = spec.endswith("?")
        base_type = spec.rstrip("?")
        fields.append(pa.field(name, _ARROW_TYPES[base_type], nullable=nullable))
    return pa.schema(fields, metadata={b"schema_version": SCHEMA_VERSION.encode(), b"dataset": dataset.encode()})


def _parse_json(value: str, field: str) -> Any:
    def reject_constant(token: str) -> None:
        raise ValueError(f"Nonstandard JSON constant: {token}")

    try:
        return json.loads(value, parse_constant=reject_constant)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{field} must contain valid JSON text: {exc}") from exc


def validate_record(dataset: str, record: Mapping[str, Any]) -> None:
    contract = get_contract(dataset)
    fields = contract["fields"]
    missing = set(fields) - set(record)
    extra = set(record) - set(fields)
    if missing or extra:
        raise ContractError(f"{dataset} has missing fields {sorted(missing)} or unknown fields {sorted(extra)}")
    if record["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"{dataset}.schema_version must be {SCHEMA_VERSION}")

    for name, spec in fields.items():
        value = record[name]
        nullable = spec.endswith("?")
        base_type = spec.rstrip("?")
        if value is None:
            if nullable:
                continue
            raise ContractError(f"{dataset}.{name} is required")
        if base_type in {"str", "json"}:
            if not isinstance(value, str):
                raise ContractError(f"{dataset}.{name} must be a string")
            if base_type == "str" and not value.strip():
                raise ContractError(f"{dataset}.{name} must be nonempty")
            if base_type == "json":
                parsed = _parse_json(value, name)
                if name in {"source_manifest_ids", "bids", "asks"} and not isinstance(parsed, list):
                    raise ContractError(f"{dataset}.{name} must be a JSON array")
                if name == "source_manifest_ids" and not all(isinstance(item, str) and item for item in parsed):
                    raise ContractError(f"{dataset}.{name} must contain nonempty manifest IDs")
                if name == "source_manifest_ids" and not parsed:
                    raise ContractError(f"{dataset}.{name} must contain at least one manifest ID")
                if name == "features" and not isinstance(parsed, dict):
                    raise ContractError(f"{dataset}.{name} must be a JSON object")
        elif base_type == "int":
            if type(value) is not int:
                raise ContractError(f"{dataset}.{name} must be an integer")
        elif base_type == "bool":
            if type(value) is not bool:
                raise ContractError(f"{dataset}.{name} must be a boolean")
        elif base_type == "utc_datetime":
            if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
                raise ContractError(f"{dataset}.{name} must be a timezone-aware UTC datetime")
        elif base_type == "decimal":
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ContractError(f"{dataset}.{name} must be a finite Decimal")
            try:
                pa.scalar(value, type=_ARROW_TYPES["decimal"])
            except (pa.ArrowInvalid, pa.ArrowTypeError, ValueError) as exc:
                raise ContractError(f"{dataset}.{name} exceeds decimal128(28, 10)") from exc

        if name in _PROBABILITIES and not Decimal(0) <= value <= Decimal(1):
            raise ContractError(f"{dataset}.{name} must be between 0 and 1")
        if name in _NONNEGATIVE and value < 0:
            raise ContractError(f"{dataset}.{name} must be nonnegative")
        if name == "imbalance" and not Decimal(-1) <= value <= Decimal(1):
            raise ContractError(f"{dataset}.{name} must be between -1 and 1")
        if name == "second" and value.microsecond != 0:
            raise ContractError(f"{dataset}.second must align to a UTC second")
        if name == "day":
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("not an ISO date")
            except ValueError as exc:
                raise ContractError(f"{dataset}.day must be an ISO calendar date") from exc

    for name in contract["primary_key"]:
        if record[name] is None:
            raise ContractError(f"{dataset}.{name} is part of the primary key")
    if dataset == "gold.training_datasets" and record["max_feature_event_time"] > record["observation_time"]:
        raise ContractError("gold.training_datasets features must be known by observation_time")
