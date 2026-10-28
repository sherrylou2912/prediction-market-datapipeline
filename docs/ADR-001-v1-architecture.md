# ADR-001: Single-host, versioned data pipeline

Status: Accepted for v1

Date: 2026-10-14

## Context

The project must support offline research and daily taker strategies while retaining enough raw market data to reconstruct second-level order books. Historical backfills and live streams must converge without silently losing source evidence. Phase 1 runs on one host, has constrained disk capacity, and prioritizes correctness, auditability, and recovery.

## Decision

1. 在 `DATA_ROOT/bronze` 保留历史和实时来源的原始内容及接收元数据，按来源选择合适格式。已保存内容不得静默改写；未来经确认并留下审计记录后，可依生命周期规则归档或清理符合条件的文件。
2. Validate and normalize into partitioned Parquet under `DATA_ROOT/silver`. Build research products under `DATA_ROOT/gold`; retain rejected material under `DATA_ROOT/quarantine`.
3. Query local analytical files with DuckDB. Use PostgreSQL as the future ledger for run records, checkpoints, and manifests. PR 1 defines file and schema boundaries; PR 2 implements the ledger and durable commits.
4. Schedule jobs with explicit CLI commands and systemd or cron. Use structured logs and future PostgreSQL run records for observability.
5. Require versioned venue adapters to declare capabilities, API/protocol versions, keys, pagination and checkpoints, rate limits, timestamp semantics, precision, and validation rules.
6. Reserve interfaces for Iceberg and ClickHouse but do not adopt them in v1. Do not deploy Kafka in v1.

## Reasons

- Append-only Bronze preserves the original evidence needed to investigate a bad normalization, schema change, or source correction. It also makes replay possible.
- 分区 Parquet 与 DuckDB 适合在单机扫描和关联数据，不需要独立数据仓库；未来可用本地查询服务支持 HTML 看板。
- PostgreSQL provides a transactional ledger for checkpoint advancement and manifests; files remain the data plane. This makes recovery rules explicit.
- CLI scheduling is easier to inspect and recover at the current scale. A larger orchestrator can be adopted after job behavior stabilizes.
- A venue adapter boundary keeps protocol churn out of storage and canonical transformations.
- Kafka, Iceberg, and ClickHouse would add operational and migration cost before this workload requires them.

## Consequences

- A writer must enforce its assigned data layer, and a later durable writer must pair files with manifests before advancing checkpoints.
- Every canonical row needs provenance; every Gold product needs input manifest references and point-in-time semantics.
- Capacity checks run before creating a v1 data layout. Operators must provision adequate space or consciously set a lower threshold for controlled tests.
- Existing legacy indexers remain isolated until migrated through the adapter and writer interfaces.

## References

- `agent/PROJECT.md` sections 3 through 9 and 11
- `docs/SCHEMAS.md` version 2
