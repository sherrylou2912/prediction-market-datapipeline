"""Venue capability, normalization, provenance, and pagination contracts."""

from __future__ import annotations

import json
from collections import deque
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from zoneinfo import ZoneInfo

import pyarrow as pa
import pytest

from src.adapters.base import NormalizationError, UnsupportedCapabilityError, parse_utc_timestamp
from src.adapters.mock import MockVenueAdapter
from src.data_schema.contracts import SCHEMA_VERSION, ContractError, arrow_schema

WHEN = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)


def envelope(payload: object) -> dict:
    return {
        "run_id": "receipt-run",
        "record_index": 42,
        "venue": "mock",
        "source": "mock",
        "message_type": "test",
        "source_event_id": None,
        "event_time": None,
        "received_at": WHEN,
        "ingested_at": WHEN,
        "sequence": None,
        "api_version": "1",
        "protocol_version": None,
        "schema_version": SCHEMA_VERSION,
        "raw_payload": json.dumps(payload),
        "raw_bytes": None,
    }


def test_normalization_failures_retain_evidence_and_exception() -> None:
    adapter = MockVenueAdapter()
    original = adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0]
    for payload in (
        {k: v for k, v in original.items() if k != "price"},
        {**original, "price": "abc"},
        {**original, "price": "1.5"},
    ):
        raw = envelope(payload)
        with pytest.raises(NormalizationError) as caught:
            adapter.normalize_trade(raw)
        assert caught.value.dataset == "silver.trades"
        assert caught.value.raw_record == raw and caught.value.__cause__ is not None
    row = adapter.normalize_trade(envelope(original))
    assert row["bronze_run_id"] == "receipt-run" and row["bronze_record_index"] == 42
    assert "bronze_run_id" not in original


@pytest.mark.parametrize("book", [False, True])
def test_raw_bytes_normalization_and_failure_keep_exact_evidence(book: bool) -> None:
    adapter = MockVenueAdapter()
    payload = (
        next(adapter.stream_market_data(["mock-1"]))
        if book
        else adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0]
    )
    raw = envelope(payload)
    raw["raw_bytes"] = raw.pop("raw_payload").encode("utf-8")
    raw["raw_payload"] = None
    normalize = adapter.normalize_book_event if book else adapter.normalize_trade
    assert normalize(raw) is not None
    for contents in (b"\xff\x00", b"{broken"):
        with pytest.raises(NormalizationError) as caught:
            normalize({**raw, "raw_bytes": contents})
        assert caught.value.raw_record["raw_bytes"] == contents
        assert caught.value.__cause__ is not None


@pytest.mark.parametrize("book", [False, True])
def test_time_anomaly_blocks_normalization_but_retains_bronze(book: bool) -> None:
    adapter = MockVenueAdapter()
    payload = (
        next(adapter.stream_market_data(["mock-1"]))
        if book
        else adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0]
    )
    raw = envelope(payload)
    raw["ingested_at"] = WHEN - timedelta(seconds=1)
    with pytest.raises(NormalizationError, match="earlier than receipt") as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert caught.value.raw_record["ingested_at"] == raw["ingested_at"]
    assert caught.value.raw_record["raw_payload"] == raw["raw_payload"]


@pytest.mark.parametrize("book", [False, True])
def test_missing_receipt_time_is_not_invented_for_silver(book: bool) -> None:
    adapter = MockVenueAdapter()
    payload = (
        next(adapter.stream_market_data(["mock-1"]))
        if book
        else adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0]
    )
    raw = envelope(payload)
    raw["received_at"] = None
    with pytest.raises(NormalizationError) as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert caught.value.raw_record["received_at"] is None


def test_book_events_include_dataset_and_arrow_schema() -> None:
    adapter = MockVenueAdapter()
    delta = next(adapter.stream_market_data(["mock-1"]))
    snapshot = {
        "type": "snapshot",
        "snapshot_id": "snap-1",
        "market_id": "mock-1",
        "outcome_id": "yes",
        "source_sequence": 1,
        "event_time": WHEN.isoformat(),
        "received_at": WHEN.isoformat(),
        "bids": [{"price": "0.4", "quantity": "2"}],
        "asks": [{"price": "0.6", "quantity": "3"}],
        "recovery": False,
    }
    for payload, dataset in ((delta, "silver.book_deltas"), (snapshot, "silver.book_snapshots")):
        result = adapter.normalize_book_event(envelope(payload))
        assert result.dataset == dataset
        assert pa.Table.from_pylist([result.record], schema=arrow_schema(dataset)).num_rows == 1
    assert list(adapter.stream_market_data(["unrelated"])) == []


