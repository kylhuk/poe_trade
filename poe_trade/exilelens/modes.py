"""Drive mode selection for ExileLens!"""

from __future__ import annotations

from enum import Enum

from .session import SessionType


class Mode(Enum):
    CLIPBOARD_FIRST = "clipboard"
    OCR_ONLY = "ocr"


def select_mode(session_type: SessionType, override: Mode | None = None) -> Mode:
    """Return the capture mode for the provided session."""

    if override is not None:
        return override

    if session_type == SessionType.WAYLAND:
        return Mode.CLIPBOARD_FIRST

    return Mode.OCR_ONLY
