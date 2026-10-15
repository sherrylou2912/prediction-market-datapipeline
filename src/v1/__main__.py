"""Validate and initialize the v1 data directory."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence

from src.v1.config import ConfigError, PipelineConfig
from src.v1.layout import DataLayout


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="v1 pipeline startup checks")
    parser.add_argument("command", choices=("check",), help="validate configuration and create data layers")
    parser.parse_args(argv)
    try:
        config = PipelineConfig.from_env(environ)
        root = config.validate_startup()
        DataLayout.create(root)
    except (ConfigError, OSError, ValueError) as exc:
        print(f"v1 startup failed: {exc}", file=sys.stderr)
        return 2
    print(f"v1 data directory ready: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