@pytest.mark.parametrize(
    ("method", "payload", "dataset"),
    [
        (
            "normalize_settlement",
            {
                "market_id": "m",
                "outcome_id": "yes",
                "payout": "1",
                "settled_at": WHEN.isoformat(),
                "observed_at": WHEN.isoformat(),
            },
            "silver.settlements",
        ),
        ("normalize_event", {"event_id": "e", "title": "title", "observed_at": WHEN.isoformat()}, "silver.events"),
        (
            "normalize_outcome",
            {"outcome_id": "yes", "market_id": "m", "label": "Yes", "observed_at": WHEN.isoformat()},
            "silver.outcomes",
        ),
        (
            "normalize_market_state",
            {"market_id": "m", "status": "open", "best_bid": "0.4", "best_ask": "0.6", "observed_at": WHEN.isoformat()},
            "silver.market_states",
        ),
    ],
)
def test_new_normalizers_validate_rows(method: str, payload: dict, dataset: str) -> None:
    normalize = getattr(MockVenueAdapter(), method)
    row = normalize(envelope(payload))
    assert pa.Table.from_pylist([row], schema=arrow_schema(dataset)).num_rows == 1
    invalid = {
        k: v
        for k, v in payload.items()
        if k
        != {
            "normalize_settlement": "payout",
            "normalize_event": "title",
            "normalize_outcome": "label",
            "normalize_market_state": "status",
        }[method]
    }
    with pytest.raises(NormalizationError) as caught:
        normalize(envelope(invalid))
    assert caught.value.dataset == dataset and caught.value.__cause__ is not None


@pytest.mark.parametrize(
    "field",
    [
        "capabilities",
        "venue",
        "primary_keys",
        "pagination_checkpoint_semantics",
        "rate_limits",
        "timestamp_semantics",
        "precision",
    ],
)
def test_empty_metadata_rejected(field: str) -> None:
    with pytest.raises(ValueError):
        replace(MockVenueAdapter().metadata, **{field: None})


@pytest.mark.parametrize("limit", [True, "10", 0, -1])
def test_invalid_rate_limits_rejected(limit: object) -> None:
    with pytest.raises(ValueError):
        replace(MockVenueAdapter().metadata, rate_limits={"requests": limit})


def test_metadata_nested_rules_and_unsupported_capability() -> None:
    adapter = MockVenueAdapter()
    for changes in (
        {"primary_keys": {"markets": ()}},
        {"capabilities": frozenset({"unknown"})},
    ):
        with pytest.raises(ValueError):
            replace(adapter.metadata, **changes)
    with pytest.raises(TypeError):
        adapter.metadata.rate_limits["requests_per_second"] = 2

    class NoTrades(MockVenueAdapter):
        @property
        def metadata(self):
            return replace(
                super().metadata,
                capabilities=super().metadata.capabilities - {"trades"},
                primary_keys={k: v for k, v in super().metadata.primary_keys.items() if k != "trades"},
            )

    with pytest.raises(UnsupportedCapabilityError):
        NoTrades().backfill_trades(WHEN, WHEN + timedelta(days=1))


def test_time_ranges_and_pagination() -> None:
    adapter = MockVenueAdapter()
    for start, end in (
        (WHEN, WHEN),
        (WHEN + timedelta(days=1), WHEN),
        (WHEN.replace(tzinfo=None), WHEN),
        (WHEN.replace(tzinfo=ZoneInfo("UTC")), WHEN),
    ):
        with pytest.raises(ValueError, match="timezone.utc"):
            adapter.backfill_trades(start, end)
    assert parse_utc_timestamp("2024-01-01T12:00:00Z") == WHEN
    ids, cursor = [], None
    while True:
        page = adapter.backfill_trades(WHEN, WHEN + timedelta(days=3), cursor)
        ids.extend(item["trade_id"] for item in page.items)
        cursor = page.next_cursor
        if cursor is None:
            break
    assert ids == ["mock-trade-1", "mock-trade-2", "mock-trade-3"]
    selected = adapter.backfill_trades(WHEN + timedelta(days=1), WHEN + timedelta(days=2))
    assert [item["trade_id"] for item in selected.items] == ["mock-trade-2"]
    assert selected.next_cursor is None


