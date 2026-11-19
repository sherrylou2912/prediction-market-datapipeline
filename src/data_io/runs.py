"""Run lifecycle: register a run, commit its files, and publish its run record.

Typical use by a write task::

    config = PipelineConfig.load()
    layout = open_write_layout(config)  # write preflight, then the layout with the configured lock timeout
    with Run.start(layout, config, RunSpec(task="mock_backfill", task_version="1")) as run:
        run.commit_file(WriterRole.NORMALIZER, "silver/trades/x.parquet", payload, facts, checkpoint)
        run.finish("succeeded")

The ledger row is the authority. ``finish`` stores the final status first and
then publishes ``manifests/runs/<run_id>/record.json`` (and ``report.md`` unless
disabled) built entirely from the ledger.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType, TracebackType
from typing import Any

from src.config import PipelineConfig
from src.config.loader import PROJECT_ROOT
from src.data_io.layout import DataLayout, WriteBoundaryError, WriterRole
from src.data_io.ledger import (
    FINAL_RUN_STATUSES,
    LEDGER_SCHEMA_VERSION,
    CheckpointAdvance,
    FileFacts,
    Ledger,
    LedgerError,
    commit_values,
    json_text,
    run_values,
)
from src.data_schema.contracts import SCHEMA_VERSION

logger = logging.getLogger(__name__)

RUN_RECORD_VERSION = "1"


def new_run_id(now: datetime | None = None) -> str:
    """A sortable ID that is also a valid Bronze receipt ID."""
    moment = now or datetime.now(timezone.utc)
    return f"{moment.strftime('%Y%m%dt%H%M%Sz')}-{uuid.uuid4().hex[:12]}"


def code_version() -> dict[str, Any]:
    """Return the checked-out commit and whether the worktree has changes; unknown is never invented."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, check=True, timeout=10
        ).stdout

    try:
        commit = git("rev-parse", "HEAD").strip()
        dirty = bool(git("status", "--porcelain").strip())
    except (OSError, subprocess.SubprocessError) as exc:
        return {"commit": None, "dirty": None, "unknown_reason": f"git unavailable: {type(exc).__name__}"}
    return {"commit": commit, "dirty": dirty}


@dataclass(frozen=True)
class RunSpec:
    """What a run does. ``parameters`` are the task's effective non-secret parameters."""

    task: str
    task_version: str
    venue: str | None = None
    dataset: str | None = None
    range_start: datetime | None = None
    range_end: datetime | None = None
    parameters: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


