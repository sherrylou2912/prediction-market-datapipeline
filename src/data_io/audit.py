"""Read-only reconciliation of data files against the ledger.

The audit never creates, changes, or deletes anything. It reports every
condition that needs a person or a recovery step to look at it:

* a registered file that is missing, not a regular file, or whose checksum or
  size no longer matches its manifest entry;
* a file in a registered layer (bronze, silver, gold) without a manifest entry,
  for example after a crash between publication and registration;
* an abandoned ``.partial-*`` file or an unexpected symbolic link;
* a payload waiting in ``recovery/``;
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


def audit(root: Path) -> dict[str, Any]:
    """Compare the data layers under ``root`` with its ledger and return a report."""
    issues: list[dict[str, Any]] = []
    ledger = Ledger.open_read_only(root)
    manifests: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    if ledger is not None:
        with ledger:
            manifests = ledger.manifests()
            runs = ledger.runs()

    registered = set()
    for entry in manifests:
        registered.add(entry["path"])
        path = root / entry["path"]
        if path.is_symlink() or (path.exists() and not path.is_file()):
            issues.append({"kind": "manifest_file_not_regular", "path": entry["path"]})
            continue
        if not path.exists():
            issues.append({"kind": "manifest_file_missing", "path": entry["path"], "run_id": entry["run_id"]})
            continue
        checksum, size = _digest(path)
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
    for layer in AUDITED_LAYERS:
        for path, is_link in _walk(root / layer):
            relative = str(path.relative_to(root))
            if is_link:
                issues.append({"kind": "unexpected_symlink", "path": relative})
            elif path.name.startswith(".partial-"):
                issues.append({"kind": "partial_file", "path": relative})
            elif relative not in registered:
                unregistered += 1
                issues.append({"kind": "unregistered_file", "path": relative})

    for path, _ in _walk(root / "recovery"):
        if path.suffix == ".bin":
            issues.append({"kind": "recovery_pending", "path": str(path.relative_to(root))})

    for run in runs:
        if run["status"] == "running":
            issues.append({"kind": "run_unfinished", "run_id": run["run_id"], "started_at": run["started_at"]})
        elif run["record_path"] is None or not (root / run["record_path"]).is_file():
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
