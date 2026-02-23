"""Simple file-backed checkpoint persistence."""

from __future__ import annotations

import hashlib
from pathlib import Path


class CheckpointStore:
    def __init__(self, directory: str) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._dir / f"{safe}.checkpoint"

    def read(self, key: str) -> str | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip() or None

    def write(self, key: str, value: str) -> None:
        path = self._path_for(key)
        path.write_text(value, encoding="utf-8")

    def delete(self, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()

    def path(self, key: str) -> Path:
        return self._path_for(key)
