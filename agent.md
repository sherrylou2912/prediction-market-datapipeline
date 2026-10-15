# AGENTS.md

Project: prediction-market-data-pipeline.
Single source of truth: PROJECT-EN.md (authoritative) / PROJECT.md.

## Hard rules
1. All venue integrations go through the `VenueAdapter` interface.
   No venue-specific logic outside adapters.
2. No silent failures: errors are logged, quarantined, or raised.
   Never `except: pass`, never silently drop rows.
3. Checkpoints advance only after: file durably written + validated +
   registered in manifest.
4. Anomalous data goes to `quarantine/`, never silently into Silver.
5. Secrets from environment only. Never in code, logs, prompts, or docs.
6. New dependencies require human approval.
7. Every PR updates the docs it affects
   (PROJECT.md, schemas, docstrings, CHANGELOG).

## Conventions
- Python 3.9+, `uv` for env/deps, `ruff` for lint/format (line-length 120).
- Data root from `DATA_ROOT` config; never hardcode `data/...` paths.
- Storage: append-only files (JSONL.zst / Parquet.zstd); ledger in PostgreSQL.
- Tests: `uv run pytest tests/ -v`; new behavior needs tests.

## Architecture boundaries
- Bronze: as-received, immutable. Silver: canonical, validated.
  Gold: purpose-built products.
- Adding a venue = implement an adapter only.
  Do not touch storage / validation / preprocessing.
