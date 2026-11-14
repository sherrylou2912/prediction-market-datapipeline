"""Read-only reconciliation of data files against the ledger.

The audit never creates, changes, or deletes anything; it refuses to open a
ledger that has a rollback journal, because SQLite would roll it back. It reports every
condition that needs a person or a recovery step to look at it:

* a registered file that is missing, not a regular file, or whose checksum or
  size no longer matches its manifest entry;
* a file in a registered layer (bronze, silver, gold) without a manifest entry,
  for example after a crash between publication and registration;
* a registered file that cannot be read (reported, and the audit continues);
* an abandoned ``.partial-*`` file (also under ``manifests/``);
* a symbolic link anywhere below a layer, or a layer that is itself a link
  (never followed outside ``DATA_ROOT``);
* a payload waiting in ``recovery/``, a recovery sidecar whose payload is
  gone, or any other file there;
* a run still marked running, or a finished run whose record is missing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.data_io.layout import _digest
from src.data_io.ledger import Ledger

AUDITED_LAYERS = ("bronze", "silver", "gold")
NOT_AUDITED_LAYERS = ("imports", "quarantine")


def _walk(directory: Path) -> list[tuple[Path, bool]]:
    """Return (path, is_symlink) for every file or link below ``directory``."""

    def fail(error: OSError) -> None:
        raise error

    found = []
    if not directory.exists():
        return found
    for current, dirs, files in os.walk(directory, followlinks=False, onerror=fail):
        current_path = Path(current)
        for name in dirs:
            if (current_path / name).is_symlink():
                found.append((current_path / name, True))
        for name in files:
            path = current_path / name
            found.append((path, path.is_symlink()))
    return sorted(found)


def _has_symlinked_parent(root: Path, relative: str) -> bool:
    current = root
    for part in Path(relative).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def audit(root: Path) -> dict[str, Any]:
    """Compare the data layers under ``root`` with the ledger and return a report.

    Run it while no writer is active: a concurrent writer can make files and
    ledger rows appear between the ledger snapshot and the directory walk.
    """
    issues: list[dict[str, Any]] = []
    ledger = Ledger.open_read_only(root)
    manifests: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    if ledger is not None:
        with ledger:
            manifests, runs = ledger.snapshot()

    registered = set()
    for entry in manifests:
        registered.add(entry["path"])
        path = root / entry["path"]
        if _has_symlinked_parent(root, entry["path"]) or path.is_symlink() or (path.exists() and not path.is_file()):
            issues.append({"kind": "manifest_file_not_regular", "path": entry["path"]})
            continue
        if not path.exists():
            issues.append({"kind": "manifest_file_missing", "path": entry["path"], "run_id": entry["run_id"]})
            continue
        try:
            checksum, size = _digest(path)
        except OSError as exc:
            issues.append({"kind": "manifest_file_unreadable", "path": entry["path"], "error": str(exc)})
            continue
        if checksum != entry["sha256"] or size != entry["size_bytes"]:
            issues.append(
                {
                    "kind": "manifest_file_changed",
                    "path": entry["path"],
                    "expected": {"sha256": entry["sha256"], "size_bytes": entry["size_bytes"]},
                    "actual": {"sha256": checksum, "size_bytes": size},
                }
            )

    unregistered = 0
    for layer in (*AUDITED_LAYERS, "manifests", "recovery"):
        directory = root / layer
        if directory.is_symlink():
            # Never follow a layer outside DATA_ROOT.
            issues.append({"kind": "unexpected_symlink", "path": layer})
            continue
        for path, is_link in _walk(directory):
            relative = str(path.relative_to(root))
            if is_link:
                issues.append({"kind": "unexpected_symlink", "path": relative})
            elif path.name.startswith(".partial-"):
                issues.append({"kind": "partial_file", "path": relative})
            elif layer == "recovery":
                issue = _recovery_issue(path, relative)
                if issue is not None:
                    issues.append(issue)
            elif layer in AUDITED_LAYERS and relative not in registered:
                unregistered += 1
                issues.append({"kind": "unregistered_file", "path": relative})

    for run in runs:
        record = None if run["record_path"] is None else root / run["record_path"]
        if run["status"] == "running":
            issues.append({"kind": "run_unfinished", "run_id": run["run_id"], "started_at": run["started_at"]})
        elif record is None or record.is_symlink() or not record.is_file():
            issues.append({"kind": "run_record_missing", "run_id": run["run_id"], "status": run["status"]})

    return {
        "ok": not issues,
        "ledger": "absent" if ledger is None else "present",
        "registered_files": len(manifests),
        "unregistered_files": unregistered,
        "runs": len(runs),
        "audited_layers": list(AUDITED_LAYERS),
        "not_audited_layers": list(NOT_AUDITED_LAYERS),
        "issues": issues,
    }


def _recovery_issue(path: Path, relative: str) -> dict[str, Any] | None:
    """A payload needs review; its sidecar is reported only when the payload is gone."""
    if path.suffix == ".bin":
        return {"kind": "recovery_pending", "path": relative}
    if path.suffix == ".json" and not path.with_suffix(".bin").exists():
        return {"kind": "recovery_metadata_without_payload", "path": relative}
    if path.suffix == ".json":
        return None
    return {"kind": "recovery_unexpected_file", "path": relative}
