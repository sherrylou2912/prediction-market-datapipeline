"""Scoped, append-only writes under the configured data root."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class WriterRole(str, Enum):
    IMPORTER = "imports"
    COLLECTOR = "bronze"
    NORMALIZER = "silver"
    PRODUCT = "gold"
    VALIDATOR = "quarantine"
    REGISTRY = "manifests"


class WriteBoundaryError(ValueError):
    """A writer attempted to use a path outside its assigned layer."""


@dataclass(frozen=True)
class DataLayout:
    root: Path

    @classmethod
    def create(cls, root: Path) -> DataLayout:
        resolved_root = root.resolve(strict=True)
        if not resolved_root.is_dir():
            raise WriteBoundaryError(f"Data root is not a directory: {resolved_root}")
        for role in WriterRole:
            layer = resolved_root / role.value
            layer.mkdir(exist_ok=True)
            if layer.is_symlink() or not layer.is_dir():
                raise WriteBoundaryError(f"Data layer must be a real directory: {layer}")
        return cls(root=resolved_root)

    def writer(self, role: WriterRole) -> ScopedWriter:
        if not isinstance(role, WriterRole):
            raise TypeError("Writer role must be a WriterRole value.")
        return ScopedWriter(root=self.root, role=role)


@dataclass(frozen=True)
class ScopedWriter:
    root: Path
    role: WriterRole

    def write_new(self, path: str | Path, payload: bytes) -> Path:
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        relative = Path(path)
        if relative.is_absolute() or ".." in relative.parts or len(relative.parts) < 2:
            raise WriteBoundaryError(f"Writer path must be a root-relative file path: {path}")
        if relative.parts[0] != self.role.value:
            raise WriteBoundaryError(f"{self.role.name} writer may only write under {self.role.value}/: {path}")

        layer = self.root / self.role.value
        if layer.is_symlink() or layer.resolve(strict=True) != layer:
            raise WriteBoundaryError(f"Writer layer is not a real directory: {layer}")
        parent = layer
        for component in relative.parts[1:-1]:
            parent = parent / component
            if parent.is_symlink():
                raise WriteBoundaryError(f"Writer path contains a symbolic link: {path}")
            parent.mkdir(exist_ok=True)
            resolved_parent = parent.resolve(strict=True)
            if resolved_parent != layer and layer not in resolved_parent.parents:
                raise WriteBoundaryError(f"Writer path escapes {self.role.value}/: {path}")
        target = parent / relative.parts[-1]
        try:
            with target.open("xb") as handle:
                handle.write(payload)
        except FileExistsError as exc:
            raise WriteBoundaryError(f"Append-only writer refuses to replace: {target}") from exc
        return target
