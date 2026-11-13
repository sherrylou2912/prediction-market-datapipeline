"""Contract examples exercise row rules and invalid registry declarations."""

import copy
import json
import os
import runpy
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal, Inexact, Rounded, localcontext
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pytest

from src.data_schema.contracts import (
    SCHEMA_REGISTRY,
    SCHEMA_VERSION,
    ContractError,
    arrow_schema,
    get_contract,
    parse_json_strict,
    validate_record,
    validate_registry,
)

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def row_for(dataset):
    defaults = {
        "str": "example",
        "int": 1,
        "bool": False,
        "utc_datetime": NOW,
        "decimal": Decimal("0.5"),
        "json": "{}",
        "binary": b"example",
    }
    row = {
        name: None if spec["type"].endswith("?") else defaults[spec["type"]]
        for name, spec in get_contract(dataset)["fields"].items()
    }
    row["schema_version"] = SCHEMA_VERSION
    if dataset == "bronze.raw":
        row["raw_payload"] = "{}"
    if "source_manifest_ids" in row:
        row["source_manifest_ids"] = '["manifest"]'
    if "status" in row:
        row["status"] = "open"
    if "side" in row:
        row["side"] = "bid"
    if "bids" in row:
        row["bids"] = '[{"price":"0.4","quantity":"10"}]'
        row["asks"] = '[{"price":0.6,"quantity":2}]'
    if "day" in row:
        row["day"] = "2024-01-01"
    if "trade_data_status" in row:
        row["trade_data_status"] = "missing"
    if dataset == "gold.market_1s":
        row["as_of"] = NOW + timedelta(seconds=1)
    if dataset == "gold.market_1m":
        row["as_of"] = NOW + timedelta(minutes=1)
    return row


def test_registry_and_contract_are_deeply_immutable():
    with pytest.raises(TypeError):
        SCHEMA_REGISTRY["version"] = "changed"
    contract = get_contract("silver.market_states")
    with pytest.raises(TypeError):
        contract["fields"]["best_bid"]["type"] = "str"
    with pytest.raises(AttributeError):
        contract["rules"].append({})
    validate_record("silver.market_states", row_for("silver.market_states"))


@pytest.mark.parametrize("bad_zone", [ZoneInfo("UTC"), ZoneInfo("Europe/London")])
def test_only_timezone_utc_accepted(bad_zone):
    row = row_for("bronze.raw")
    validate_record("bronze.raw", row)
    row["received_at"] = NOW.replace(tzinfo=bad_zone)
    with pytest.raises(ContractError, match="timezone.utc"):
        validate_record("bronze.raw", row)


def test_zero_offset_timezone_factory_returns_utc_singleton():
    # CPython canonicalizes timezone(timedelta(0)) to timezone.utc.
    assert timezone(timedelta(0)) is timezone.utc


@pytest.mark.parametrize("contents", [b"", b"\xff\x00", b"{bad json", b"column,value\n1,2\n"])
def test_bronze_preserves_raw_bytes_without_parsing(contents):
    row = row_for("bronze.raw")
    row.update(venue=None, api_version=None, received_at=None, ingested_at=None, raw_payload=None, raw_bytes=contents)
    validate_record("bronze.raw", row)
    table = pa.Table.from_pylist([row], schema=arrow_schema("bronze.raw"))
    assert table.column("raw_bytes").to_pylist() == [contents]


def test_bronze_requires_one_raw_representation():
    row = row_for("bronze.raw")
    validate_record("bronze.raw", row)
    for payload, binary in ((None, None), ("{}", b"{}")):
        with pytest.raises(ContractError, match="exactly one"):
            validate_record("bronze.raw", {**row, "raw_payload": payload, "raw_bytes": binary})
    with pytest.raises(ContractError, match="must be bytes"):
        validate_record("bronze.raw", {**row, "raw_payload": None, "raw_bytes": bytearray(b"data")})

    class BytesSubclass(bytes):
        pass

    with pytest.raises(ContractError, match="must be bytes"):
        validate_record("bronze.raw", {**row, "raw_payload": None, "raw_bytes": BytesSubclass(b"data")})


