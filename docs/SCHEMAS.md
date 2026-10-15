# Data Contracts v2

This document defines the v1 pipeline's version 2 contracts. The former venue-specific Parquet layouts are legacy inputs, not canonical Silver schemas. `PROJECT.md` is authoritative for architecture and data layout.

## Storage and version rules

- All paths are relative to configured `DATA_ROOT`. Bronze is append-only JSONL.zst or Parquet.zstd; Silver and Gold are partitioned Parquet with zstd compression.
- `schema_version` is `2.0.0` in every row below. Changes to field meaning, type, or nullability require a new version. Unknown fields are rejected.
- `utc_datetime` is a timezone-aware UTC Python `datetime`, stored as Parquet `timestamp[us, tz=UTC]`. Naive timestamps are invalid.
- `decimal` is a finite Python `Decimal`, stored as Parquet `decimal128(28, 10)`. Prices and payouts lie in `[0, 1]`; quantities, volumes, counts, and durations are nonnegative.
- `json` is valid JSON text. Bronze `raw_payload` preserves the source message's JSON text. `source_manifest_ids` is a nonempty JSON array of manifest identifiers.
- A `?` suffix marks a nullable field. Nullable fields must still be present with `null` when unavailable. Primary-key fields are required and nonempty. File-wide uniqueness is checked by the PR 4 validation gate.
- Silver rows carry `bronze_run_id` and `bronze_record_index` for provenance. Gold rows carry `source_manifest_ids`. A Gold calculation may use only information available at its `as_of` or `observation_time`.

## Dataset meanings

| Dataset | Meaning |
| --- | --- |
| `bronze.raw` | One source message, partitioned by venue, source, and ingestion date. |
| `silver.events` | Canonical event metadata. |
| `silver.markets` | Market metadata versions. |
| `silver.outcomes` | Tradable outcomes. |
| `silver.market_states` | Time-varying market state. |
| `silver.trades` | Canonical executions. |
| `silver.book_snapshots` | Full source book images. |
| `silver.book_deltas` | Source book changes. |
| `silver.settlements` | Final payout observations. |
| `gold.market_daily` | Daily research aggregates. |
| `gold.market_1s` | One-second BBO, depth, activity, latency, and gap features. |
| `gold.liquidity_features` | Point-in-time liquidity features. |
| `gold.training_datasets` | Reproducible feature and label rows. |

## Machine-readable contract

This JSON block is the field-level source of truth. Every dataset has a primary key and an ordered field map. Tests compare it with the Python schema registry.

