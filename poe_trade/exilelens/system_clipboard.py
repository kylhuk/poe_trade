"""System clipboard helpers for Linux-based ExileLens."""

from __future__ import annotations

import shutil
import subprocess
from typing import Sequence


class ClipboardUnavailable(RuntimeError):
    pass


class SystemClipboard:
    """Adapter that reads and writes using system clipboard helpers."""

    _READERS: Sequence[tuple[str, Sequence[str]]] = (
        ("wl-paste", ("wl-paste", "--no-newline")),
        ("xclip", ("xclip", "-selection", "clipboard", "-o")),
        ("xsel", ("xsel", "--clipboard", "--output")),
    )
    _WRITERS: Sequence[tuple[str, Sequence[str]]] = (
        ("wl-copy", ("wl-copy",)),
        ("xclip", ("xclip", "-selection", "clipboard")),
        ("xsel", ("xsel", "--clipboard", "--input")),
    )

    def __init__(self) -> None:
        self._read_cmd = self._find_command(self._READERS)
        self._write_cmd = self._find_command(self._WRITERS)
        if not self._read_cmd or not self._write_cmd:
            raise ClipboardUnavailable(
                "clipboard helpers missing; install wl-paste/wl-copy, xclip, or xsel"
            )

    def _find_command(self, candidates: Sequence[tuple[str, Sequence[str]]]) -> Sequence[str] | None:
        for name, cmd in candidates:
            if shutil.which(name):
                return list(cmd)
        return None

    def read_text(self) -> str:
        result = subprocess.run(
            self._read_cmd, check=True, capture_output=True, text=True
        )
        return result.stdout.rstrip("\n")

    def write_text(self, value: str) -> None:
        subprocess.run(self._write_cmd, check=True, input=value, text=True)