def test_bronze_retains_reversed_times_for_later_review():
    row = row_for("bronze.raw")
    row.update(received_at=NOW, ingested_at=NOW - timedelta(seconds=1))
    validate_record("bronze.raw", row)
    assert row["ingested_at"] < row["received_at"]


def test_market_crossed_quotes_and_optional_comparison():
    for dataset in ("silver.market_states", "gold.market_1s"):
        row = row_for(dataset)
        row.update(best_bid=Decimal("0.4"), best_ask=Decimal("0.6"))
        if "spread" in row:
            row["spread"] = Decimal("0.2")
        validate_record(dataset, row)
        with pytest.raises(ContractError, match="best_bid"):
            validate_record(dataset, {**row, "best_bid": Decimal("0.8")})
        validate_record(dataset, {**row, "best_bid": None, **({"spread": None} if "spread" in row else {})})
        if "spread" in row:
            with pytest.raises(ContractError, match="spread"):
                validate_record(dataset, {**row, "spread": Decimal("0.1")})


def test_difference_is_exact_independent_of_decimal_context():
    row = row_for("gold.market_1s")
    row.update(best_bid=Decimal("0.1234567890"), best_ask=Decimal("0.8765432109"))
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        validate_record("gold.market_1s", {**row, "spread": Decimal("0.7530864219")})
        with pytest.raises(ContractError, match="spread"):
            validate_record("gold.market_1s", {**row, "spread": Decimal("0.75")})


def test_mid_requires_quotes_and_rounds_half_even_independent_of_context():
    row = row_for("gold.market_1s")
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.traps[Inexact] = True
        ctx.traps[Rounded] = True
        for bid, ask, mid in (
            ("0.0000000000", "0.0000000001", "0.0000000000"),
            ("0.0000000001", "0.0000000002", "0.0000000002"),
            ("0.1234567890", "0.8765432109", "0.5000000000"),
        ):
            row.update(best_bid=Decimal(bid), best_ask=Decimal(ask), mid=Decimal(mid))
            validate_record("gold.market_1s", row)
        with pytest.raises(ContractError, match="rounded mean"):
            validate_record("gold.market_1s", {**row, "mid": Decimal("0.49")})
        for field in ("best_bid", "best_ask"):
            with pytest.raises(ContractError, match="requires"):
                validate_record("gold.market_1s", {**row, field: None})
            validate_record("gold.market_1s", {**row, field: None, "mid": None})


def test_extreme_json_decimal_exponent_reports_contract_error():
    bad_json = '{"value":1e99999999999999999999}'
    with pytest.raises(ContractError, match="valid JSON"):
        parse_json_strict(bad_json, "source")
    row = row_for("bronze.raw")
    with pytest.raises(ContractError, match="valid JSON"):
        validate_record("bronze.raw", {**row, "raw_payload": bad_json})


@pytest.mark.parametrize(
    "dataset,field",
    [("silver.markets", "title"), ("gold.training_datasets", "features"), ("bronze.raw", "raw_payload")],
)
def test_arrow_string_fields_reject_unencodable_unicode(dataset, field):
    row = row_for(dataset)
    row[field] = "\ud800" if field == "title" else '{"value":"\ud800"}'
    with pytest.raises(ContractError, match="UTF-8 encodable"):
        validate_record(dataset, row)


def test_bronze_escaped_surrogate_remains_original_json_text():
    row = row_for("bronze.raw")
    row["raw_payload"] = r'{"value":"\ud800"}'
    validate_record("bronze.raw", row)
    assert pa.Table.from_pylist([row], schema=arrow_schema("bronze.raw")).num_rows == 1


def test_market_time_and_enums():
    row = row_for("silver.markets")
    for kind in ("scheduled", "actual"):
        opened, closed = f"{kind}_open_at", f"{kind}_close_at"
        row.update({opened: NOW, closed: NOW})
        validate_record("silver.markets", row)
        with pytest.raises(ContractError, match=opened):
            validate_record("silver.markets", {**row, closed: NOW - timedelta(seconds=1)})
        validate_record("silver.markets", {**row, opened: None})
    for old in ("open_at", "close_at"):
        with pytest.raises(ContractError, match="unknown fields"):
            validate_record("silver.markets", {**row, old: NOW})
    with pytest.raises(ContractError, match="status"):
        validate_record("silver.markets", {**row, "status": "invented"})
    for dataset, name in [("silver.book_deltas", "side"), ("silver.trades", "taker_side")]:
        row = row_for(dataset)
        if name == "taker_side":
            row[name] = "buy"
        validate_record(dataset, row)
        with pytest.raises(ContractError, match=name):
            validate_record(dataset, {**row, name: "invented"})


