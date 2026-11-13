"""Deterministic, network-free venue adapter used to exercise the contract."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from src.adapters.base import (
    CAPABILITIES,
    AdapterMetadata,
    NormalizedBookEvent,
    Page,
    RawRecord,
    SourceDataError,
    VenueAdapter,
    parse_utc_timestamp,
)
from src.data_schema.contracts import SCHEMA_VERSION


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise SourceDataError("decimal field must be a number or string")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise SourceDataError("invalid decimal value") from exc


def _json_decimal(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _optional_time(payload: RawRecord, name: str) -> Any:
    value = payload.get(name)
    return None if value is None else parse_utc_timestamp(value)


def _optional_text(payload: RawRecord, name: str) -> Any:
    value = payload.get(name)
    if value is not None and not isinstance(value, str):
        raise SourceDataError(f"source field {name} must be text")
    return value


def _field(payload: RawRecord, name: str) -> Any:
    try:
        return payload[name]
    except KeyError as exc:
        raise SourceDataError(f"missing source field {name}") from exc


class MockVenueAdapter(VenueAdapter):
    _WHEN = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            capabilities=CAPABILITIES,
            primary_keys={
                "markets": ("market_id",),
                "trades": ("trade_id",),
                "settlements": ("market_id", "outcome_id"),
                "book_snapshots": ("snapshot_id",),
                "book_deltas": ("delta_id",),
                "events": ("event_id",),
                "outcomes": ("market_id", "outcome_id"),
                "market_states": ("market_id", "received_at"),
            },
            pagination_checkpoint_semantics="Query-bound offset cursor; one item per page; time range [start, end).",
            rate_limits={"requests_per_second": 1000},
            timestamp_semantics="Source timestamps are ISO UTC; market_states identity uses Bronze received_at.",
            precision={"price": "decimal(28,10)", "quantity": "decimal(28,10)"},
            venue="mock",
            api_version="1",
            protocol_version=None,
        )

    @classmethod
    def _markets(cls) -> tuple[RawRecord, ...]:
        return tuple(
            {
                "market_id": f"mock-{n}",
                "title": f"Mock market {n}?",
                "status": "open",
                "updated_at": (cls._WHEN + timedelta(days=n - 1)).isoformat(),
            }
            for n in (1, 2, 3)
        )

    @classmethod
    def _trades(cls) -> tuple[RawRecord, ...]:
        return tuple(
            {
                "trade_id": f"mock-trade-{n}",
                "market_id": f"mock-{n}",
                "price": "0.65",
                "quantity": "2",
                "event_time": (cls._WHEN + timedelta(days=n - 1)).isoformat(),
            }
            for n in (1, 2, 3)
        )

    @staticmethod
    def _page(records: Sequence[RawRecord], cursor: str | None, query: str) -> Page[RawRecord]:
        if cursor is None:
            index = 0
        else:
            try:
                state = json.loads(cursor)
            except (TypeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid mock cursor") from exc
            if (
                not isinstance(state, dict)
                or set(state) != {"query", "offset"}
                or state["query"] != query
                or type(state["offset"]) is not int
                or state["offset"] < 0
            ):
                raise ValueError("Mock cursor does not match query")
            index = state["offset"]
        if index >= len(records) and index != 0:
            raise ValueError("Mock cursor beyond end of results")
        next_index = index + 1
        next_cursor = (
            json.dumps({"query": query, "offset": next_index}, separators=(",", ":"))
            if next_index < len(records)
            else None
        )
        return Page(tuple(records[index:next_index]), next_cursor)

    def _discover_markets(self, cursor: str | None) -> Page[RawRecord]:
        return self._page(self._markets(), cursor, "discover_markets")

    def _backfill_markets(self, start: datetime, end: datetime, cursor: str | None) -> Page[RawRecord]:
        return self._page(
            [r for r in self._markets() if start <= parse_utc_timestamp(r["updated_at"]) < end],
            cursor,
            f"backfill_markets:{start.isoformat()}:{end.isoformat()}",
        )

    def _backfill_trades(self, start: datetime, end: datetime, cursor: str | None) -> Page[RawRecord]:
        return self._page(
            [r for r in self._trades() if start <= parse_utc_timestamp(r["event_time"]) < end],
            cursor,
            f"backfill_trades:{start.isoformat()}:{end.isoformat()}",
        )

    def _fetch_settlements(self, start: datetime, end: datetime, cursor: str | None) -> Page[RawRecord]:
        records = (
            {
                "market_id": "mock-1",
                "outcome_id": "yes",
                "payout": "1",
                "settled_at": self._WHEN.isoformat(),
            },
        )
        return self._page(
            [r for r in records if start <= parse_utc_timestamp(r["settled_at"]) < end],
            cursor,
            f"fetch_settlements:{start.isoformat()}:{end.isoformat()}",
        )

    def _stream_market_data(self, market_ids: Sequence[str]) -> Iterator[RawRecord]:
        if "mock-1" in market_ids:
            yield {
                "type": "delta",
                "delta_id": "mock-delta-1",
                "market_id": "mock-1",
                "outcome_id": "yes",
                "source_sequence": 1,
                "side": "bid",
                "price": "0.65",
                "quantity": "4",
                "event_time": self._WHEN.isoformat(),
            }

    @staticmethod
    def _common(envelope: RawRecord) -> dict[str, Any]:
        return {
            "venue": envelope["venue"],
            "bronze_run_id": envelope["run_id"],
            "bronze_record_index": envelope["record_index"],
            "schema_version": SCHEMA_VERSION,
        }

    def _normalize_market(self, p: RawRecord, e: RawRecord) -> Mapping[str, Any]:
        return {
            **self._common(e),
            "market_id": _field(p, "market_id"),
            "event_id": None,
            "title": _field(p, "title"),
            "description": p.get("description"),
            "settlement_rules": p.get("settlement_rules"),
            "status": _field(p, "status"),
            "scheduled_open_at": _optional_time(p, "scheduled_open_at"),
            "scheduled_close_at": _optional_time(p, "scheduled_close_at"),
            "actual_open_at": _optional_time(p, "actual_open_at"),
            "actual_close_at": _optional_time(p, "actual_close_at"),
            # Mock open_at/close_at do not say whether they are scheduled or actual: keep the text.
            "source_open_time_text": _optional_text(p, "open_at"),
            "source_close_time_text": _optional_text(p, "close_at"),
            "observed_at": e["received_at"],
        }

    def _normalize_trade(self, p: RawRecord, e: RawRecord) -> Mapping[str, Any]:
        return {
            **self._common(e),
            "trade_id": _field(p, "trade_id"),
            "market_id": _field(p, "market_id"),
            "outcome_id": None,
            "price": _decimal(_field(p, "price")),
            "quantity": _decimal(_field(p, "quantity")),
            "taker_side": None,
            "event_time": parse_utc_timestamp(p["event_time"]) if p.get("event_time") is not None else None,
            "observed_at": e["received_at"],
        }

    def _normalize_book_event(self, p: RawRecord, e: RawRecord) -> NormalizedBookEvent:
        if p.get("type") not in ("snapshot", "delta"):
            raise SourceDataError("book event type must be snapshot or delta")
        row = {
            **self._common(e),
            "market_id": _field(p, "market_id"),
            "outcome_id": _field(p, "outcome_id"),
            "source_sequence": p.get("source_sequence"),
            "event_time": parse_utc_timestamp(p["event_time"]) if p.get("event_time") is not None else None,
            "received_at": e["received_at"],
        }
        if _field(p, "type") == "snapshot":
            return NormalizedBookEvent(
                "silver.book_snapshots",
                {
                    **row,
                    "snapshot_id": _field(p, "snapshot_id"),
                    "bids": json.dumps(_field(p, "bids"), default=_json_decimal),
                    "asks": json.dumps(_field(p, "asks"), default=_json_decimal),
                    "recovery": _field(p, "recovery"),
                },
            )
        return NormalizedBookEvent(
            "silver.book_deltas",
            {
                **row,
                "delta_id": _field(p, "delta_id"),
                "side": _field(p, "side"),
                "price": _decimal(_field(p, "price")),
                "quantity": _decimal(_field(p, "quantity")),
            },
        )

    def _normalize_settlement(self, p: RawRecord, e: RawRecord) -> Mapping[str, Any]:
        return {
            **self._common(e),
            "market_id": _field(p, "market_id"),
            "outcome_id": _field(p, "outcome_id"),
            "payout": _decimal(_field(p, "payout")),
            "settled_at": _optional_time(p, "settled_at"),
            "observed_at": e["received_at"],
        }

    def _normalize_event(self, p: RawRecord, e: RawRecord) -> Mapping[str, Any]:
        return {
            **self._common(e),
            "event_id": _field(p, "event_id"),
            "title": _field(p, "title"),
            "observed_at": e["received_at"],
        }

    def _normalize_outcome(self, p: RawRecord, e: RawRecord) -> Mapping[str, Any]:
        return {
            **self._common(e),
            "outcome_id": _field(p, "outcome_id"),
            "market_id": _field(p, "market_id"),
            "label": _field(p, "label"),
            "description": p.get("description"),
            "observed_at": e["received_at"],
        }

    def _normalize_market_state(self, p: RawRecord, e: RawRecord) -> Mapping[str, Any]:
        return {
            **self._common(e),
            "market_id": _field(p, "market_id"),
            "status": _field(p, "status"),
            "best_bid": _decimal(_field(p, "best_bid")) if p.get("best_bid") is not None else None,
            "best_ask": _decimal(_field(p, "best_ask")) if p.get("best_ask") is not None else None,
            "observed_at": e["received_at"],
        }
