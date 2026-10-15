"""The eight-operation interface and declarations required of every venue."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Generic, TypeVar

RawRecord = Mapping[str, Any]
CanonicalRecord = Mapping[str, Any]
T = TypeVar("T")


@dataclass(frozen=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class AdapterMetadata:
    capabilities: frozenset[str]
    api_protocol_version: str
    primary_keys: Mapping[str, tuple[str, ...]]
    pagination_checkpoint_semantics: str
    rate_limits: Mapping[str, int]
    timestamp_semantics: str
    precision: Mapping[str, str]
    validation_rules: tuple[str, ...]

    def __post_init__(self) -> None:
        declarations = (
            self.capabilities,
            self.api_protocol_version,
            self.primary_keys,
            self.pagination_checkpoint_semantics,
            self.rate_limits,
            self.timestamp_semantics,
            self.precision,
            self.validation_rules,
        )
        if any(not value for value in declarations):
            raise ValueError("All eight venue adapter declarations must be nonempty.")
        if any(limit <= 0 for limit in self.rate_limits.values()):
            raise ValueError("Venue adapter rate limits must be positive.")


class VenueAdapter(ABC):
    """Venue contract: failed reads or normalization must raise, never return false success.

    An empty page is valid only when the source genuinely has no records. Future
    orchestration must record raised errors and leave checkpoints unchanged;
    malformed source records must retain their evidence for quarantine.
    """

    @property
    @abstractmethod
    def metadata(self) -> AdapterMetadata:
        """Declare capabilities, versions, keys, cursors, limits, time, precision, and validation."""

    @abstractmethod
    def discover_markets(self, cursor: str | None = None) -> Page[RawRecord]:
        """Discover source markets without writing data."""

    @abstractmethod
    def backfill_markets(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        """Read source market history within a time range."""

    @abstractmethod
    def backfill_trades(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        """Read source trades within a time range."""

    @abstractmethod
    def fetch_settlements(self, start: datetime, end: datetime, cursor: str | None = None) -> Page[RawRecord]:
        """Read source settlement observations."""

    @abstractmethod
    def stream_market_data(self, market_ids: Sequence[str]) -> Iterator[RawRecord]:
        """Yield source stream messages for selected markets."""

    @abstractmethod
    def normalize_market(self, raw: RawRecord) -> CanonicalRecord:
        """Map one source market to the Silver market contract."""

    @abstractmethod
    def normalize_trade(self, raw: RawRecord) -> CanonicalRecord:
        """Map one source trade to the Silver trade contract."""

    @abstractmethod
    def normalize_book_event(self, raw: RawRecord) -> CanonicalRecord:
        """Map one source book event to a Silver snapshot or delta contract."""
