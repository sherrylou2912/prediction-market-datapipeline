"""Validate and initialize the pipeline data directory."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from src.pipeline.config import ConfigError, PipelineConfig
from src.pipeline.layout import DataLayout


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="pipeline startup checks")
    parser.add_argument("command", choices=("check",), help="validate configuration and create data layers")
    parser.parse_args(argv)
    try:
        config = PipelineConfig.load(environ=environ)
        root = config.validate_startup()
        DataLayout.create(root)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"pipeline startup failed: {exc}", file=sys.stderr)
        return 2
    print(f"pipeline data directory ready: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