```json
{
  "version": "2.0.0",
  "datasets": {
    "bronze.raw": {
      "primary_key": [
        "run_id",
        "record_index"
      ],
      "fields": {
        "run_id": "str",
        "record_index": "int",
        "venue": "str",
        "source": "str",
        "message_type": "str",
        "source_event_id": "str?",
        "event_time": "utc_datetime?",
        "received_at": "utc_datetime",
        "ingested_at": "utc_datetime",
        "sequence": "int?",
        "api_version": "str",
        "protocol_version": "str?",
        "schema_version": "str",
        "raw_payload": "json"
      }
    },
    "silver.events": {
      "primary_key": [
        "venue",
        "event_id",
        "observed_at"
      ],
      "fields": {
        "venue": "str",
        "event_id": "str",
        "title": "str",
        "observed_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.markets": {
      "primary_key": [
        "venue",
        "market_id",
        "observed_at"
      ],
      "fields": {
        "venue": "str",
        "market_id": "str",
        "event_id": "str?",
        "title": "str",
        "status": "str",
        "open_at": "utc_datetime?",
        "close_at": "utc_datetime?",
        "observed_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.outcomes": {
      "primary_key": [
        "venue",
        "outcome_id",
        "observed_at"
      ],
      "fields": {
        "venue": "str",
        "outcome_id": "str",
        "market_id": "str",
        "label": "str",
        "observed_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.market_states": {
      "primary_key": [
        "venue",
        "market_id",
        "observed_at"
      ],
      "fields": {
        "venue": "str",
        "market_id": "str",
        "status": "str",
        "best_bid": "decimal?",
        "best_ask": "decimal?",
        "observed_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.trades": {
      "primary_key": [
        "venue",
        "trade_id"
      ],
      "fields": {
        "venue": "str",
        "trade_id": "str",
        "market_id": "str",
        "outcome_id": "str?",
        "price": "decimal",
        "quantity": "decimal",
        "taker_side": "str?",
        "event_time": "utc_datetime",
        "observed_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.book_snapshots": {
      "primary_key": [
        "venue",
        "snapshot_id"
      ],
      "fields": {
        "venue": "str",
        "snapshot_id": "str",
        "market_id": "str",
        "outcome_id": "str",
        "source_sequence": "int?",
        "bids": "json",
        "asks": "json",
        "event_time": "utc_datetime",
        "received_at": "utc_datetime",
        "recovery": "bool",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.book_deltas": {
      "primary_key": [
        "venue",
        "delta_id"
      ],
      "fields": {
        "venue": "str",
        "delta_id": "str",
        "market_id": "str",
        "outcome_id": "str",
        "source_sequence": "int?",
        "side": "str",
        "price": "decimal",
        "quantity": "decimal",
        "event_time": "utc_datetime",
        "received_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "silver.settlements": {
      "primary_key": [
        "venue",
        "market_id",
        "outcome_id",
        "observed_at"
      ],
      "fields": {
        "venue": "str",
        "market_id": "str",
        "outcome_id": "str",
        "payout": "decimal",
        "settled_at": "utc_datetime",
        "observed_at": "utc_datetime",
        "bronze_run_id": "str",
        "bronze_record_index": "int",
        "schema_version": "str"
      }
    },
    "gold.market_daily": {
      "primary_key": [
        "venue",
        "market_id",
        "day",
        "as_of"
      ],
      "fields": {
        "venue": "str",
        "market_id": "str",
        "day": "str",
        "volume": "decimal",
        "trade_count": "int",
        "as_of": "utc_datetime",
        "source_manifest_ids": "json",
        "schema_version": "str"
      }
    },
    "gold.market_1s": {
      "primary_key": [
        "venue",
        "market_id",
        "outcome_id",
        "second"
      ],
      "fields": {
        "venue": "str",
        "market_id": "str",
        "outcome_id": "str",
        "second": "utc_datetime",
        "best_bid": "decimal?",
        "best_ask": "decimal?",
        "spread": "decimal?",
        "mid": "decimal?",
        "microprice": "decimal?",
        "bid_depth_top_n": "decimal?",
        "ask_depth_top_n": "decimal?",
        "imbalance": "decimal?",
        "last_trade_price": "decimal?",
        "rolling_volume": "decimal",
        "update_count": "int",
        "book_age_ms": "int?",
        "receive_latency_ms": "int?",
        "gap": "bool",
        "recovery": "bool",
        "as_of": "utc_datetime",
        "source_manifest_ids": "json",
        "schema_version": "str"
      }
    },
    "gold.liquidity_features": {
      "primary_key": [
        "venue",
        "market_id",
        "outcome_id",
        "observation_time"
      ],
      "fields": {
        "venue": "str",
        "market_id": "str",
        "outcome_id": "str",
        "observation_time": "utc_datetime",
        "spread": "decimal?",
        "depth_top_n": "decimal?",
        "imbalance": "decimal?",
        "source_manifest_ids": "json",
        "schema_version": "str"
      }
    },
    "gold.training_datasets": {
      "primary_key": [
        "dataset_name",
        "venue",
        "market_id",
        "observation_time"
      ],
      "fields": {
        "dataset_name": "str",
        "venue": "str",
        "market_id": "str",
        "observation_time": "utc_datetime",
        "features": "json",
        "max_feature_event_time": "utc_datetime",
        "label": "decimal?",
        "label_available_at": "utc_datetime?",
        "source_manifest_ids": "json",
        "schema_version": "str"
      }
    }
  }
}
```

## Validation boundary

The PR 1 row validator checks exact field shape, types, required values, schema version, basic numeric ranges, UTC timestamps, JSON arrays, and training feature time bounds. Bronze preserves the source payload even if downstream validation fails. The PR 4 gate will check file-wide key uniqueness, referential integrity, coverage, and venue-specific quality rules; failures go to `quarantine/` with reasons. Stream sequence gaps must be represented in raw events and reflected by `gold.market_1s.gap`, never silently interpolated.