def test_book_source_format_is_adapter_specific_and_invalid_result_is_programmer_error() -> None:
    from src.adapters.base import NormalizedBookEvent

    class DifferentVenueFormat(MockVenueAdapter):
        def _normalize_book_event(self, payload, bronze):
            return super()._normalize_book_event({**payload, "type": payload["kind"]}, bronze)

    adapter = DifferentVenueFormat()
    payload = dict(next(adapter.stream_market_data(["mock-1"])))
    payload["kind"] = payload.pop("type")
    assert adapter.normalize_book_event(envelope(payload)).dataset == "silver.book_deltas"

    class BrokenAdapter(MockVenueAdapter):
        def _normalize_book_event(self, payload, bronze):
            return NormalizedBookEvent("silver.unrelated", {})

    from src.adapters.base import AdapterOutputError

    with pytest.raises(AdapterOutputError, match="invalid book event dataset") as caught:
        BrokenAdapter().normalize_book_event(envelope(payload))
    assert not isinstance(caught.value, NormalizationError)


def test_decimal_source_type_error_is_normalization_error_not_programming_error() -> None:
    adapter = MockVenueAdapter()
    payload = dict(adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0])
    payload["price"] = None
    with pytest.raises(NormalizationError) as caught:
        adapter.normalize_trade(envelope(payload))
    assert isinstance(caught.value.__cause__, ValueError)

    class BrokenAdapter(MockVenueAdapter):
        def _normalize_trade(self, payload, bronze):
            raise TypeError("programming error")

    with pytest.raises(TypeError, match="programming error"):
        BrokenAdapter().normalize_trade(envelope(payload))


def test_malformed_source_and_programming_errors_are_distinct() -> None:
    adapter = MockVenueAdapter()
    payload = dict(adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0])
    for error in (ValueError("parser bug"), KeyError("internal bug"), TypeError("internal bug")):

        class BrokenAdapter(MockVenueAdapter):
            def _normalize_trade(self, payload, bronze, _error=error):
                raise _error

        with pytest.raises(type(error), match="bug") as caught:
            BrokenAdapter().normalize_trade(envelope(payload))
        assert not isinstance(caught.value, NormalizationError)


def test_normalization_uses_envelope_observation_and_checks_provenance() -> None:
    from src.adapters.base import AdapterOutputError

    adapter = MockVenueAdapter()
    payload = dict(adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0])
    payload["observed_at"] = "1900-01-01T00:00:00Z"
    raw = envelope(payload)
    assert adapter.normalize_trade(raw)["observed_at"] == raw["received_at"]
    delta = dict(next(adapter.stream_market_data(["mock-1"])))
    delta["received_at"] = "1900-01-01T00:00:00Z"
    assert adapter.normalize_book_event(envelope(delta)).record["received_at"] == WHEN

    for field, value in (
        ("bronze_run_id", "wrong"),
        ("bronze_record_index", 99),
        ("venue", "kalshi"),
        ("observed_at", WHEN + timedelta(days=1)),
    ):

        class BrokenAdapter(MockVenueAdapter):
            def _normalize_trade(self, payload, bronze, _field=field, _value=value):
                return {**super()._normalize_trade(payload, bronze), _field: _value}

        with pytest.raises(AdapterOutputError):
            BrokenAdapter().normalize_trade(raw)


@pytest.mark.parametrize("book", [False, True])
def test_adapter_cannot_mutate_or_forge_bronze_provenance(book: bool) -> None:
    from src.adapters.base import AdapterOutputError, NormalizedBookEvent

    class BrokenAdapter(MockVenueAdapter):
        def _normalize_trade(self, payload, bronze):
            with pytest.raises(TypeError):
                bronze["run_id"] = "forged"
            return {**super()._normalize_trade(payload, bronze), "bronze_run_id": "forged"}

        def _normalize_book_event(self, payload, bronze):
            with pytest.raises(TypeError):
                bronze["run_id"] = "forged"
            event = super()._normalize_book_event(payload, bronze)
            return NormalizedBookEvent(event.dataset, {**event.record, "bronze_run_id": "forged"})

    adapter = BrokenAdapter()
    payload = (
        next(adapter.stream_market_data(["mock-1"]))
        if book
        else adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0]
    )
    raw = envelope(payload)
    with pytest.raises(AdapterOutputError, match="provenance"):
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert raw["run_id"] == "receipt-run"


