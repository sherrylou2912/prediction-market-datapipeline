# Prediction Market Data Pipeline

This repository contains a legacy prediction-market analysis workflow and the foundation of a new, versioned data pipeline. The new pipeline is designed for reproducible research, traceable source records, and recoverable data collection. `PROJECT.md` is the architecture authority.

## Current scope

The PR 1 pipeline foundation provides configuration loading, startup checks, six data layers with scoped writers, Bronze/Silver/Gold row contracts, a venue adapter interface, and a network-free mock adapter. It does not download venue data, create PostgreSQL tables, or commit files and checkpoints together. Future work begins when the project owner authorizes the next PR.

## Source layout

`src/` holds the pipeline code. Each folder has one responsibility:

| Path | Responsibility |
| --- | --- |
| `src/config/` | Load configuration and check its values and the data disk. |
| `src/config/defaults/` | Editable, version-controlled non-secret defaults. |
| `src/data_schema/` | Versioned Bronze, Silver, and Gold row contracts. |
| `src/data_io/` | Create data directories and restrict each writer to its assigned layer. |
| `src/adapters/` | Venue interface and a deterministic mock implementation. |
| `src/cli.py`, `src/__main__.py` | The `python -m src check` startup command. |
| `src/common/`, `src/indexers/`, `src/analysis/` | Existing legacy code; its migration is outside PR 1. |

There is no real data loader in PR 1. `src/data_io/` contains the directory and writer foundation for future loading work.

## Python environment and required libraries

Use Python 3.9 or newer and install `uv`. Run these commands from the repository root:

