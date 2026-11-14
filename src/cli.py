"""Dispatch pipeline commands to their task entry points."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping, Sequence

from src.config import ConfigError, PipelineConfig
from src.data_io.audit import audit as audit_root
from src.data_io.ledger import LedgerError
from src.logging_config import pipeline_logging


def check(environ: Mapping[str, str] | None = None) -> int:
    """Validate the configured root without creating or probing it for writes."""
    try:
        config = PipelineConfig.load(environ=environ)
        with pipeline_logging(config.log_level):
            logging.getLogger("src.cli").info(
                "effective configuration",
                extra={"event": "config.effective", "details": config.effective_settings()},
            )
            root = config.check_configured_root()
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


def audit(environ: Mapping[str, str] | None = None) -> int:
    """Read-only: reconcile data files with the ledger; 0 when clean, 1 with issues, 2 on errors."""
    try:
        config = PipelineConfig.load(environ=environ)
        with pipeline_logging(config.log_level):
            logging.getLogger("src.cli").info(
                "effective configuration",
                extra={"event": "config.effective", "details": config.effective_settings()},
            )
            root = config.validate_for_read()
            report = audit_root(root)
    except (ConfigError, LedgerError, OSError, ValueError) as exc:
        print(f"pipeline audit failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="prediction market pipeline commands")
    parser.add_argument(
        "command",
        choices=("check", "audit"),
        help="check: validate configuration without writing data; audit: reconcile files with the ledger (read-only)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code)
    # Future example: if args.command == "collect": return collect_task(environ)
    if args.command == "check":
        return check(environ)
    if args.command == "audit":
        return audit(environ)
    raise AssertionError("argparse accepted an unsupported command")


if __name__ == "__main__":
    sys.exit(main())

# 是最终的程序入口，可以理解为 app.py。