def test_book_levels_structure_and_values():
    row = row_for("silver.book_snapshots")
    validate_record("silver.book_snapshots", row)
    for bad in [
        "{}",
        '[{"price":"1.1","quantity":"1"}]',
        '[{"price":"0.5","quantity":"-1"}]',
        '[{"price":true,"quantity":1}]',
        '[{"price":"0.5"}]',
    ]:
        with pytest.raises(ContractError, match="bids"):
            validate_record("silver.book_snapshots", {**row, "bids": bad})


@pytest.mark.parametrize(
    "dataset,field,values",
    [
        (
            "silver.book_snapshots",
            "bids",
            ('[{"price":"0.12345678901","quantity":"1"}]', '[{"price":"0.5","quantity":"1000000000000000000"}]'),
        ),
        ("gold.market_1m", "bid_level_prices", ('{"1":"0.12345678901"}',)),
        ("gold.market_1m", "bid_level_quantities", ('{"1":"1000000000000000000"}',)),
        ("gold.market_1m", "ask_level_amounts", ('{"1":"0.12345678901"}',)),
    ],
)
def test_book_levels_reject_values_outside_decimal_precision(dataset, field, values):
    row = row_for(dataset)
    for value in values:
        with pytest.raises(ContractError, match=field):
            validate_record(dataset, {**row, field: value})
    raw = row_for("bronze.raw")
    raw["raw_payload"] = '{"price":"0.12345678901"}'
    validate_record("bronze.raw", raw)
    assert raw["raw_payload"] == '{"price":"0.12345678901"}'


def test_book_levels_accept_exact_decimal_boundaries_without_rounding():
    row = row_for("silver.book_snapshots")
    row["bids"] = '[{"price":"0.1234567890","quantity":"999999999999999999.9999999999"}]'
    validate_record("silver.book_snapshots", row)
    row = row_for("gold.market_1m")
    row["ask_level_amounts"] = '{"1":"999999999999999999.9999999999"}'
    validate_record("gold.market_1m", row)


def test_training_available_times_and_json():
    row = row_for("gold.training_datasets")
    validate_record("gold.training_datasets", row)
    for value in (NOW, NOW - timedelta(seconds=1)):
        with pytest.raises(ContractError, match="label_available_at"):
            validate_record("gold.training_datasets", {**row, "label_available_at": value})
    validate_record("gold.training_datasets", {**row, "label_available_at": NOW + timedelta(seconds=1)})
    with pytest.raises(ContractError, match="max_feature_available_at"):
        validate_record("gold.training_datasets", {**row, "max_feature_available_at": NOW + timedelta(seconds=1)})
    for patch in ({"features": "[]"}, {"source_manifest_ids": "{}"}, {"source_manifest_ids": '[" "]'}):
        with pytest.raises(ContractError):
            validate_record("gold.training_datasets", {**row, **patch})


def test_minute_contract_and_missing_data():
    row = row_for("gold.market_1m")
    validate_record("gold.market_1m", row)
    assert pa.Table.from_pylist([row], schema=arrow_schema("gold.market_1m")).num_rows == 1
    for patch in (
        {"minute": NOW + timedelta(seconds=1)},
        {"open": Decimal("1.1")},
        {"volume": Decimal("0")},
        {"trade_count": 0},
        {"bid_level_prices": '{"1":"1.1"}'},
        {"bid_level_quantities": '{"0":"1"}'},
    ):
        with pytest.raises(ContractError):
            validate_record("gold.market_1m", {**row, **patch})
    zero = {**row, "trade_data_status": "confirmed_no_trades", "volume": Decimal("0"), "trade_count": 0}
    validate_record("gold.market_1m", zero)
    with pytest.raises(ContractError):
        validate_record("gold.market_1m", {**zero, "volume": None})
    observed = {
        **row,
        "trade_data_status": "observed",
        "volume": Decimal("2"),
        "trade_count": 1,
        "open": Decimal("0.5"),
        "open_close_reason": "成交顺序不明",
        "bid_level_prices": '{"1":"0.45"}',
    }
    validate_record("gold.market_1m", observed)
    with pytest.raises(ContractError, match="open_close_reason"):
        validate_record("gold.market_1m", {**observed, "open_close_reason": None})
    with pytest.raises(ContractError, match="positive"):
        validate_record("gold.market_1m", {**observed, "volume": Decimal("0")})


