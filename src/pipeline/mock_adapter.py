"""Deterministic, network-free venue adapter used to prove the interface."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.pipeline.adapter import AdapterMetadata, Page, RawRecord, VenueAdapter
from src.pipeline.contracts import SCHEMA_VERSION, validate_record


class MockVenueAdapter(VenueAdapter):
    _WHEN = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    @property
    def metadata(self) -> AdapterMetadata:
        return AdapterMetadata(
            capabilities=frozenset({"markets", "trades", "settlements", "book_stream"}),
            api_protocol_version="mock-api/1; mock-protocol/1",
            primary_keys={"markets": ("market_id",), "trades": ("trade_id",), "book": ("delta_id",)},
            pagination_checkpoint_semantics="One finite page; no cursor advancement.",
            rate_limits={"requests_per_second": 1000},
            timestamp_semantics="All source timestamps are aware UTC datetimes.",
            precision={"price": "decimal(28,10)", "quantity": "decimal(28,10)"},
            validation_rules=("Canonical v2 row validation",),
        )

    def discover_markets(self, cursor: str | None = None) -> Page[RawRecord]:
        return Page(
            items=(
                {
                    "market_id": "mock-1",
                    "title": "Will the mock test pass?",
                    "status": "open",
                    "observed_at": self._WHEN,
                    "bronze_run_id": "mock-run",
                    "bronze_record_index": 0,
                },
            )
        )

    def backfill_markets(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        return self.discover_markets(cursor)

    def backfill_trades(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        return Page(
            items=(
                {
                    "trade_id": "mock-trade-1",
                    "market_id": "mock-1",
                    "price": "0.65",
                    "quantity": "2",
                    "event_time": self._WHEN,
                    "observed_at": self._WHEN,
                    "bronze_run_id": "mock-run",
                    "bronze_record_index": 1,
                },
            )
        )

    def fetch_settlements(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        return Page(items=())

    def stream_market_data(self, market_ids: Sequence[str]) -> Iterator[RawRecord]:
        if "mock-1" in market_ids:
            yield {
                "delta_id": "mock-delta-1",
                "market_id": "mock-1",
                "outcome_id": "yes",
                "source_sequence": 1,
                "side": "bid",
                "price": "0.65",
                "quantity": "4",
                "event_time": self._WHEN,
                "received_at": self._WHEN,
                "bronze_run_id": "mock-run",
                "bronze_record_index": 2,
            }

    def normalize_market(self, raw: RawRecord) -> Mapping[str, Any]:
        row = {
            "venue": "mock",
            "market_id": raw["market_id"],
            "event_id": None,
            "title": raw["title"],
            "status": raw["status"],
            "open_at": None,
            "close_at": None,
            "observed_at": raw["observed_at"],
            "bronze_run_id": raw["bronze_run_id"],
            "bronze_record_index": raw["bronze_record_index"],
            "schema_version": SCHEMA_VERSION,
        }
        validate_record("silver.markets", row)
        return row

    def normalize_trade(self, raw: RawRecord) -> Mapping[str, Any]:
        row = {
            "venue": "mock",
            "trade_id": raw["trade_id"],
            "market_id": raw["market_id"],
            "outcome_id": None,
            "price": Decimal(raw["price"]),
            "quantity": Decimal(raw["quantity"]),
            "taker_side": None,
            "event_time": raw["event_time"],
            "observed_at": raw["observed_at"],
            "bronze_run_id": raw["bronze_run_id"],
            "bronze_record_index": raw["bronze_record_index"],
            "schema_version": SCHEMA_VERSION,
        }
        validate_record("silver.trades", row)
        return row

    def normalize_book_event(self, raw: RawRecord) -> Mapping[str, Any]:
        row = {
            "venue": "mock",
            "delta_id": raw["delta_id"],
            "market_id": raw["market_id"],
            "outcome_id": raw["outcome_id"],
            "source_sequence": raw["source_sequence"],
            "side": raw["side"],
            "price": Decimal(raw["price"]),
            "quantity": Decimal(raw["quantity"]),
            "event_time": raw["event_time"],
            "received_at": raw["received_at"],
            "bronze_run_id": raw["bronze_run_id"],
            "bronze_record_index": raw["bronze_record_index"],
            "schema_version": SCHEMA_VERSION,
        }
        validate_record("silver.book_deltas", row)
        return row