```bash
uv sync --locked --group dev
uv run python -m src check
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

Run the startup command after setting `DATA_ROOT` as described below. `uv sync --locked --group dev` creates or updates the local `.venv` from the committed lockfile and includes the test and lint tools. The `--locked` flag prevents an accidental lockfile update during installation. `.venv` is local and ignored by Git; do not edit installed packages inside it.

**Where are the required library names?** Root [`pyproject.toml`](pyproject.toml) lists runtime libraries, including `pyarrow` and `python-dotenv`, in `[project].dependencies`. The same file lists `pytest` and `ruff` in `[dependency-groups].dev`. Root [`uv.lock`](uv.lock) records the resolved package versions and transitive dependencies. To change a requirement, edit `pyproject.toml`, regenerate `uv.lock` with `uv lock`, and commit both files together. PR 1 adds no libraries.

Dependency versions are controlled, but wheel distribution is not configured: `pyproject.toml` has no build backend. Run commands from the repository root so Python can import `src` directly.

## Configure the pipeline

1. Copy `.env.example` to `.env` and set `DATA_ROOT` to an absolute path on a volume intended for pipeline data. The local `.env` is ignored by Git. The CLI reads it automatically; an exported process environment variable overrides the same key in `.env`.
2. Edit `src/config/defaults/storage.json` for the default minimum free space and `src/config/defaults/runtime.json` for the default log level. Both files are version controlled and contain no secrets.
3. Run the startup check. It validates the path, available space, write access, and the six top-level directories.

```bash
cp .env.example .env
# Edit .env and set DATA_ROOT before running this command.
uv run python -m src check
```

The default capacity threshold is 200 GiB. Set `DATA_MIN_FREE_GIB=0` only in an isolated test environment. The project plan warns that the current local disk may be below the production threshold.

### Settings and precedence

| Setting | Location and default | Purpose |
| --- | --- | --- |
| `DATA_ROOT` | Required in `.env` or process environment | Absolute data directory; never hardcoded in pipeline code. |
| `PIPELINE_CONFIG_DIR` | Optional environment key; defaults to `src/config/defaults/` | Alternate absolute directory containing `storage.json` and `runtime.json`. |
| `DATA_MIN_FREE_GIB` | Environment override of `src/config/defaults/storage.json`, default 200 | Minimum free disk space before startup. |
| `PIPELINE_LOG_LEVEL` | Environment override of `src/config/defaults/runtime.json`, default `INFO` | Validated logging level for future jobs. |
| `POLYGON_RPC`, `POLYMARKET_START_BLOCK` | `.env.example` | Existing legacy indexer settings. |
| `KALSHI_API_KEY_ID`, `KALSHI_PRIVATE_KEY_PEM` | Blank in `.env.example` | Reserved for a later Kalshi adapter; unused by this PR. |
| `POLYMARKET_API_KEY`, `POLYMARKET_API_SECRET`, `POLYMARKET_API_PASSPHRASE` | Blank in `.env.example` | Reserved for later authenticated Polymarket operations; unused by this PR. |
| `DATABASE_URL` | Blank in `.env.example` | Reserved for a future PostgreSQL ledger; unused by PR 1. |

Precedence is **process environment > local `.env` > version-controlled JSON default**. Empty override values fall back to JSON defaults where a default exists. `DATA_ROOT` has no fallback. Secrets are never copied into `PipelineConfig` or printed by the startup check. More details are in [src/config/README.md](src/config/README.md).

### Startup errors

| Message | Action |
| --- | --- |
| `DATA_ROOT is required` | Set `DATA_ROOT` in `.env` or export it. |
| `DATA_ROOT must be an absolute path` | Replace a relative value with an absolute directory path. |
| `DATA_ROOT is not writable` | Check ownership, permissions, and the parent directory. |
| `DATA_MIN_FREE_GIB requires ...` | Use a volume with enough free space. Lower the threshold only for controlled tests. |
| `Missing configuration file` or `Cannot read configuration file` | Restore valid `storage.json` and `runtime.json` in the selected config directory. |

## Data layout and writer boundaries

The startup check creates `imports/`, `bronze/`, `silver/`, `gold/`, `quarantine/`, and `manifests/` under `DATA_ROOT`. A writer is bound to one layer:

| Writer role | Allowed directory |
| --- | --- |
| `IMPORTER` | `imports/` |
| `COLLECTOR` | `bronze/` |
| `NORMALIZER` | `silver/` |
| `PRODUCT` | `gold/` |
| `VALIDATOR` | `quarantine/` |
| `REGISTRY` | `manifests/` |

For example, a `COLLECTOR` writer accepts `bronze/source/file.jsonl` and rejects `silver/file.parquet`, absolute paths, parent traversal, symlink escapes, and replacement of existing files. It publishes a complete file after writing it to a temporary sibling. A writer call in PR 1 does not register a manifest or advance a checkpoint.

## Data contracts and adapter interface

[Data Contracts v2](docs/SCHEMAS.md) defines the Bronze raw envelope, eight Silver datasets, and four Gold products. The JSON registry in `src/data_schema/schema_registry.json` is checked against that document in tests. `validate_record` enforces row shape, types, UTC timestamps, numeric bounds, JSON shape, and selected point-in-time rules. File-wide uniqueness, coverage, and source-specific quality checks belong to the later validation gate.

`VenueAdapter` declares eight operations and eight metadata areas. `MockVenueAdapter` uses only in-memory data and demonstrates market discovery and normalization, trade normalization, and book-event normalization without real API calls. Future venue adapters must implement that interface.

## Run checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

The focused acceptance tests are in `tests/test_pipeline_foundation.py`. They cover startup failures, configuration precedence, writer boundaries, schema/document agreement, point-in-time checks, and the mock adapter chain.

## Legacy workflow

The older collection and analysis commands remain available while their migration is planned. They still use the former `data/kalshi/` and `data/polymarket/` layout and are outside the new `DATA_ROOT` writer path. Do not use `make setup` to initialize the new pipeline: it downloads and extracts a large archive into the legacy layout.

```bash
make index
make analyze
make package
```

## Documentation

- [Architecture and execution plan](PROJECT.md)
- [Data contracts](docs/SCHEMAS.md)
- [Architecture decision record](docs/ADR-001-v1-architecture.md)
- [Configuration guide](src/config/README.md)
- [Writing analyses in the legacy workflow](docs/ANALYSIS.md)

## Research & Citations

- Becker, J. (2026). _The Microstructure of Wealth Transfer in Prediction Markets_. Jbecker. https://jbecker.dev/research/prediction-market-microstructure
- Becker, J. (2026). _The Microstructure of Wealth Transfer in Prediction Markets_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7217640
- Le, N. A. (2026). _Decomposing Crowd Wisdom: Domain-Specific Calibration Dynamics in Prediction Markets_. arXiv. https://arxiv.org/abs/2602.19520
- Akey P., Gregoire, V., Harvie, N., Martineau, C. (2026). _Who Wins and Who Loses In Prediction Markets? Evidence from Polymarket_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6443103
- Vedova, J. (2026). _Who Profits from Prediction Markets? Execution, not Information_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6191618
- Brown, A. (2026). _Cassandra Or the Boy Who Cried Wolf? Are Prediction Markets Effective Early Warning Systems?_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6381538
- Cao, D. (2026). _Retail-Adjusted Expected Value in Prediction Markets: Calibration, Longshot Bias, and Consumer Welfare_. SSRN. https://papers.ssrn.com/sol3/Delivery.cfm/7049119.pdf?abstractid=7049119&mirid=1
- Adamczewski, M. (2026). _Integration Without Leadership: Cross-Venue Price Discovery in UFC Prediction Markets_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7194218
- Reichenbach, F., Walther, M. (2025). _Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5910522
- Bartlett, R., O'Hara, M. (2026). _Adverse Selection in Prediction Markets: Evidence from Kalshi_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6615739
- Luong, K. L., Heesen, G. (2026). _The Wisdom of the Few: Skilled Traders and Prediction Market Accuracy_. SSRN. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6758662
- Adegbenro, A. (2026). _What Prediction Markets Can See: Market Formation, Settlement Legibility, and the Geography of Tradable Uncertainty in Africa and Latin America_. arXiv. https://arxiv.org/abs/2606.17503
- Mauboussin, M. J., Callahan, D. (2026). _The Wisdom of Crowds in Markets: Crowd Behavior in Prediction, Betting, and Stock Markets_. Morgan Stanley. https://www.morganstanley.com/content/dam/im/assets/publication/thought-leadership/consilient-observer/article_thewisdomofcrowds_ltr.pdf?1786370649511

If you have used or plan to use this dataset in your research, please reach out via [email](mailto:jonathan@jbecker.dev) or [Twitter](https://x.com/BeckerrJon) -- i'd love to hear about what you're using the data for! Additionally, feel free to open a PR and update this section with a link to your paper.
