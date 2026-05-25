"""Path helpers that work in both the repo checkout and the Docker image."""
from __future__ import annotations

from pathlib import Path


def find_backend_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for parent in (current.parent, *current.parents):
        if (parent / "app").is_dir() and (parent / "artifacts").is_dir():
            return parent
        if parent.name == "backend" and (parent / "app").is_dir():
            return parent
    return Path.cwd()


def find_workspace_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    for parent in (current.parent, *current.parents):
        if (parent / "IA_BASES").is_dir():
            return parent

    backend_root = find_backend_root(current)
    return backend_root.parent if backend_root.name == "backend" else backend_root
