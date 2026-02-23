"""Local bridge API helpers for manual overlay + clipboard tooling."""

from .local_bridge import (
    BridgeResult,
    capture_screen_text,
    clipboard_read,
    clipboard_write,
    push_overlay_payload,
    write_item_filter,
)

__all__ = [
    "BridgeResult",
    "capture_screen_text",
    "clipboard_read",
    "clipboard_write",
    "push_overlay_payload",
    "write_item_filter",
]
