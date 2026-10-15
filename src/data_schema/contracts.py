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
# PR 1 range rules are dataset-scoped because a field name can have different
# meanings across contracts. A future schema revision should declare these
# constraints with the fields in the registry instead of maintaining code lists.
_PROBABILITIES = {
    ("silver.market_states", "best_bid"),
    ("silver.market_states", "best_ask"),
    ("silver.trades", "price"),
    ("silver.book_deltas", "price"),
    ("silver.settlements", "payout"),
    ("gold.market_1s", "best_bid"),
    ("gold.market_1s", "best_ask"),
    ("gold.market_1s", "mid"),
    ("gold.market_1s", "microprice"),
    ("gold.market_1s", "last_trade_price"),
    ("gold.training_datasets", "label"),
}
_NONNEGATIVE = {
    ("bronze.raw", "record_index"),
    ("bronze.raw", "sequence"),
    ("silver.events", "bronze_record_index"),
    ("silver.markets", "bronze_record_index"),
    ("silver.outcomes", "bronze_record_index"),
    ("silver.market_states", "bronze_record_index"),
    ("silver.trades", "bronze_record_index"),
    ("silver.trades", "quantity"),
    ("silver.book_snapshots", "bronze_record_index"),
    ("silver.book_snapshots", "source_sequence"),
    ("silver.book_deltas", "bronze_record_index"),
    ("silver.book_deltas", "source_sequence"),
    ("silver.book_deltas", "quantity"),
    ("silver.settlements", "bronze_record_index"),
    ("gold.market_daily", "volume"),
    ("gold.market_daily", "trade_count"),
    ("gold.market_1s", "spread"),
    ("gold.market_1s", "bid_depth_top_n"),
    ("gold.market_1s", "ask_depth_top_n"),
    ("gold.market_1s", "rolling_volume"),
    ("gold.market_1s", "update_count"),
    ("gold.market_1s", "book_age_ms"),
    ("gold.market_1s", "receive_latency_ms"),
    ("gold.liquidity_features", "spread"),
    ("gold.liquidity_features", "depth_top_n"),
}
_IMBALANCE = {("gold.market_1s", "imbalance"), ("gold.liquidity_features", "imbalance")}


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

        if (dataset, name) in _PROBABILITIES and not Decimal(0) <= value <= Decimal(1):
            raise ContractError(f"{dataset}.{name} must be between 0 and 1")
        if (dataset, name) in _NONNEGATIVE and value < 0:
            raise ContractError(f"{dataset}.{name} must be nonnegative")
        if (dataset, name) in _IMBALANCE and not Decimal(-1) <= value <= Decimal(1):
            raise ContractError(f"{dataset}.{name} must be between -1 and 1")
        if (dataset, name) == ("gold.market_1s", "second") and value.microsecond != 0:
            raise ContractError(f"{dataset}.second must align to a UTC second")
        if (dataset, name) == ("gold.market_daily", "day"):
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