def test_int64_boundary_matches_arrow():
    row = row_for("bronze.raw")
    row["record_index"] = 2**63 - 1
    validate_record("bronze.raw", row)
    assert pa.Table.from_pylist([row], schema=arrow_schema("bronze.raw")).num_rows == 1
    for value in (2**63, -(2**63) - 1):
        with pytest.raises(ContractError, match="int64"):
            validate_record("bronze.raw", {**row, "record_index": value})


def test_minute_trade_amount_and_ohlc_consistency():
    row = row_for("gold.market_1m")
    zero = {**row, "trade_data_status": "confirmed_no_trades", "volume": Decimal("0"), "trade_count": 0}
    for amount in (None, Decimal("0")):
        validate_record("gold.market_1m", {**zero, "trade_amount": amount})
    with pytest.raises(ContractError, match="trade_amount"):
        validate_record("gold.market_1m", {**zero, "trade_amount": Decimal("5")})
    observed = {
        **row,
        "trade_data_status": "observed",
        "open": Decimal("0.4"),
        "high": Decimal("0.8"),
        "low": Decimal("0.2"),
        "close": Decimal("0.7"),
        "vwap": Decimal("0.5"),
    }
    validate_record("gold.market_1m", observed)
    for patch in (
        {"high": Decimal("0.1")},
        {"open": Decimal("0.9")},
        {"close": Decimal("0.1")},
        {"vwap": Decimal("0.9")},
    ):
        with pytest.raises(ContractError, match="must be <="):
            validate_record("gold.market_1m", {**observed, **patch})
    validate_record("gold.market_1m", {**observed, "high": None, "low": None})


def test_joint_coverage_needs_both_sides_and_cannot_exceed_either():
    row = row_for("gold.market_1m")
    row.update(bid_coverage_seconds=Decimal("1"), ask_coverage_seconds=Decimal("1"))
    validate_record("gold.market_1m", {**row, "joint_coverage_seconds": Decimal("1")})
    validate_record("gold.market_1m", {**row, "joint_coverage_seconds": None})
    for patch in (
        {"joint_coverage_seconds": Decimal("60")},
        {"joint_coverage_seconds": Decimal("0.5"), "bid_coverage_seconds": None},
        {"joint_coverage_seconds": Decimal("0.5"), "ask_coverage_seconds": None},
    ):
        with pytest.raises(ContractError, match="joint_coverage_seconds"):
            validate_record("gold.market_1m", {**row, **patch})


@pytest.mark.parametrize("side", ["bid", "ask"])
def test_minute_explicit_zero_coverage_rejects_side_values_and_spread(side):
    row = row_for("gold.market_1m")
    coverage = f"{side}_coverage_seconds"
    fields = {
        f"{side}_best_price": Decimal("0.5"),
        f"{side}_level_prices": '{"1":"0.5"}',
        f"{side}_level_quantities": '{"1":"1"}',
        f"{side}_level_amounts": '{"1":"0.5"}',
        f"{side}_depth_top_n_quantity": Decimal("1"),
        f"{side}_depth_top_n_amount": Decimal("0.5"),
        f"{side}_observed_levels_avg": Decimal("1"),
        f"{side}_observed_levels_min": 1,
        "spread": Decimal("0.2"),
    }
    for field, value in fields.items():
        with pytest.raises(ContractError, match="must be null"):
            validate_record("gold.market_1m", {**row, coverage: Decimal("0"), field: value})
        # Unknown coverage is not treated as zero; positive coverage is allowed.
        validate_record("gold.market_1m", {**row, coverage: None, field: value})
        validate_record("gold.market_1m", {**row, coverage: Decimal("1"), field: value})


