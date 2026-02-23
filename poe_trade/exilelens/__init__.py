"""Linux ExileLens capture helpers."""

from __future__ import annotations

from .client import ExileLensClient
from .history import History, ScanRecord
from .modes import Mode, select_mode
from .normalizer import is_likely_item_text, normalize_item_text
from .session import ROIConfig, SessionType, detect_session
from .system_clipboard import ClipboardUnavailable, SystemClipboard
from .system_ocr import OcrUnavailable, SystemOCR

__all__ = [
    "ExileLensClient",
    "History",
    "ScanRecord",
    "Mode",
    "select_mode",
    "is_likely_item_text",
    "normalize_item_text",
    "ROIConfig",
    "SessionType",
    "detect_session",
    "ClipboardUnavailable",
    "SystemClipboard",
    "OcrUnavailable",
    "SystemOCR",
]
