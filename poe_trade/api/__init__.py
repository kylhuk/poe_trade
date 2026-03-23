"""API package."""

from __future__ import annotations

from typing import Any

__all__ = ["ApiApp", "create_app"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .app import ApiApp, create_app

        return {"ApiApp": ApiApp, "create_app": create_app}[name]
    raise AttributeError(name)