def test_minute_zero_joint_coverage_and_probability_spread_limit():
    row = row_for("gold.market_1m")
    row.update(bid_coverage_seconds=Decimal("1"), ask_coverage_seconds=Decimal("1"))
    with pytest.raises(ContractError, match="must be null"):
        validate_record("gold.market_1m", {**row, "joint_coverage_seconds": Decimal("0"), "spread": Decimal("0.2")})
    with pytest.raises(ContractError, match="between"):
        validate_record("gold.market_1m", {**row, "spread": Decimal("1.01")})
    validate_record("gold.market_1m", {**row, "joint_coverage_seconds": None, "spread": Decimal("1")})


@pytest.mark.parametrize("dataset", ["silver.trades", "silver.book_snapshots", "silver.book_deltas"])
def test_silver_missing_event_time_is_preserved_in_arrow(dataset):
    row = row_for(dataset)
    row["event_time"] = None
    validate_record(dataset, row)
    table = pa.Table.from_pylist([row], schema=arrow_schema(dataset))
    assert table.column("event_time").null_count == 1


def test_daily_unknown_volume_and_count_remain_null_in_arrow():
    row = row_for("gold.market_daily")
    row.update(volume=None, trade_count=None)
    validate_record("gold.market_daily", row)
    table = pa.Table.from_pylist([row], schema=arrow_schema("gold.market_daily"))
    assert table.column("volume").null_count == 1
    assert table.column("trade_count").null_count == 1


def test_daily_zero_trades_cannot_have_positive_volume():
    row = row_for("gold.market_daily")
    for volume in (None, Decimal("0")):
        validate_record("gold.market_daily", {**row, "trade_count": 0, "volume": volume})
    with pytest.raises(ContractError, match="volume"):
        validate_record("gold.market_daily", {**row, "trade_count": 0, "volume": Decimal("5")})
    validate_record("gold.market_daily", {**row, "trade_count": None, "volume": Decimal("5")})


def test_one_second_unknown_rolling_volume_preserves_quotes_in_arrow():
    row = row_for("gold.market_1s")
    row.update(best_bid=Decimal("0.4"), best_ask=Decimal("0.6"), rolling_volume=None)
    validate_record("gold.market_1s", row)
    table = pa.Table.from_pylist([row], schema=arrow_schema("gold.market_1s"))
    assert table.column("rolling_volume").null_count == 1
    assert table.column("best_bid").to_pylist() == [Decimal("0.4000000000")]
    validate_record("gold.market_1s", {**row, "rolling_volume": Decimal("0")})


def test_one_second_microprice_requires_both_quotes():
    row = row_for("gold.market_1s")
    row.update(best_bid=Decimal("0.4"), best_ask=Decimal("0.6"), microprice=Decimal("0.5"))
    validate_record("gold.market_1s", row)
    for field in ("best_bid", "best_ask"):
        with pytest.raises(ContractError, match="requires"):
            validate_record("gold.market_1s", {**row, field: None})
        validate_record("gold.market_1s", {**row, field: None, "microprice": None})


def test_one_second_imbalance_requires_depth_and_nonzero_total():
    row = row_for("gold.market_1s")
    row.update(bid_depth_top_n=Decimal("1"), ask_depth_top_n=Decimal("1"), imbalance=Decimal("0"))
    validate_record("gold.market_1s", row)
    for field in ("bid_depth_top_n", "ask_depth_top_n"):
        with pytest.raises(ContractError, match="requires"):
            validate_record("gold.market_1s", {**row, field: None})
        validate_record("gold.market_1s", {**row, field: None, "imbalance": None})
    zeros = {**row, "bid_depth_top_n": Decimal("0"), "ask_depth_top_n": Decimal("0")}
    with pytest.raises(ContractError, match="must be null"):
        validate_record("gold.market_1s", zeros)
    validate_record("gold.market_1s", {**zeros, "imbalance": None})