@pytest.mark.parametrize("book", [False, True])
def test_readonly_mapping_failure_preserves_bronze_evidence(book: bool) -> None:
    adapter = MockVenueAdapter()
    raw = envelope({})
    raw["raw_payload"] = '{"duplicate":1,"duplicate":2}'
    with pytest.raises(NormalizationError) as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(MappingProxyType(raw))
    assert caught.value.evidence_is_snapshot is True
    assert type(caught.value.raw_record) is dict
    assert caught.value.raw_record == raw
    raw["run_id"] = "changed"
    assert caught.value.raw_record["run_id"] == "receipt-run"


@pytest.mark.parametrize("book", [False, True])
@pytest.mark.parametrize("field", ["run_id", "raw_payload"])
def test_nested_readonly_mapping_in_invalid_envelope_retains_evidence(book: bool, field: str) -> None:
    raw = envelope({})
    nested = {"items": [MappingProxyType({"key": "original"})]}
    raw[field] = MappingProxyType(nested)
    adapter = MockVenueAdapter()
    with pytest.raises(NormalizationError) as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(MappingProxyType(raw))
    nested["items"][0] = {"key": "changed"}
    assert caught.value.evidence_is_snapshot is True
    assert type(caught.value.raw_record) is dict
    assert type(caught.value.raw_record[field]) is dict
    assert type(caught.value.raw_record[field]["items"][0]) is dict
    assert caught.value.raw_record[field]["items"][0]["key"] == "original"
    assert isinstance(caught.value.__cause__, ContractError)


@pytest.mark.parametrize("book", [False, True])
@pytest.mark.parametrize("kind", ["readonly_in_deque", "deep_list", "uncopyable"])
def test_failed_evidence_copy_keeps_original_record_reference(book: bool, kind: str) -> None:
    class Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("copy failed")

    if kind == "readonly_in_deque":
        value = deque([MappingProxyType({"key": "original"})])
    elif kind == "deep_list":
        value = []
        current = value
        for _ in range(1200):
            child = []
            current.append(child)
            current = child
    else:
        value = Uncopyable()
    raw = envelope({})
    raw["run_id"] = value
    adapter = MockVenueAdapter()
    with pytest.raises(NormalizationError, match="not a snapshot") as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert caught.value.raw_record is raw
    assert caught.value.raw_record["run_id"] is value
    assert caught.value.evidence_is_snapshot is False
    assert caught.value.evidence_copy_error_type == type(caught.value.__cause__).__name__
    raw["source"] = "changed later"
    assert caught.value.raw_record["source"] == "changed later"


def test_error_reuses_independent_first_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.adapters import base

    original_copy = base._copy_raw_record
    calls = []

    def copy_once(record):
        calls.append(True)
        if len(calls) > 1:
            raise RuntimeError("second copy failed")
        return original_copy(record)

    monkeypatch.setattr(base, "_copy_raw_record", copy_once)
    raw = envelope({})
    raw["run_id"] = -1
    with pytest.raises(NormalizationError) as caught:
        MockVenueAdapter().normalize_trade(raw)
    assert isinstance(caught.value.__cause__, ContractError)
    assert len(calls) == 1
    assert caught.value.evidence_is_snapshot is True
    assert caught.value.evidence_copy_error_type is None
    assert caught.value.raw_record is not raw
    assert caught.value.raw_record["run_id"] == raw["run_id"]
    raw["source"] = "changed later"
    assert caught.value.raw_record["source"] != raw["source"]


