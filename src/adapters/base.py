"""Venue interfaces, capability declarations, and Bronze-to-Silver boundaries."""

from __future__ import annotations

import copy
import gc
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Generic, TypeVar

from src.data_schema.contracts import ContractError, parse_json_strict, validate_record

RawRecord = Mapping[str, Any]
CanonicalRecord = Mapping[str, Any]
T = TypeVar("T")
CAPABILITIES = frozenset({"markets", "trades", "settlements", "book_stream", "events", "outcomes", "market_states"})

CAPABILITY_KEYS = {
    "markets": frozenset({"markets"}),
    "trades": frozenset({"trades"}),
    "settlements": frozenset({"settlements"}),
    "book_stream": frozenset({"book_snapshots", "book_deltas"}),
    "events": frozenset({"events"}),
    "outcomes": frozenset({"outcomes"}),
    "market_states": frozenset({"market_states"}),
}


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class NormalizedBookEvent:
    dataset: str
    record: CanonicalRecord


class UnsupportedCapabilityError(NotImplementedError):
    """The adapter declares that the requested capability is unavailable."""


class AdapterRoutingError(ValueError):
    """The Bronze envelope was routed to the wrong adapter or version."""


class AdapterOutputError(ValueError):
    """An adapter returned a Silver row inconsistent with its Bronze input."""


class SourceDataError(ValueError):
    """A source-specific parser identified malformed input rather than a code defect."""


def _require_trusted_mapping(value: RawRecord) -> None:
    if type(value) is dict:
        return
    if type(value) is MappingProxyType:
        # A proxy can wrap a custom mapping with arbitrary access methods.
        # Only trust a proxy when its single referent is an exact built-in dict;
        # otherwise retain the original as non-snapshot evidence.
        referents = gc.get_referents(value)
        if len(referents) == 1 and type(referents[0]) is dict:
            return
    raise TypeError("Cannot verify evidence mapping has trusted access behavior")


def _copy_raw_record(raw: RawRecord) -> dict:
    """Copy evidence only when its mappings and values have trusted copy semantics.

    Plain dicts and read-only proxies over plain dicts are copied (proxies become
    dicts); anything else is rejected so callers keep the original reference and
    mark it as not an independent snapshot.
    """
    _require_trusted_mapping(raw)
    # copy() of a trusted dict or proxy copies without rehashing keys, so no
    # key hook runs before the type checks below.
    record = raw.copy()
    seen: set[int] = set()
    proxies = []
    memo: dict[int, Any] = {}
    pending: list[Any] = [record]
    while pending:
        value = pending.pop()
        if id(value) in seen:
            continue
        seen.add(id(value))
        if type(value) in (str, int, bool, float, bytes, type(None), Decimal):
            continue
        if type(value) is datetime:
            if value.tzinfo is not None and value.tzinfo is not timezone.utc:
                raise TypeError("Cannot verify evidence timestamp timezone is immutable")
        elif type(value) in (dict, MappingProxyType):
            if type(value) is MappingProxyType:
                _require_trusted_mapping(value)
                proxies.append(value)
                memo[id(value)] = {}
            for key, item in value.items():
                pending.extend((key, item))
        elif type(value) in (list, tuple, set, frozenset):
            pending.extend(value)
        else:
            # User-defined copying hooks can return the original mutable value
            # or even replace a provenance field with a different value.
            raise TypeError("Cannot verify independent evidence copy for this value type")
    # deepcopy cannot copy a mappingproxy; pre-seed each with a copied dict.
    for proxy in proxies:
        copied = memo[id(proxy)]
        for key, value in proxy.items():
            copied[copy.deepcopy(key, memo)] = copy.deepcopy(value, memo)
    return copy.deepcopy(record, memo)


class NormalizationError(ValueError):
    """A malformed record and its evidence, with snapshot status made explicit."""

    def __init__(
        self,
        dataset: str,
        reason: str,
        raw_record: RawRecord,
        *,
        evidence_copy_error_type: str | None = None,
        _already_snapshot: bool = False,
    ):
        self.dataset = dataset
        self.reason = reason
        self.evidence_copy_error_type = evidence_copy_error_type
        if _already_snapshot:
            self.raw_record = raw_record
        elif evidence_copy_error_type is None:
            try:
                self.raw_record = _copy_raw_record(raw_record)
            except Exception as exc:
                self.raw_record = raw_record
                self.evidence_copy_error_type = type(exc).__name__
        else:
            self.raw_record = raw_record
        self.evidence_is_snapshot = self.evidence_copy_error_type is None
        suffix = "" if self.evidence_is_snapshot else "; evidence is the original reference, not a snapshot"
        super().__init__(f"{dataset}: {reason}{suffix}")


def _snapshot_or_error(dataset: str, raw: RawRecord) -> dict:
    try:
        return _copy_raw_record(raw)
    except Exception as exc:
        raise NormalizationError(
            dataset, "Cannot copy Bronze evidence", raw, evidence_copy_error_type=type(exc).__name__
        ) from exc