def test_one_second_spread_requires_both_quotes():
    row = row_for("gold.market_1s")
    row.update(best_bid=Decimal("0.4"), best_ask=Decimal("0.6"), spread=Decimal("0.2"))
    validate_record("gold.market_1s", row)
    for field in ("best_bid", "best_ask"):
        with pytest.raises(ContractError, match="requires"):
            validate_record("gold.market_1s", {**row, field: None})
        validate_record("gold.market_1s", {**row, field: None, "spread": None})
    validate_record("gold.market_1s", {**row, "spread": None})


@pytest.mark.parametrize(
    "dataset,delta", [("gold.market_1s", timedelta(seconds=1)), ("gold.market_1m", timedelta(minutes=1))]
)
def test_window_result_not_available_before_end(dataset, delta):
    row = row_for(dataset)
    validate_record(dataset, {**row, "as_of": NOW + delta})
    validate_record(dataset, {**row, "as_of": NOW + delta + timedelta(hours=1)})
    with pytest.raises(ContractError, match="window end"):
        validate_record(dataset, {**row, "as_of": NOW + delta - timedelta(microseconds=1)})


def test_duplicate_json_keys_rejected_even_in_nested_objects():
    row = row_for("gold.market_1m")
    row["bid_level_prices"] = '{"1":"0.4","1":"0.8"}'
    with pytest.raises(ContractError, match="Duplicate JSON key"):
        validate_record("gold.market_1m", row)
    raw = row_for("bronze.raw")
    raw["raw_payload"] = '{"nested":{"key":1,"key":2}}'
    validate_record("bronze.raw", raw)
    assert raw["raw_payload"] == '{"nested":{"key":1,"key":2}}'
    with pytest.raises(ContractError, match="Duplicate JSON key"):
        parse_json_strict(raw["raw_payload"], "raw_payload")


def test_shape_type_range_and_iso_rejections():
    row = row_for("gold.market_daily")
    validate_record("gold.market_daily", row)
    bad_rows = [
        {k: v for k, v in row.items() if k != "venue"},
        {**row, "schema_version": "old"},
        {**row, "venue": None},
        {**row, "venue": " "},
        {**row, "trade_count": True},
        {**row, "day": "2024-02-30"},
    ]
    for bad in bad_rows:
        with pytest.raises(ContractError):
            validate_record("gold.market_daily", bad)
    row = row_for("gold.liquidity_features")
    with pytest.raises(ContractError, match="imbalance"):
        validate_record("gold.liquidity_features", {**row, "imbalance": Decimal("-1.1")})


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_pk",
        "nullable_pk",
        "bad_type",
        "missing_description",
        "empty_description",
        "unknown_rule",
        "unknown_field",
        "malformed_rule",
        "wrong_rule_field_type",
    ],
)
def test_invalid_registry_rejected(mutation):
    path = Path(__file__).parents[1] / "src/data_schema/schema_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    dataset = registry["datasets"]["silver.market_states"]
    if mutation == "missing_pk":
        dataset["primary_key"].append("missing")
    elif mutation == "nullable_pk":
        dataset["fields"]["venue"]["type"] = "str?"
    elif mutation == "bad_type":
        dataset["fields"]["venue"]["type"] = "unknown"
    elif mutation == "missing_description":
        del dataset["fields"]["venue"]["description"]
    elif mutation == "empty_description":
        dataset["fields"]["venue"]["description"] = " "
    elif mutation == "unknown_rule":
        dataset["rules"].append({"type": "unknown"})
    elif mutation == "unknown_field":
        dataset["rules"].append({"type": "range", "field": "missing", "min": "0"})
    elif mutation == "malformed_rule":
        dataset["rules"].append({"type": "range", "field": "best_bid"})
    else:
        dataset["rules"].append({"type": "range", "field": "venue", "min": "0"})
    with pytest.raises(ValueError):
        validate_registry(copy.deepcopy(registry))


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_field", "nullable_field"])
def test_registry_requires_exactly_one_rule_for_required_version_field(mutation):
    path = Path(__file__).parents[1] / "src/data_schema/schema_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    contract = registry["datasets"]["bronze.raw"]
    version_rule = next(rule for rule in contract["rules"] if rule["type"] == "version")
    if mutation == "missing":
        contract["rules"].remove(version_rule)
    elif mutation == "duplicate":
        contract["rules"].append(copy.deepcopy(version_rule))
    elif mutation == "wrong_field":
        version_rule["field"] = "source"
    else:
        contract["fields"][registry["version_field"]]["type"] = "str?"
    with pytest.raises(ValueError, match="version"):
        validate_registry(registry)