class Run:
    """A registered run. Use ``Run.start``; a run must end with ``finish``."""

    def __init__(self, layout: DataLayout, ledger: Ledger, run_id: str, *, write_report: bool) -> None:
        self.layout = layout
        self.run_id = run_id
        self._ledger = ledger
        self._write_report = write_report
        # "running" until the final status is stored, then "closed".
        self._state = "running"
        self.record_path: Path | None = None

    @classmethod
    def start(
        cls,
        layout: DataLayout,
        config: PipelineConfig,
        spec: RunSpec,
        *,
        write_report: bool = True,
        run_id: str | None = None,
    ) -> Run:
        """Validate everything, then register the run; nothing is created when validation fails."""
        if not isinstance(spec, RunSpec):
            raise LedgerError("spec must be a RunSpec value")
        if not isinstance(write_report, bool):
            raise LedgerError("write_report must be a boolean")
        if not isinstance(spec.parameters, Mapping):
            raise LedgerError("parameters must be a mapping")
        identifier = new_run_id() if run_id is None else run_id
        if not isinstance(identifier, str) or re.fullmatch(r"[a-z0-9][a-z0-9_-]*", identifier) is None:
            raise LedgerError("run_id must use lowercase ASCII letters, digits, _ or -")
        configured_root = config.data_root.resolve() if config.data_root.exists() else config.data_root
        if configured_root != layout.root:
            raise LedgerError(f"Config DATA_ROOT {config.data_root} does not match the layout root {layout.root}")
        if config.writer_lock_timeout_seconds != layout.lock_timeout_seconds:
            raise LedgerError("Config writer_lock_timeout_seconds does not match the layout's lock timeout")
        settings = config.effective_settings()
        fields = {
            "run_id": identifier,
            "task": spec.task,
            "task_version": spec.task_version,
            "started_at": datetime.now(timezone.utc),
            "code_version": code_version(),
            "config": settings,
            "parameters": dict(spec.parameters),
            "venue": spec.venue,
            "dataset": spec.dataset,
            "range_start": spec.range_start,
            "range_end": spec.range_end,
        }
        run_values(**fields)  # reject invalid input before the ledger file is created
        ledger = Ledger.open(layout)
        try:
            ledger.create_run(**fields)
        except BaseException:
            ledger.close()
            raise
        logger.info(
            "run started",
            extra={"event": "run.started", "run_id": identifier, "details": {"task": spec.task, "config": settings}},
        )
        return cls(layout, ledger, identifier, write_report=write_report)

    def _require_running(self) -> None:
        if self._state != "running":
            raise LedgerError(f"Run {self.run_id} is already finished")

    def commit_file(
        self,
        role: WriterRole,
        path: str | Path,
        payload: bytes,
        facts: FileFacts,
        checkpoint: CheckpointAdvance | None = None,
        *,
        receipt_id: str | None = None,
    ) -> dict[str, Any]:
        """Publish ``payload`` durably, then register it and advance ``checkpoint`` in one transaction.

        Arguments and the run state are checked before publishing. If
        registration still fails afterwards (for example a stale checkpoint
        version), the file stays on disk unregistered and
        ``python -m src audit`` reports it.
        """
        self._require_running()
        commit_values(path, facts, checkpoint)
        self._ledger.require_running(self.run_id)
        published = self.layout.writer(role).write_new(path, payload, receipt_id=receipt_id)
        relative = published.relative_to(self.layout.root)
        try:
            entry = self._ledger.commit(self.run_id, relative, facts, checkpoint)
        except LedgerError:
            logger.error(
                "file was published but registration failed: %s",
                relative,
                extra={"event": "run.file_unregistered", "run_id": self.run_id},
            )
            raise
        logger.info(
            "file committed: %s",
            relative,
            extra={"event": "run.file_committed", "run_id": self.run_id, "details": entry},
        )
        return entry

    def add_counts(self, *, requests: int = 0, rows_received: int = 0, rows_quarantined: int = 0) -> None:
        self._require_running()
        self._ledger.add_counts(
            self.run_id, requests=requests, rows_received=rows_received, rows_quarantined=rows_quarantined
        )

    def finish(self, status: str, error: str | None = None) -> Path:
        """Store the final status, then publish the run record; returns the record path.

        If storing the status fails, the run stays open so the caller (or
        ``__exit__``) can retry or record a failure.
        """
        self._require_running()
        if status not in FINAL_RUN_STATUSES:
            raise LedgerError(f"Final run status must be one of {FINAL_RUN_STATUSES}")
        if error is not None and (not isinstance(error, str) or status == "succeeded"):
            raise LedgerError("error must be a string and is only allowed for partial or failed runs")
        if status == "failed" and not (error and error.strip()):
            raise LedgerError("A failed run requires an error description")
        self._ledger.finish_run(self.run_id, status=status, finished_at=datetime.now(timezone.utc), error=error)
        self._state = "closed"
        try:
            record = build_record(self._ledger, self.run_id)
            writer = self.layout.writer(WriterRole.REGISTRY)
            base = f"manifests/runs/{self.run_id}"
            record_path = writer.write_new(f"{base}/record.json", (json_text(record, "run record") + "\n").encode())
            if self._write_report:
                writer.write_new(f"{base}/report.md", render_report(record).encode("utf-8"))
            relative = str(record_path.relative_to(self.layout.root))
            self._ledger.set_record_path(self.run_id, relative)
        except WriteBoundaryError as exc:
            raise LedgerError(
                f"Run {self.run_id} finished as {status} but its record was not published: {exc}"
            ) from exc
        finally:
            self._ledger.close()
        self.record_path = record_path
        logger.info(
            "run finished: %s",
            status,
            extra={"event": "run.finished", "run_id": self.run_id, "details": {"record": relative}},
        )
        return record_path

    def __enter__(self) -> Run:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        if self._state != "running":
            return
        reason = "run exited without calling finish()" if exc is None else f"{type(exc).__name__}: {exc}"
        try:
            self.finish("failed", error=reason)
        except LedgerError as finish_exc:
            if self._state == "running":
                # The final status itself was not stored.
                message = "could not be recorded as failed; it remains marked running in the ledger"
                self._state = "closed"
                self._ledger.close()
            else:
                message = "was recorded as failed, but its run record was not published"
            logger.exception(
                "run %s %s", self.run_id, message, extra={"event": "run.finish_failed", "run_id": self.run_id}
            )
            if exc is None:
                raise LedgerError(f"Run {self.run_id} exited without calling finish() and {message}") from finish_exc
            return
        if exc is None:
            raise LedgerError(f"Run {self.run_id} exited without calling finish(); recorded as failed")


