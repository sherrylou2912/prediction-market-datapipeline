"""Check pipeline configuration without starting a data write."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from src.config.settings import ConfigError, PipelineConfig
from src.config.validation import check_configured_root


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pipeline configuration checks")
    parser.add_argument("command", choices=("check",), help="validate configuration without writing data")
    parser.parse_args(argv)
    try:
        config = PipelineConfig.load(environ=environ)
        root = check_configured_root(config.data_root)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"pipeline startup failed: {exc}", file=sys.stderr)
        return 2
    if root.exists():
        print(f"pipeline configuration valid; DATA_ROOT exists: {root}")
    else:
        print(
            f"pipeline configuration valid; DATA_ROOT does not exist; a write job will create it if permitted: {root}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