@pytest.mark.parametrize("location", ["top_level", "nested"])
def test_registry_import_rejects_duplicate_keys(tmp_path, location):
    root = Path(__file__).parents[1]
    source = root / "src/data_schema/contracts.py"
    registry_text = (source.parent / "schema_registry.json").read_text(encoding="utf-8")
    if location == "top_level":
        registry_text = registry_text.replace(
            f'"version": "{SCHEMA_VERSION}",', f'"version": "{SCHEMA_VERSION}", "version": "9.9.9",', 1
        )
    else:
        registry_text = registry_text.replace('"run_id": {', '"run_id": {"type": "str", "type": "str",', 1)
    (tmp_path / "contracts.py").write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "schema_registry.json").write_text(registry_text, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        runpy.run_path(str(tmp_path / "contracts.py"))


def test_schema_generator_refuses_duplicate_registry_keys_without_writing(tmp_path):
    root = Path(__file__).parents[1]
    (tmp_path / "scripts").mkdir()
    (tmp_path / "src/data_schema").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    for relative in (
        "scripts/generate_schema_docs.py",
        "src/__init__.py",
        "src/data_schema/__init__.py",
        "src/data_schema/contracts.py",
    ):
        (tmp_path / relative).write_bytes((root / relative).read_bytes())
    registry = (root / "src/data_schema/schema_registry.json").read_text(encoding="utf-8")
    registry = registry.replace(
        f'"version": "{SCHEMA_VERSION}",', f'"version": "{SCHEMA_VERSION}", "version": "9.9.9",', 1
    )
    (tmp_path / "src/data_schema/schema_registry.json").write_text(registry, encoding="utf-8")
    document = tmp_path / "docs/SCHEMAS.md"
    document.write_text("do not replace", encoding="utf-8")
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, str(tmp_path / "scripts/generate_schema_docs.py")],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Duplicate JSON key: version" in result.stderr
    assert document.read_text(encoding="utf-8") == "do not replace"


def test_generated_docs_detect_registry_changes():
    from scripts.generate_schema_docs import regenerate

    root = Path(__file__).parents[1]
    document = (root / "docs/SCHEMAS.md").read_text(encoding="utf-8")
    registry = json.loads((root / "src/data_schema/schema_registry.json").read_text(encoding="utf-8"))
    assert regenerate(document, registry) == document
    registry["datasets"]["silver.markets"]["fields"]["title"]["description"] += " changed"
    assert regenerate(document, registry) != document


def test_market_keeps_scheduled_and_actual_times_separately():
    row = row_for("silver.markets")
    row.update(
        description="Source market description.",
        settlement_rules="Resolves Yes if the source condition is met.",
        scheduled_open_at=NOW,
        scheduled_close_at=NOW + timedelta(days=2),
        actual_open_at=NOW + timedelta(hours=1),
        actual_close_at=NOW + timedelta(days=1),
    )
    validate_record("silver.markets", row)
    # Scheduled and actual times are independent; an early actual close is representable.
    validate_record("silver.markets", {**row, "actual_close_at": NOW + timedelta(hours=2)})
    validate_record("silver.markets", {**row, "source_close_time_text": "2024-01-02T00:00:00Z"})
    table = pa.Table.from_pylist([row], schema=arrow_schema("silver.markets"))
    assert table.column("settlement_rules").to_pylist() == [row["settlement_rules"]]
    for name in ("description", "settlement_rules", "source_open_time_text", "source_close_time_text"):
        validate_record("silver.markets", {**row, name: None})
        with pytest.raises(ContractError, match=f"{name} must be nonempty"):
            validate_record("silver.markets", {**row, name: " "})