@pytest.mark.parametrize("book", [False, True])
def test_untrusted_copy_hooks_cannot_forge_or_claim_independent_evidence(book: bool) -> None:
    class MutableSelfCopy:
        def __init__(self):
            self.value = "original"

        def __deepcopy__(self, memo):
            return self

    class ChangedString(str):
        def __deepcopy__(self, memo):
            return "fabricated-run-id"

    adapter = MockVenueAdapter()
    for value in (MutableSelfCopy(), ChangedString("genuine-run-id")):
        raw = envelope({})
        raw["run_id"] = value
        with pytest.raises(NormalizationError, match="not a snapshot") as caught:
            (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
        assert caught.value.raw_record is raw
        assert caught.value.raw_record["run_id"] is value
        assert caught.value.evidence_is_snapshot is False


@pytest.mark.parametrize("book", [False, True])
@pytest.mark.parametrize("readonly", [False, True])
def test_untrusted_top_level_mapping_cannot_forge_provenance(book: bool, readonly: bool) -> None:
    class ForgedMapping(dict):
        def __iter__(self):
            return super().__iter__()

        def __getitem__(self, key):
            return "fabricated-run-id" if key == "run_id" else super().__getitem__(key)

    original = ForgedMapping(envelope({}))
    raw = MappingProxyType(original) if readonly else original
    adapter = MockVenueAdapter()
    with pytest.raises(NormalizationError, match="not a snapshot") as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert caught.value.raw_record is raw
    assert caught.value.evidence_is_snapshot is False
    assert dict.__getitem__(original, "run_id") == "receipt-run"


@pytest.mark.parametrize("book", [False, True])
def test_excessively_nested_source_json_retains_evidence(book: bool) -> None:
    raw = envelope({})
    raw["raw_payload"] = '{"nested":' + "[" * 1200 + "0" + "]" * 1200 + "}"
    adapter = MockVenueAdapter()
    with pytest.raises(NormalizationError) as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert caught.value.raw_record["raw_payload"] == raw["raw_payload"]
    assert isinstance(caught.value.__cause__, ContractError)
    assert isinstance(caught.value.__cause__.__cause__, RecursionError)


@pytest.mark.parametrize("book", [False, True])
def test_non_string_envelope_key_retains_evidence(book: bool) -> None:
    raw = {**envelope({}), 42: "number key", "unexpected": "text key"}
    adapter = MockVenueAdapter()
    with pytest.raises(NormalizationError, match="field names must be strings") as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert caught.value.raw_record[42] == "number key"
    assert caught.value.raw_record["unexpected"] == "text key"
    assert isinstance(caught.value.__cause__, ContractError)


@pytest.mark.parametrize("book", [False, True])
def test_extreme_json_number_becomes_normalization_error_with_evidence(book: bool) -> None:
    raw = envelope({})
    raw["raw_payload"] = '{"price":1e999999999999999999999999999}'
    adapter = MockVenueAdapter()
    with pytest.raises(NormalizationError) as caught:
        (adapter.normalize_book_event if book else adapter.normalize_trade)(raw)
    assert isinstance(caught.value.__cause__, ContractError)
    assert caught.value.evidence_is_snapshot is True
    assert caught.value.raw_record["raw_payload"] == raw["raw_payload"]


@pytest.mark.parametrize("kind", ["trade", "snapshot", "delta"])
@pytest.mark.parametrize("missing", [False, True])
def test_source_event_time_can_be_unknown(kind: str, missing: bool) -> None:
    adapter = MockVenueAdapter()
    if kind == "trade":
        payload = dict(adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0])
    elif kind == "delta":
        payload = dict(next(adapter.stream_market_data(["mock-1"])))
    else:
        payload = {
            "type": "snapshot",
            "snapshot_id": "s",
            "market_id": "m",
            "outcome_id": "yes",
            "bids": [],
            "asks": [],
            "recovery": False,
            "event_time": WHEN.isoformat(),
        }
    if missing:
        payload.pop("event_time", None)
    else:
        payload["event_time"] = None
    result = (
        adapter.normalize_trade(envelope(payload))
        if kind == "trade"
        else adapter.normalize_book_event(envelope(payload)).record
    )
    assert result["event_time"] is None


def test_adapter_rejects_wrong_venue_or_version() -> None:
    from src.adapters.base import AdapterRoutingError

    adapter = MockVenueAdapter()
    payload = adapter.backfill_trades(WHEN - timedelta(hours=1), WHEN + timedelta(hours=1)).items[0]
    for changes in (
        {"venue": "kalshi"},
        {"venue": None},
        {"api_version": "wrong"},
        {"api_version": None},
        {"protocol_version": "wrong"},
    ):
        with pytest.raises(AdapterRoutingError):
            adapter.normalize_trade({**envelope(payload), **changes})


