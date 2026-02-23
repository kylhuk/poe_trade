"""Unit tests for the ExileLens capture helpers."""

from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from poe_trade.exilelens.client import ExileLensClient, OCRAdapter
from poe_trade.exilelens.history import History
from poe_trade.exilelens.modes import Mode, select_mode
from poe_trade.exilelens.session import ROIConfig, SessionType
from poe_trade.exilelens.system_clipboard import ClipboardUnavailable, SystemClipboard
from poe_trade.exilelens.system_ocr import SystemOCR
from poe_trade.services.exilelens import _copy_price_field


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
        self.written: list[str] = []

    def read_text(self) -> str:
        return self._text

    def write_text(self, value: str) -> None:
        self.written.append(value)


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


class SystemClipboardTests(unittest.TestCase):
    @mock.patch("poe_trade.exilelens.system_clipboard.shutil.which")
    @mock.patch("poe_trade.exilelens.system_clipboard.subprocess.run")
    def test_prefers_wayland_helpers(self, mock_run, mock_which) -> None:
        mock_which.side_effect = lambda name: f"/bin/{name}" if name in {"wl-paste", "wl-copy"} else None
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="value\n")
        clipboard = SystemClipboard()
        self.assertEqual(clipboard.read_text(), "value")
        clipboard.write_text("price")
        self.assertEqual(mock_run.call_args_list[-1][0][0], ["wl-copy"])

    @mock.patch("poe_trade.exilelens.system_clipboard.shutil.which")
    @mock.patch("poe_trade.exilelens.system_clipboard.subprocess.run")
    def test_fallback_to_xclip_when_wayland_missing(self, mock_run, mock_which) -> None:
        mock_which.side_effect = lambda name: f"/usr/bin/{name}" if name == "xclip" else None
        mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="item")
        clipboard = SystemClipboard()
        self.assertEqual(clipboard.read_text(), "item")
        clipboard.write_text("copy")
        self.assertEqual(mock_run.call_args_list[-1][0][0], ["xclip", "-selection", "clipboard"])

    @mock.patch("poe_trade.exilelens.system_clipboard.shutil.which", return_value=None)
    def test_missing_tools_raise(self, mock_which) -> None:
        with self.assertRaises(ClipboardUnavailable):
            SystemClipboard()


class SystemOCRTests(unittest.TestCase):
    @mock.patch("poe_trade.exilelens.system_ocr.shutil.which")
    @mock.patch("poe_trade.exilelens.system_ocr.subprocess.run")
    def test_uses_grim_and_tesseract(self, mock_run, mock_which) -> None:
        def which(name: str) -> str | None:
            if name in {"grim", "tesseract"}:
                return f"/usr/bin/{name}"
            return None

        mock_which.side_effect = which

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "grim":
                return subprocess.CompletedProcess(args=cmd, returncode=0)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ocr")

        mock_run.side_effect = run_side_effect
        ocr = SystemOCR(SessionType.WAYLAND)
        with mock.patch.object(SystemOCR, "_image_to_base64", return_value="encoded"):
            text, image = ocr.capture_text(ROIConfig(1, 2, 3, 4))
        self.assertEqual(text, "ocr")
        self.assertEqual(image, "encoded")
        first_call = mock_run.call_args_list[0][0][0]
        self.assertEqual(first_call[0], "grim")
        self.assertIn("-g", first_call)
        self.assertIn("1,2 3x4", first_call)

    @mock.patch("poe_trade.exilelens.system_ocr.shutil.which")
    @mock.patch("poe_trade.exilelens.system_ocr.subprocess.run")
    def test_falls_back_to_maim_on_x11(self, mock_run, mock_which) -> None:
        def which(name: str) -> str | None:
            if name in {"maim", "tesseract"}:
                return f"/usr/bin/{name}"
            return None

        mock_which.side_effect = which

        def run_side_effect(cmd, **kwargs):
            if cmd[0] == "maim":
                return subprocess.CompletedProcess(args=cmd, returncode=0)
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ocr")

        mock_run.side_effect = run_side_effect
        ocr = SystemOCR(SessionType.X11)
        with mock.patch.object(SystemOCR, "_image_to_base64", return_value="encoded"):
            text, image = ocr.capture_text()
        self.assertEqual(text, "ocr")
        self.assertEqual(image, "encoded")
        self.assertEqual(mock_run.call_args_list[0][0][0][0], "maim")


class CopyFieldHelperTests(unittest.TestCase):
    class _RecordingClipboard:
        def __init__(self) -> None:
            self.values: list[str] = []

        def write_text(self, value: str) -> None:
            self.values.append(value)

    def test_copy_field_writes_selected_price(self) -> None:
        clipboard = self._RecordingClipboard()
        result = {"price": {"est_chaos": 123}}
        copied = _copy_price_field(result, "est_chaos", clipboard)
        self.assertTrue(copied)
        self.assertEqual(clipboard.values, ["123"])

    def test_copy_field_handles_missing_price(self) -> None:
        clipboard = self._RecordingClipboard()
        result: dict = {}
        copied = _copy_price_field(result, "list_fast", clipboard)
        self.assertFalse(copied)
        self.assertEqual(clipboard.values, [])

    def test_copy_field_uses_nested_price_block(self) -> None:
        clipboard = self._RecordingClipboard()
        result = {"result": {"price": {"list_normal": "4.5"}}}
        copied = _copy_price_field(result, "list_normal", clipboard)
        self.assertTrue(copied)
        self.assertEqual(clipboard.values, ["4.5"])


if __name__ == "__main__":
    unittest.main()
