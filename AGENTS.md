# Agent Instructions

Project: prediction-market-datapipeline.

## Authority and language

- `PROJECT.md` is the single source of truth for the v1 rebuild. Resolve conflicting code or documentation against it unless an explicit architectural decision changes it.
- Write all code, comments, docstrings, tests, and Markdown in English unless the project owner explicitly requests another language for a specific artifact. Communicate with the project owner in Chinese. The requested report under `inprocessfile/` is in Chinese.

## Hard rules

1. All new venue integrations implement `VenueAdapter`. Keep venue-specific behavior inside adapters.
2. Never silently discard data or failures. Raise, log, or quarantine them with a reason.
3. Advance a checkpoint only after its data file is durably written, validated, and registered in a manifest.
4. Send anomalous records to `quarantine/`; never silently admit them to Silver.
5. Read secrets only from the environment. Never put them in code, logs, prompts, or documentation.
6. Do not add dependencies without the project owner's approval.
7. Update affected documentation with every PR.
8. Derive all new pipeline data paths from `DATA_ROOT`. Use a layer-scoped writer for data writes.

## Conventions

- Support Python 3.9 and newer. Use `uv` for the existing environment and `ruff` for lint and format checks.
- Bronze is immutable raw data; Silver is validated canonical data; Gold is a purpose-built product.
- Use `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest tests/ -v` before delivery.
- Keep legacy indexers separate from the v1 pipeline until their respective migration PRs.
- Keep the new pipeline under `src/pipeline/`; do not use a version number as the source folder name.
