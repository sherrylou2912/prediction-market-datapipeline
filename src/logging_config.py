"""Configure JSON logging for the pipeline's own loggers."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Format one log record as one JSON object without environment details."""

    def format(self, record: logging.LogRecord) -> str:
        event = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.name),
            "message": record.getMessage(),
        }
        if hasattr(record, "run_id"):
            event["run_id"] = record.run_id
        if hasattr(record, "details"):
            event["details"] = record.details
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        return json.dumps(event, ensure_ascii=False)


@contextmanager
def pipeline_logging(level: str) -> Iterator[None]:
    """Configure logs for a command, then restore the embedding application's state."""
    logger = logging.getLogger("src")
    previous_handlers = logger.handlers[:]
    previous_level, previous_propagate = logger.level, logger.propagate
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.handlers = [handler]
    logger.setLevel(level)
    logger.propagate = False
    try:
        yield
    finally:
        logger.handlers = previous_handlers
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
        handler.close()