@pytest.mark.parametrize("venue", ["kalshi", None])
@pytest.mark.parametrize(
    "content",
    [
        {"raw_payload": None, "raw_bytes": b"\xff"},
        {"raw_payload": None, "raw_bytes": b"a,b\n1,2\n"},
        {"raw_payload": "[]"},
        {"raw_payload": "{not json"},
        {"record_index": -1},
        {"ingested_at": WHEN - timedelta(seconds=1)},
    ],
)
@pytest.mark.parametrize("book", [False, True])
def test_routing_is_checked_before_content_and_time(venue: object, content: dict, book: bool) -> None:
    from src.adapters.base import AdapterRoutingError

    adapter = MockVenueAdapter()
    normalize = adapter.normalize_book_event if book else adapter.normalize_trade
    with pytest.raises(AdapterRoutingError):
        normalize({**envelope({"trade_id": "t"}), "venue": venue, **content})


def test_primary_keys_match_capabilities_and_cursor_matches_query() -> None:
    adapter = MockVenueAdapter()
    with pytest.raises(ValueError, match="match declared capabilities"):
        replace(adapter.metadata, primary_keys={"unrelated": ("id",)})
    cursor = adapter.backfill_trades(WHEN, WHEN + timedelta(days=3)).next_cursor
    assert cursor
    with pytest.raises(ValueError, match="does not match query"):
        adapter.backfill_trades(WHEN + timedelta(days=1), WHEN + timedelta(days=3), cursor)
    with pytest.raises(ValueError, match="does not match query"):
        adapter.backfill_markets(WHEN, WHEN + timedelta(days=3), cursor)
    with pytest.raises(ValueError, match="does not match query"):
        adapter.discover_markets(cursor)


def test_duplicate_source_json_keys_are_quarantined_without_losing_raw_evidence() -> None:
    adapter = MockVenueAdapter()
    raw = envelope({})
    raw["raw_payload"] = '{"trade_id":"one","trade_id":"other"}'
    with pytest.raises(NormalizationError, match="Duplicate JSON key") as caught:
        adapter.normalize_trade(raw)
    assert caught.value.raw_record["raw_payload"] == raw["raw_payload"]
    assert caught.value.__cause__ is not None


def test_book_snapshot_accepts_json_decimal_levels_without_rounding() -> None:
    adapter = MockVenueAdapter()
    raw = envelope(
        {
            "type": "snapshot",
            "snapshot_id": "s",
            "market_id": "m",
            "outcome_id": "yes",
            "event_time": WHEN.isoformat(),
            "bids": [],
            "asks": [],
            "recovery": False,
        }
    )
    raw["raw_payload"] = raw["raw_payload"].replace('"bids": []', '"bids": [{"price": 0.123456789, "quantity": 2.5}]')
    result = adapter.normalize_book_event(raw)
    assert json.loads(result.record["bids"])[0]["price"] == "0.123456789"


def test_mock_market_maps_explicit_source_fields_without_guessing() -> None:
    adapter = MockVenueAdapter()
    payload = {"market_id": "m", "title": "Title", "status": "open"}
    row = adapter.normalize_market(envelope(payload))
    for name in (
        "description",
        "settlement_rules",
        "scheduled_open_at",
        "scheduled_close_at",
        "actual_open_at",
        "actual_close_at",
        "source_open_time_text",
        "source_close_time_text",
    ):
        assert row[name] is None
    full = {
        **payload,
        "description": "Description",
        "settlement_rules": "Rules",
        "scheduled_open_at": WHEN.isoformat(),
        "scheduled_close_at": (WHEN + timedelta(days=1)).isoformat(),
        "actual_open_at": WHEN.isoformat(),
        "actual_close_at": (WHEN + timedelta(hours=1)).isoformat(),
    }
    row = adapter.normalize_market(envelope(full))
    assert row["settlement_rules"] == "Rules"
    assert row["actual_close_at"] == WHEN + timedelta(hours=1)
    assert row["scheduled_close_at"] == WHEN + timedelta(days=1)
    with pytest.raises(NormalizationError) as caught:
        adapter.normalize_market(envelope({**full, "actual_close_at": "not-a-time"}))
    assert caught.value.dataset == "silver.markets"