def parse_utc_timestamp(value: str) -> datetime:
    """Parse ISO 8601 including Z consistently on Python 3.9; require UTC."""
    if not isinstance(value, str):
        raise SourceDataError("timestamp must be an ISO string")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise SourceDataError("timestamp must be valid ISO 8601") from exc
    if parsed.tzinfo is not timezone.utc:
        raise SourceDataError("timestamp must be UTC")
    return parsed


@dataclass(frozen=True)
class AdapterMetadata:
    capabilities: frozenset[str]
    primary_keys: Mapping[str, tuple[str, ...]]
    pagination_checkpoint_semantics: str
    rate_limits: Mapping[str, int]
    timestamp_semantics: str
    precision: Mapping[str, str]
    venue: str
    # None when the source has no API version or it is not applicable; never invented.
    api_version: str | None
    protocol_version: str | None

    def __post_init__(self) -> None:
        if not all(
            (
                self.capabilities,
                self.primary_keys,
                self.pagination_checkpoint_semantics,
                self.rate_limits,
                self.timestamp_semantics,
                self.precision,
            )
        ):
            raise ValueError("All required venue adapter declarations must be nonempty.")
        if not isinstance(self.capabilities, frozenset) or not self.capabilities <= CAPABILITIES:
            raise ValueError("Unknown or invalid venue adapter capabilities.")
        for value in (
            self.pagination_checkpoint_semantics,
            self.timestamp_semantics,
            self.venue,
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Adapter text declarations must be nonempty strings.")
        if not isinstance(self.primary_keys, Mapping) or any(
            not isinstance(k, str)
            or not k.strip()
            or not isinstance(v, tuple)
            or not v
            or any(not isinstance(field, str) or not field.strip() for field in v)
            for k, v in self.primary_keys.items()
        ):
            raise ValueError("Adapter primary keys must contain nonempty field tuples.")
        required = set().union(*(CAPABILITY_KEYS[capability] for capability in self.capabilities))
        if set(self.primary_keys) != required:
            raise ValueError("Adapter primary keys must match declared capabilities")
        for name in ("api_version", "protocol_version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"Adapter {name} must be a nonempty string or None")
        if not isinstance(self.rate_limits, Mapping) or any(
            not isinstance(k, str) or not k.strip() or type(v) is not int or v <= 0 for k, v in self.rate_limits.items()
        ):
            raise ValueError("Venue adapter rate limits must be positive integers.")
        if not isinstance(self.precision, Mapping) or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in self.precision.items()
        ):
            raise ValueError("Adapter precision must contain nonempty strings.")
        for field in ("primary_keys", "rate_limits", "precision"):
            object.__setattr__(self, field, MappingProxyType(dict(getattr(self, field))))


class VenueAdapter(ABC):
    """Collectors return source records; orchestration persists bronze.raw before normalization.

    Normalizers receive the persisted Bronze envelope. JSON source messages may
    be supplied as text or original bytes; provenance comes from the envelope.
    """

    @property
    @abstractmethod
    def metadata(self) -> AdapterMetadata: ...

    def _require(self, capability: str) -> None:
        if capability not in self.metadata.capabilities:
            raise UnsupportedCapabilityError(f"Unsupported capability: {capability}")

    @staticmethod
    def _range(start: datetime, end: datetime) -> None:
        if (
            not isinstance(start, datetime)
            or not isinstance(end, datetime)
            or start.tzinfo is not timezone.utc
            or end.tzinfo is not timezone.utc
            or start >= end
        ):
            raise ValueError("start and end must use timezone.utc and satisfy start < end")

    def discover_markets(self, cursor: str | None = None) -> Page[RawRecord]:
        self._require("markets")
        return self._discover_markets(cursor)

    def backfill_markets(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        self._require("markets")
        self._range(start, end)
        return self._backfill_markets(start, end, cursor)

    def backfill_trades(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        self._require("trades")
        self._range(start, end)
        return self._backfill_trades(start, end, cursor)

    def fetch_settlements(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        self._require("settlements")
        self._range(start, end)
        return self._fetch_settlements(start, end, cursor)

    def stream_market_data(self, market_ids: Sequence[str]) -> Iterator[RawRecord]:
        self._require("book_stream")
        return self._stream_market_data(market_ids)

    def _payload(self, dataset: str, raw: RawRecord) -> dict:
        # Route before validating the envelope: envelope validation parses
        # raw_payload, and a record sent to the wrong adapter must not be
        # reported as a data error of this adapter's dataset.
        keys = ("venue", "api_version", "protocol_version")
        if isinstance(raw, Mapping) and all(k in raw and (raw[k] is None or type(raw[k]) is str) for k in keys):
            identity = tuple(raw[k] for k in keys)
            expected = (self.metadata.venue, self.metadata.api_version, self.metadata.protocol_version)
            if identity != expected:
                raise AdapterRoutingError(f"Bronze adapter identity mismatch: expected {expected}, got {identity}")
        try:
            # A malformed identity reaches here and is rejected by the contract;
            # a valid one has already matched this adapter.
            validate_record("bronze.raw", raw)
        except ContractError as exc:
            raise NormalizationError(dataset, str(exc), raw, _already_snapshot=True) from exc
        try:
            received, ingested = raw["received_at"], raw["ingested_at"]
            if received is not None and ingested is not None and ingested < received:
                raise SourceDataError("Bronze ingestion time is earlier than receipt time; review required")
            contents = raw["raw_payload"]
            if contents is None:
                contents = raw["raw_bytes"].decode("utf-8")
            payload = parse_json_strict(contents, "bronze.raw payload")
            if not isinstance(payload, dict):
                raise SourceDataError("raw_payload must be a JSON object")
        except (ContractError, SourceDataError, UnicodeDecodeError) as exc:
            raise NormalizationError(dataset, str(exc), raw, _already_snapshot=True) from exc
        return payload

    @staticmethod
    def _check_provenance(row: CanonicalRecord, raw: RawRecord) -> None:
        expected = {"venue": raw["venue"], "bronze_run_id": raw["run_id"], "bronze_record_index": raw["record_index"]}
        for field in ("observed_at", "received_at"):
            if field in row:
                expected[field] = raw["received_at"]
        if any(row.get(field) != value for field, value in expected.items()):
            raise AdapterOutputError("Silver provenance or observation time differs from Bronze envelope")

    def _normalize(self, dataset: str, capability: str, raw: RawRecord, method: Any) -> CanonicalRecord:
        self._require(capability)
        snapshot = _snapshot_or_error(dataset, raw)
        payload = self._payload(dataset, snapshot)
        try:
            row = method(payload, MappingProxyType(snapshot))
            validate_record(dataset, row)
        except (SourceDataError, ContractError) as exc:
            raise NormalizationError(dataset, str(exc), snapshot, _already_snapshot=True) from exc
        self._check_provenance(row, snapshot)
        return row

    def normalize_market(self, raw: RawRecord) -> CanonicalRecord:
        return self._normalize("silver.markets", "markets", raw, self._normalize_market)

    def normalize_trade(self, raw: RawRecord) -> CanonicalRecord:
        return self._normalize("silver.trades", "trades", raw, self._normalize_trade)

    def normalize_settlement(self, raw: RawRecord) -> CanonicalRecord:
        return self._normalize("silver.settlements", "settlements", raw, self._normalize_settlement)

    def normalize_event(self, raw: RawRecord) -> CanonicalRecord:
        return self._normalize("silver.events", "events", raw, self._normalize_event)

    def normalize_outcome(self, raw: RawRecord) -> CanonicalRecord:
        return self._normalize("silver.outcomes", "outcomes", raw, self._normalize_outcome)

    def normalize_market_state(self, raw: RawRecord) -> CanonicalRecord:
        return self._normalize("silver.market_states", "market_states", raw, self._normalize_market_state)

    def normalize_book_event(self, raw: RawRecord) -> NormalizedBookEvent:
        self._require("book_stream")
        snapshot = _snapshot_or_error("silver.book_events", raw)
        payload = self._payload("silver.book_events", snapshot)
        try:
            event = self._normalize_book_event(payload, MappingProxyType(snapshot))
        except SourceDataError as exc:
            raise NormalizationError("silver.book_events", str(exc), snapshot, _already_snapshot=True) from exc
        if not isinstance(event, NormalizedBookEvent) or event.dataset not in (
            "silver.book_snapshots",
            "silver.book_deltas",
        ):
            raise AdapterOutputError("Adapter returned an invalid book event dataset")
        try:
            validate_record(event.dataset, event.record)
        except ContractError as exc:
            raise NormalizationError(event.dataset, str(exc), snapshot, _already_snapshot=True) from exc
        self._check_provenance(event.record, snapshot)
        return event

    @abstractmethod
    def _discover_markets(self, cursor: str | None) -> Page[RawRecord]: ...
    @abstractmethod
    def _backfill_markets(self, start: datetime, end: datetime, cursor: str | None) -> Page[RawRecord]: ...
    @abstractmethod
    def _backfill_trades(self, start: datetime, end: datetime, cursor: str | None) -> Page[RawRecord]: ...
    @abstractmethod
    def _fetch_settlements(self, start: datetime, end: datetime, cursor: str | None) -> Page[RawRecord]: ...
    @abstractmethod
    def _stream_market_data(self, market_ids: Sequence[str]) -> Iterator[RawRecord]: ...
    @abstractmethod
    def _normalize_market(self, payload: RawRecord, envelope: RawRecord) -> CanonicalRecord: ...
    @abstractmethod
    def _normalize_trade(self, payload: RawRecord, envelope: RawRecord) -> CanonicalRecord: ...
    @abstractmethod
    def _normalize_book_event(self, payload: RawRecord, envelope: RawRecord) -> NormalizedBookEvent: ...
    @abstractmethod
    def _normalize_settlement(self, payload: RawRecord, envelope: RawRecord) -> CanonicalRecord: ...
    @abstractmethod
    def _normalize_event(self, payload: RawRecord, envelope: RawRecord) -> CanonicalRecord: ...
    @abstractmethod
    def _normalize_outcome(self, payload: RawRecord, envelope: RawRecord) -> CanonicalRecord: ...
    @abstractmethod
    def _normalize_market_state(self, payload: RawRecord, envelope: RawRecord) -> CanonicalRecord: ...
