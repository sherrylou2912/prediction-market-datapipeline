# Agent Instructions

Project: prediction-market-datapipeline.

## Workflow and roles

- Start each substantive PR or task by reading `agent/PROJECT.md`, this file, the request, and the relevant role guide. These are guidance files, not automatically running agents.
- `PLANNER.md`: clarify goals and design with the owner; propose scope, blocks, and acceptance criteria. `ANALYST.md`: implement the agreed block. `REPORTER.md`: explain each completed block and its tests to the owner. `VALIDATOR.md`: independently find problems and verify their fixes.
- Handoff: Planner defines meaningful blocks with the owner → Analyst implements one block → Reporter explains it → wait for the owner's explicit confirmation before the next block. Small corrections within the current block may proceed continuously; report material changes and updated checks before requesting confirmation again. Validator reviews critical gates and the final change without fixing issues. For small tasks one agent may perform multiple roles, but a separate review context is preferred for high-risk changes; it is not proof of independence. The owner decides material design changes and merge.
- At each handoff identify the task, branch and worktree or commit, changed files, decisions, actual checks and results, failures, and unverified items. Do not treat planning, a report, or a green test as proof of production readiness.
- Preserve existing work. Before a commit inspect staged changes; after a PR is opened, review the latest head and its checks. After merge, record the merged revision, verification, limitations, and handoff. Do not claim an unrun check passed or approve, merge, deploy, or trade without the owner's authorization.

## Authority and language

- `PROJECT.md` is the single source of truth for the v1 rebuild. Resolve conflicting code or documentation against it unless an explicit architectural decision changes it.
- Communicate with the project owner in Chinese. Prefer Chinese for new or updated Markdown and human-facing explanations where practical; retain clear English identifiers and established external formats. Do not translate existing files solely to change their language.

## Hard rules

1. All new venue integrations implement `VenueAdapter`. Keep venue-specific behavior inside adapters.
2. Never silently discard data or failures. Raise, log, or quarantine them with a reason.
3. Advance a checkpoint only after its data file is durably written, validated, and registered in a manifest.
4. Send anomalous records to `quarantine/`; never silently admit them to Silver.
5. Read secrets only from the environment. Never put them in code, logs, prompts, or documentation.
6. Do not add dependencies without the project owner's approval.
7. Update affected documentation with every PR.
8. Derive all new pipeline data paths from `DATA_ROOT`. Use a layer-scoped writer for data writes.
9. Read-only task entry points call `PipelineConfig.validate_for_read()`. Write-producing task entry points call `PipelineConfig.validate_for_write()` before `DataLayout.create()` or any data write. Keep the general `check` command free of disk-space probes and write side effects.
10. Put tunable job and experiment parameters in `src/config/` instead of scattering literals through task code. Provide documented defaults only when they are safe; keep required values explicit. Validate every effective parameter, including type, range, and relationships with other parameters, before an experiment starts or data processing has side effects. Reject invalid settings immediately with a clear error. At job start, log the effective non-secret values and whether defaults or overrides were used; never log secrets.
11. Every `src/config/` change must follow `src/config/developing.md`, add only files required by the current PR, and update both `src/config/README.md` and `src/config/README_FOR_DEVELOPER.md` in the same change.

## Conventions

- Support Python 3.9 and newer. Use `uv` for the existing environment and `ruff` for lint and format checks.
- Bronze is immutable raw data; Silver is validated canonical data; Gold is a purpose-built product.
- Use `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest tests/ -v` before delivery.
- Keep legacy indexers separate from the v1 pipeline until their respective migration PRs.
- Keep documentation in the layout described by `docs/README.md`: PR-specific plans, rules, and reading progress under `docs/pr<N>/`, architecture decision records under `docs/adr/`, and legacy-workflow docs under `docs/legacy/`. Add new documents to that index.
- Keep the new pipeline under `src/`; do not use a version number as the source folder name. Put settings and validation in `src/config/`, contracts in `src/data_schema/`, data directory and writer code in `src/data_io/`, and venue implementations in `src/adapters/`.

## Owner notes

- Keep the project owner's private design notes in `docs/notes.md`.
- Write them in concise Chinese as numbered entries. State the idea, pipeline, and called functions; mark proposed functions as unimplemented.
- Never include secrets, credentials, or personal data.