def test_mock_settlement_without_time_stays_unknown() -> None:
    adapter = MockVenueAdapter()
    payload = {"market_id": "m", "outcome_id": "yes", "payout": "1"}
    row = adapter.normalize_settlement(envelope(payload))
    assert row["settled_at"] is None
    assert row["observed_at"] == WHEN
    assert (
        adapter.normalize_outcome(envelope({"outcome_id": "yes", "market_id": "m", "label": "Yes"}))["description"]
        is None
    )


def test_mock_unclassified_source_times_are_kept_as_text_only() -> None:
    adapter = MockVenueAdapter()
    payload = {
        "market_id": "m",
        "title": "Title",
        "status": "closed",
        "open_at": "2024-01-01T00:00:00Z",
        "close_at": "Jan 2 2024 5pm ET",
    }
    row = adapter.normalize_market(envelope(payload))
    assert row["source_open_time_text"] == "2024-01-01T00:00:00Z"
    assert row["source_close_time_text"] == "Jan 2 2024 5pm ET"
    for name in ("scheduled_open_at", "scheduled_close_at", "actual_open_at", "actual_close_at"):
        assert row[name] is None
    with pytest.raises(NormalizationError):
        adapter.normalize_market(envelope({**payload, "close_at": 1704214800}))


@pytest.mark.parametrize("field", ["api_version", "protocol_version"])
@pytest.mark.parametrize("value", ["", "  ", 1])
def test_optional_versions_must_be_nonempty_text_when_declared(field: str, value: object) -> None:
    with pytest.raises(ValueError, match=field):
        replace(MockVenueAdapter().metadata, **{field: value})


class NoApiVersionAdapter(MockVenueAdapter):
    @property
    def metadata(self):
        return replace(super().metadata, api_version=None)


def test_adapter_without_api_version_normalizes_matching_records_only() -> None:
    from src.adapters.base import AdapterRoutingError

    adapter = NoApiVersionAdapter()
    assert adapter.metadata.api_version is None
    payload = {"market_id": "m", "title": "Title", "status": "open"}
    row = adapter.normalize_market({**envelope(payload), "api_version": None})
    assert row["market_id"] == "m"
    with pytest.raises(AdapterRoutingError):
        adapter.normalize_market(envelope(payload))
    with pytest.raises(AdapterRoutingError):
        MockVenueAdapter().normalize_market({**envelope(payload), "api_version": None})


@pytest.mark.parametrize("changes", [{"venue": 1}, {"api_version": b"1"}])
def test_malformed_identity_is_an_envelope_error_not_a_routing_error(changes: dict) -> None:
    adapter = MockVenueAdapter()
    payload = {"market_id": "m", "title": "Title", "status": "open"}
    with pytest.raises(NormalizationError) as caught:
        adapter.normalize_market({**envelope(payload), **changes})
    assert caught.value.dataset == "silver.markets"


@pytest.mark.parametrize("book", [False, True])
def test_valid_readonly_envelope_normalizes_like_a_dict(book: bool) -> None:
    # Owner decision (2026-11-13): a valid read-only proxy over a plain dict normalizes.
    adapter = MockVenueAdapter()
    payload = (
        {
            "type": "delta",
            "delta_id": "d",
            "market_id": "mock-1",
            "outcome_id": "yes",
            "side": "bid",
            "price": "0.4",
            "quantity": "1",
            "event_time": WHEN.isoformat(),
            "received_at": WHEN.isoformat(),
        }
        if book
        else {"trade_id": "t", "market_id": "m", "price": "0.5", "quantity": "1"}
    )
    raw = envelope(payload)
    normalize = adapter.normalize_book_event if book else adapter.normalize_trade
    assert normalize(MappingProxyType(raw)) == normalize(raw)


def test_trusted_proxy_copy_runs_no_key_hooks_before_rejecting_untrusted_keys() -> None:
    calls = []

    class HookedKey(str):
        def __hash__(self):
            calls.append(1)
            return str.__hash__(self)

    raw = envelope({})
    raw[HookedKey("extra")] = "value"
    calls.clear()
    record = MappingProxyType(raw)
    with pytest.raises(NormalizationError) as caught:
        MockVenueAdapter().normalize_trade(record)
    assert calls == []
    assert caught.value.raw_record is record
    assert caught.value.evidence_is_snapshot is False
