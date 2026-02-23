"""Session detection and ROI helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class SessionType(Enum):
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ROIConfig:
    x: int
    y: int
    width: int
    height: int


def detect_session(env: Mapping[str, str] | None = None) -> SessionType:
    """Best-effort guess of the current desktop session."""

    env = env or os.environ
    session_hint = env.get("XDG_SESSION_TYPE", "").lower()

    if "wayland" in session_hint or env.get("WAYLAND_DISPLAY"):
        return SessionType.WAYLAND

    if "x11" in session_hint or env.get("DISPLAY"):
        return SessionType.X11

    return SessionType.UNKNOWN
