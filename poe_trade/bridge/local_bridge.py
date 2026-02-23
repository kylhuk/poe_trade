"""Local bridge actions for manual overlay helpers."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Protocol

from poe_trade.exilelens.session import ROIConfig


class ClipboardAdapter(Protocol):
    """Abstraction for clipboard helpers."""

    def read_text(self) -> str:
        ...

    def write_text(self, value: str) -> None:
        ...


class OCRAdapter(Protocol):
    """Abstraction for screen capture helpers."""

    def capture_text(self, roi: ROIConfig | None = None) -> tuple[str, str | None]:
        ...


@dataclass(frozen=True)
class BridgeResult:
    action: str
    success: bool
    message: str
    payload: Dict[str, Any]


_MANUAL_REQUIRED = "manual trigger required for local bridge actions"


def _manual_guard(action: str, manual_trigger: bool) -> BridgeResult | None:
    if manual_trigger:
        return None
    return BridgeResult(
        action=action,
        success=False,
        message=_MANUAL_REQUIRED,
        payload={"manual_trigger": manual_trigger},
    )


def capture_screen_text(
    ocr: OCRAdapter,
    *,
    manual_trigger: bool,
    roi: ROIConfig | None = None,
) -> BridgeResult:
    guard = _manual_guard("capture_screen_text", manual_trigger)
    if guard:
        return guard
    try:
        text, image_b64 = ocr.capture_text(roi)
    except Exception as exc:  # pragma: no cover - depends on capture tools
        return BridgeResult(
            action="capture_screen_text",
            success=False,
            message=f"capture failed: {exc}",
            payload={
                "manual_trigger": manual_trigger,
                "error": str(exc),
            },
        )
    return BridgeResult(
        action="capture_screen_text",
        success=True,
        message="capture completed",
        payload={
            "manual_trigger": manual_trigger,
            "text": text,
            "image_b64": image_b64,
        },
    )


def clipboard_read(
    clipboard: ClipboardAdapter,
    *,
    manual_trigger: bool,
) -> BridgeResult:
    guard = _manual_guard("clipboard_read", manual_trigger)
    if guard:
        return guard
    value = clipboard.read_text()
    return BridgeResult(
        action="clipboard_read",
        success=True,
        message="clipboard inspected",
        payload={"manual_trigger": manual_trigger, "value": value},
    )


def clipboard_write(
    clipboard: ClipboardAdapter,
    value: str,
    *,
    manual_trigger: bool,
) -> BridgeResult:
    guard = _manual_guard("clipboard_write", manual_trigger)
    if guard:
        return guard
    clipboard.write_text(value)
    return BridgeResult(
        action="clipboard_write",
        success=True,
        message="clipboard updated",
        payload={"manual_trigger": manual_trigger, "value": value},
    )


def push_overlay_payload(
    queue_path: Path | str,
    payload: Dict[str, Any],
    *,
    manual_trigger: bool,
) -> BridgeResult:
    guard = _manual_guard("push_overlay_payload", manual_trigger)
    if guard:
        return guard
    queue_file = Path(queue_path)
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "manual_trigger": manual_trigger,
        "action": "push_overlay_payload",
        "payload": payload,
    }
    with queue_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record))
        handle.write("\n")
    return BridgeResult(
        action="push_overlay_payload",
        success=True,
        message="overlay payload queued",
        payload={
            "manual_trigger": manual_trigger,
            "queue_path": str(queue_file),
            "record": record,
        },
    )


def write_item_filter(
    filter_path: Path | str,
    contents: str,
    *,
    manual_trigger: bool,
    backup_path: Path | str | None = None,
) -> BridgeResult:
    guard = _manual_guard("write_item_filter", manual_trigger)
    if guard:
        return guard
    target = Path(filter_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_target = Path(backup_path) if backup_path else None
    if backup_target:
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.copy2(target, backup_target)
    temp_dir = target.parent or Path(".")
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=str(temp_dir)
    ) as tmp:
        tmp.write(contents)
        tmp.flush()
        os.fsync(tmp.fileno())
    temp_path = Path(tmp.name)
    try:
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    payload = {
        "manual_trigger": manual_trigger,
        "filter_path": str(target),
    }
    if backup_target:
        payload["backup_path"] = str(backup_target)
    return BridgeResult(
        action="write_item_filter",
        success=True,
        message="filter written atomically",
        payload=payload,
    )