def test_outcome_identity_includes_market_and_description_is_optional():
    contract = get_contract("silver.outcomes")
    assert contract["primary_key"] == ("venue", "market_id", "outcome_id", "observed_at")
    first = row_for("silver.outcomes")
    second = {**first, "market_id": "other-market"}
    validate_record("silver.outcomes", first)
    validate_record("silver.outcomes", second)
    key = contract["primary_key"]
    assert tuple(first[k] for k in key) != tuple(second[k] for k in key)
    validate_record("silver.outcomes", {**first, "description": "Source outcome text."})
    with pytest.raises(ContractError, match="description must be nonempty"):
        validate_record("silver.outcomes", {**first, "description": ""})


def test_settlement_time_may_be_unknown_without_substitution():
    row = row_for("silver.settlements")
    assert row["settled_at"] is None
    validate_record("silver.settlements", row)
    table = pa.Table.from_pylist([row], schema=arrow_schema("silver.settlements"))
    assert table.column("settled_at").to_pylist() == [None]


def test_daily_as_of_not_before_utc_day_start():
    row = row_for("gold.market_daily")
    row["day"] = "2024-01-02"
    day_start = datetime(2024, 1, 2, tzinfo=timezone.utc)
    # Boundary and intraday values are allowed; the day need not have ended.
    for as_of in (day_start, day_start + timedelta(hours=6), day_start + timedelta(days=3)):
        validate_record("gold.market_daily", {**row, "as_of": as_of})
    with pytest.raises(ContractError, match=r"as_of must not be before the start of UTC day 2024-01-02 \(day\)"):
        validate_record("gold.market_daily", {**row, "as_of": day_start - timedelta(microseconds=1)})
    with pytest.raises(ContractError, match="ISO calendar date"):
        validate_record("gold.market_daily", {**row, "day": "2024-13-01", "as_of": day_start})
    # Rule order is not guaranteed, so day_start must reject an unparsable day on its own.
    from src.data_schema.contracts import _check_rule

    rule = {"type": "day_start", "field": "as_of", "day": "day"}
    for bad in ("2024-13-01", 20240102):
        with pytest.raises(ContractError, match=r"gold.market_daily.day must be an ISO calendar date"):
            _check_rule("gold.market_daily", rule, {**row, "day": bad, "as_of": day_start}, {})


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong_field_type", "day_start needs"),
        ("wrong_day_type", "day_start needs"),
        ("missing_iso_date", "day_start needs"),
        ("missing_key", "malformed day_start rule"),
    ],
)
def test_day_start_rule_declaration_is_checked(mutation, message):
    path = Path(__file__).parents[1] / "src/data_schema/schema_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    dataset = registry["datasets"]["gold.market_daily"]
    rule = next(r for r in dataset["rules"] if r["type"] == "day_start")
    if mutation == "wrong_field_type":
        rule["field"] = "market_id"
    elif mutation == "wrong_day_type":
        rule["day"] = "as_of"
    elif mutation == "missing_iso_date":
        dataset["rules"].remove({"type": "iso_date", "field": "day"})
    else:
        del rule["day"]
    with pytest.raises(ValueError, match=message):
        validate_registry(registry)


def test_generated_schema_tables_list_every_rule_on_each_referenced_field():
    from scripts.generate_schema_docs import generated_tables
    from src.data_schema.contracts import RULE_FIELDS

    path = Path(__file__).parents[1] / "src/data_schema/schema_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    rows = {}
    dataset = None
    for line in generated_tables(registry).splitlines():
        if line.startswith("### `"):
            dataset = line[5:-1]
        elif line.startswith("| `"):
            rows[(dataset, line.split("`")[1])] = line
    for name, contract in registry["datasets"].items():
        for rule in contract["rules"]:
            text = json.dumps(rule, ensure_ascii=False, sort_keys=True)
            for key in RULE_FIELDS[rule["type"]]:
                assert f"`{text}`" in rows[(name, rule[key])], (name, rule)


def test_schema_generator_rejects_arguments_without_writing(tmp_path, monkeypatch):
    import scripts.generate_schema_docs as generator

    monkeypatch.setattr(generator, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["generate_schema_docs.py", "--help"])
    with pytest.raises(SystemExit, match="takes no arguments"):
        generator.main()
    assert not (tmp_path / "docs").exists()