def build_record(ledger: Ledger, run_id: str) -> dict[str, Any]:
    """Build the machine-readable run record from the ledger alone."""
    run = ledger.get_run(run_id)
    for name in ("code_version", "config", "parameters"):
        run[name] = json.loads(run[name])
    run.pop("record_path")
    manifests = ledger.manifests(run_id)
    return {
        "record_version": RUN_RECORD_VERSION,
        "run": run,
        "rule_versions": {"data_contracts": SCHEMA_VERSION, "ledger_schema": LEDGER_SCHEMA_VERSION},
        "datasets": sorted({entry["dataset"] for entry in manifests}),
        "manifests": manifests,
        "checkpoints": ledger.checkpoint_history(run_id),
    }


def render_report(record: Mapping[str, Any]) -> str:
    """Render a short human-readable Markdown summary of a run record."""
    run = record["run"]
    code = run["code_version"]
    commit = code.get("commit") or "unknown"
    dirty = {True: "yes", False: "no", None: "unknown"}[code.get("dirty")]
    lines = [
        f"# Run {run['run_id']}",
        "",
        f"- Task: `{run['task']}` version `{run['task_version']}`",
        f"- Status: **{run['status']}**",
        f"- Started: {run['started_at']}; finished: {run['finished_at']}",
        f"- Code: `{commit}`; uncommitted changes: {dirty}",
        f"- Config SHA-256: `{run['config'].get('sha256', 'unknown')}`",
        f"- Data contracts: `{record['rule_versions']['data_contracts']}`",
        f"- Requests: {run['requests']}; rows received: {run['rows_received']}; "
        f"rows written: {run['rows_written']}; rows quarantined: {run['rows_quarantined']}",
    ]
    if run["error"]:
        lines.append(f"- Error: {run['error']}")
    lines += ["", "## Files", ""]
    if record["manifests"]:
        lines += ["| Path | Dataset | Rows | SHA-256 |", "| --- | --- | --- | --- |"]
        lines += [
            f"| `{m['path']}` | {m['dataset']} | {m['row_count']} | `{m['sha256'][:12]}` |" for m in record["manifests"]
        ]
    else:
        lines.append("No files were registered.")
    lines += ["", "## Checkpoints", ""]
    if record["checkpoints"]:
        lines += [
            f"- `{c['checkpoint_key']}` → version {c['version']} (`{c['last_file']}`)" for c in record["checkpoints"]
        ]
    else:
        lines.append("No checkpoints advanced.")
    return "\n".join(lines) + "\n"


__all__ = ["Run", "RunSpec", "build_record", "code_version", "new_run_id", "render_report"]
