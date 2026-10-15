# Prediction Market Analysis

A framework for analyzing prediction market data, including the largest publicly available dataset of Polymarket and Kalshi market and trade data. Provides tools for data collection, storage, and running analysis scripts that generate figures and statistics.

## Overview

This project enables research and analysis of prediction markets by providing:
- Pre-collected datasets from Polymarket and Kalshi
- Data collection indexers for gathering new data
- Analysis framework for generating figures and statistics

Currently supported features:
- Market metadata collection (Kalshi & Polymarket)
- Trade history collection via API and blockchain
- Parquet-based storage with automatic progress saving
- Extensible analysis script framework

## Installation & Usage

Requires Python 3.9+. Install dependencies with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

### v1 pipeline foundation

The v1 rebuild uses a separate entry point. Set `DATA_ROOT` to an absolute location with at least 200 GiB free, then validate and create its six data layers:

```bash
export DATA_ROOT=/absolute/path/to/prediction-market-data
uv run python -m src.v1 check
```

`DATA_MIN_FREE_GIB` defaults to 200 and may be overridden for controlled tests. `PIPELINE_LOG_LEVEL` defaults to `INFO`. Missing, unwritable, or undersized data roots fail at startup. The legacy commands below still use their former layout and are not part of the v1 writer path.

The legacy setup command downloads and extracts the pre-collected dataset (36 GiB compressed). Do not run it as a v1 initialization step:

```bash
make setup
```

This downloads `data.tar.zst` from [Cloudflare R2 Storage](https://s3.jbecker.dev/data.tar.zst) and extracts it to `data/`.

### Data Collection

Collect market and trade data from prediction market APIs:

```bash
make index
```

This opens an interactive menu to select which indexer to run. Data is saved to `data/kalshi/` and `data/polymarket/` directories. Progress is saved automatically, so you can interrupt and resume collection.

### Running Analyses

```bash
make analyze
```

This opens an interactive menu to select which analysis to run. You can run all analyses or select a specific one. Output files (PNG, PDF, CSV, JSON) are saved to `output/`.

### Packaging Data

To compress the data directory for storage/distribution:

```bash
make package
```

This creates a zstd-compressed tar archive (`data.tar.zst`) and removes the `data/` directory.

## Project Structure

```
├── src/
│   ├── analysis/           # Analysis scripts
│   │   ├── kalshi/         # Kalshi-specific analyses
│   │   └── polymarket/     # Polymarket-specific analyses
│   ├── indexers/           # Data collection indexers
│   │   ├── kalshi/         # Kalshi API client and indexers
│   │   └── polymarket/     # Polymarket API/blockchain indexers
│   └── common/             # Shared utilities and interfaces
├── data/                   # Data directory (extracted from data.tar.zst)
│   ├── kalshi/
│   │   ├── markets/
│   │   └── trades/
│   └── polymarket/
│       ├── blocks/
│       ├── markets/
│       └── trades/
├── docs/                   # Documentation
└── output/                 # Analysis outputs (figures, CSVs)
```

## Documentation

- [Data Contracts v2](docs/SCHEMAS.md) - Bronze, Silver, and Gold contracts
- [Architecture decision](docs/ADR-001-v1-architecture.md) - v1 storage and scheduling choices
- [Writing Analyses](docs/ANALYSIS.md) - Guide for writing custom analysis scripts

## Contributing

If you'd like to contribute to this project, please open a pull-request with your changes, as well as detailed information on what is changed, added, or improved.

For more information, see the [contributing guide](CONTRIBUTING.md).

## Issues

If you've found an issue or have a question, please open an issue [here](https://github.com/jon-becker/prediction-market-analysis/issues).

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
