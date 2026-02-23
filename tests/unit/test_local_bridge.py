"""Unit tests for the local bridge slice."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from poe_trade.bridge.local_bridge import (
    capture_screen_text,
    clipboard_read,
    clipboard_write,
    push_overlay_payload,
    write_item_filter,
)


class FakeClipboard:
    def __init__(self, initial: str = "") -> None:
        self.value = initial

    def read_text(self) -> str:
        return self.value

    def write_text(self, value: str) -> None:
        self.value = value


class FakeOCR:
    def __init__(self, text: str = "text", image_b64: str = "image") -> None:
        self._text = text
        self._image = image_b64
        self.last_roi = None

    def capture_text(self, roi=None) -> tuple[str, str]:
        self.last_roi = roi
        return self._text, self._image


class LocalBridgeTests(unittest.TestCase):
    def test_manual_trigger_guard_blocks_action(self) -> None:
        clipboard = FakeClipboard("vault")
        result = clipboard_read(clipboard, manual_trigger=False)
        self.assertFalse(result.success)
        self.assertIn("manual trigger", result.message)

    def test_clipboard_read_and_write(self) -> None:
        clipboard = FakeClipboard("initial")
        read_result = clipboard_read(clipboard, manual_trigger=True)
        self.assertTrue(read_result.success)
        self.assertEqual(read_result.payload["value"], "initial")
        write_result = clipboard_write(clipboard, "updated", manual_trigger=True)
        self.assertTrue(write_result.success)
        self.assertEqual(clipboard.value, "updated")

    def test_capture_hook_returns_text_and_image(self) -> None:
        ocr = FakeOCR("payload", "encoded")
        result = capture_screen_text(ocr, manual_trigger=True)
        self.assertTrue(result.success)
        self.assertEqual(result.payload["text"], "payload")
        self.assertEqual(result.payload["image_b64"], "encoded")

    def test_overlay_payload_appends_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "queue.jsonl"
            payload = {"event": "overlay"}
            result = push_overlay_payload(path, payload, manual_trigger=True)
            self.assertTrue(result.success)
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["payload"], payload)
            self.assertEqual(record["action"], "push_overlay_payload")

    def test_item_filter_write_creates_backup(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "filter.txt"
            target.write_text("baseline")
            backup = Path(tmpdir) / "filter.bak"
            result = write_item_filter(
                target,
                "updated",
                manual_trigger=True,
                backup_path=backup,
            )
            self.assertTrue(result.success)
            self.assertEqual(target.read_text(encoding="utf-8"), "updated")
            self.assertEqual(backup.read_text(encoding="utf-8"), "baseline")
