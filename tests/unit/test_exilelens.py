"""Unit tests for the ExileLens capture helpers."""

from __future__ import annotations

import unittest

from poe_trade.exilelens.client import ExileLensClient, OCRAdapter
from poe_trade.exilelens.history import History
from poe_trade.exilelens.modes import Mode, select_mode
from poe_trade.exilelens.normalizer import normalize_item_text
from poe_trade.exilelens.session import ROIConfig, SessionType


class _FixedHttpClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def close(self) -> None:
        return None

    class _Response:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def post(self, url: str, json: dict) -> "_FixedHttpClient._Response":
        self.calls.append((url, json))
        return _FixedHttpClient._Response({"status": "ok", "echo": json})


class _StubClipboard:
    def __init__(self, text: str) -> None:
        self._text = text

    def read_text(self) -> str:
        return self._text


class _StubOCR(OCRAdapter):
    def __init__(self, text: str, image: str | None = None) -> None:
        self._text = text
        self._image = image

    def capture_text(self, roi: ROIConfig | None = None) -> tuple[str, str | None]:
        return self._text, self._image


class ExileLensClientTests(unittest.TestCase):
    endpoint = "https://example.com/v1/item/analyze"

    def setUp(self) -> None:
        self.http = _FixedHttpClient()
        self.history = History(maxlen=3)
        self.client = ExileLensClient(self.endpoint, http_client=self.http, history=self.history)

    def tearDown(self) -> None:
        self.client.close()

    def test_mode_selection_defaults(self) -> None:
        self.assertEqual(select_mode(SessionType.WAYLAND), Mode.CLIPBOARD_FIRST)
        self.assertEqual(select_mode(SessionType.X11), Mode.OCR_ONLY)
        self.assertEqual(select_mode(SessionType.UNKNOWN), Mode.OCR_ONLY)
        self.assertEqual(select_mode(SessionType.UNKNOWN, Mode.CLIPBOARD_FIRST), Mode.CLIPBOARD_FIRST)

    def test_clipboard_success_posts_source_clipboard(self) -> None:
        clipboard = _StubClipboard("Rarity: Unique\nItem Level: 100\n")
        result = self.client.capture(
            clipboard,
            _StubOCR(""),
            session_type=SessionType.WAYLAND,
            debug_history=True,
        )
        self.assertEqual(len(self.http.calls), 1)
        url, payload = self.http.calls[0]
        self.assertEqual(url, self.endpoint)
        self.assertEqual(payload["source"], "clipboard")
        self.assertIn("ts_client", payload)
        self.assertEqual(result["status"], "ok")

    def test_ocr_fallback_posts_source_ocr(self) -> None:
        clipboard = _StubClipboard("I am junk")
        ocr = _StubOCR("Rarity: Magic\nItem Level: 1\n", image="aGVsbG8=")
        result = self.client.capture(
            clipboard,
            ocr,
            session_type=SessionType.WAYLAND,
            debug_history=False,
        )
        self.assertEqual(self.http.calls[0][1]["source"], "ocr")
        self.assertEqual(result["status"], "ok")

    def test_ocr_only_mode_always_uses_ocr(self) -> None:
        clipboard = _StubClipboard("Rarity: Unique\nItem Level: 100\n")
        ocr = _StubOCR("Rarity: Magic\nItem Level: 1\n", image="payload")
        result = self.client.capture(
            clipboard,
            ocr,
            session_type=SessionType.WAYLAND,
            mode_override=Mode.OCR_ONLY,
            debug_history=True,
        )
        payload = self.http.calls[0][1]
        self.assertEqual(payload["source"], "ocr")
        self.assertTrue(payload["text"].startswith("Rarity: Magic"))
        self.assertEqual(result["status"], "ok")

    def test_payload_includes_ts_and_path(self) -> None:
        clipboard = _StubClipboard("Rarity: Unique\nItem Level: 100")
        self.client.capture(
            clipboard,
            _StubOCR(""),
            session_type=SessionType.WAYLAND,
        )
        _, payload = self.http.calls[0]
        self.assertTrue(payload["ts_client"].endswith("Z"))
        self.assertTrue(payload["text"].startswith("Rarity:"))

    def test_history_ring_buffer_and_image_guardrail(self) -> None:
        clipboard = _StubClipboard("Rarity: Rare\nItem Level: 5\n")
        self.client.capture(
            clipboard,
            _StubOCR(""),
            session_type=SessionType.WAYLAND,
            debug_history=False,
        )
        self.client.capture(
            _StubClipboard("junk"),
            _StubOCR("Rarity: Unique\n", image="data"),
            session_type=SessionType.WAYLAND,
            debug_history=True,
        )
        records = self.history.records()
        self.assertEqual(len(records), 2)
        self.assertIsNone(records[0].image_b64)
        self.assertEqual(records[1].image_b64, "data")
        self.assertEqual(records[1].source, "ocr")

    def test_payload_image_guardrail(self) -> None:
        ocr = _StubOCR("Rarity: Rare\n", image="secure")
        self.client.capture(
            _StubClipboard("junk"),
            ocr,
            session_type=SessionType.WAYLAND,
            mode_override=Mode.OCR_ONLY,
            debug_history=False,
        )
        payload = self.http.calls[0][1]
        self.assertNotIn("image_b64", payload)
        self.assertEqual(len(self.history.records()), 1)
        self.assertIsNone(self.history.records()[0].image_b64)

if __name__ == "__main__":
    unittest.main()
