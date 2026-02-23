"""Tests for Ledger API client's bridge wiring."""

from __future__ import annotations

import httpx
import os
import unittest
from unittest.mock import MagicMock, patch

from poe_trade.bridge.local_bridge import BridgeResult
from poe_trade.ui import client as ui_client


class LedgerUiClientBridgeTests(unittest.TestCase):
    def test_bridge_disabled_returns_failure(self) -> None:
        with patch.dict(os.environ, {"POE_LEDGER_UI_DISABLE_LOCAL_BRIDGE": "1"}):
            client = ui_client.LedgerApiClient(local_mode=True)
        result = client.bridge_capture_screen(manual_trigger=True)
        self.assertFalse(result.success)
        self.assertIn("disabled", result.message.lower())
        self.assertTrue(result.payload.get("bridge_disabled"))

    @patch("poe_trade.ui.client.clipboard_read")
    @patch("poe_trade.ui.client.SystemClipboard")
    def test_clipboard_read_delegates(
        self, mock_clipboard_cls: MagicMock, mock_clipboard_read: MagicMock
    ) -> None:
        fake_clipboard = MagicMock()
        mock_clipboard_cls.return_value = fake_clipboard
        expected = BridgeResult(
            action="clipboard_read",
            success=True,
            message="ok",
            payload={"manual_trigger": True, "value": "x"},
        )
        mock_clipboard_read.return_value = expected
        client = ui_client.LedgerApiClient(local_mode=True)
        result = client.bridge_clipboard_read(manual_trigger=True)
        self.assertIs(result, expected)
        mock_clipboard_cls.assert_called_once()
        mock_clipboard_read.assert_called_once_with(fake_clipboard, manual_trigger=True)

    def test_capture_handles_ocr_unavailable(self) -> None:
        class RisingOCR:
            def __init__(self) -> None:
                raise ui_client.OcrUnavailable("missing")

        with patch("poe_trade.ui.client.SystemOCR", side_effect=RisingOCR):
            client = ui_client.LedgerApiClient(local_mode=True)
            result = client.bridge_capture_screen(manual_trigger=True)
        self.assertFalse(result.success)
        self.assertIn("ocr unavailable", result.message.lower())
        self.assertEqual(result.payload.get("manual_trigger"), True)

    @patch("poe_trade.ui.client.push_overlay_payload")
    def test_overlay_push_uses_default_queue(self, mock_push: MagicMock) -> None:
        expected = BridgeResult(
            action="push_overlay_payload",
            success=True,
            message="pushed",
            payload={"manual_trigger": True},
        )
        mock_push.return_value = expected
        client = ui_client.LedgerApiClient(local_mode=True)
        result = client.bridge_push_overlay_payload(
            payload={"foo": "bar"}, manual_trigger=True
        )
        self.assertIs(result, expected)
        mock_push.assert_called_once()
        path_arg = mock_push.call_args[0][0]
        self.assertEqual(path_arg, ui_client.LedgerApiClient.DEFAULT_OVERLAY_QUEUE_PATH)

    @patch.object(ui_client.LedgerApiClient, "_request")
    def test_remote_clipboard_read_invokes_api(self, mock_request: MagicMock) -> None:
        client = ui_client.LedgerApiClient(local_mode=False)
        response_payload = {
            "action": "clipboard_read",
            "success": True,
            "message": "remote",
            "payload": {"manual_trigger": True, "value": "remote"},
        }
        mock_request.return_value = response_payload
        result = client.bridge_clipboard_read(manual_trigger=True)
        self.assertEqual(result, BridgeResult(**response_payload))
        mock_request.assert_called_once_with(
            "POST",
            "/v1/bridge/clipboard/read",
            json={"manual_trigger": True},
        )

    @patch.object(ui_client.LedgerApiClient, "_request")
    def test_remote_filter_write_calls_api(self, mock_request: MagicMock) -> None:
        client = ui_client.LedgerApiClient(local_mode=False)
        response_payload = {
            "action": "write_item_filter",
            "success": True,
            "message": "remote",
            "payload": {"manual_trigger": True},
        }
        mock_request.return_value = response_payload
        result = client.bridge_write_item_filter(
            "# contents",
            manual_trigger=True,
            filter_path="/tmp/custom.filter",
            backup_path="/tmp/custom.filter.bak",
        )
        self.assertEqual(result, BridgeResult(**response_payload))
        mock_request.assert_called_once_with(
            "POST",
            "/v1/bridge/filter/write",
            json={
                "manual_trigger": True,
                "contents": "# contents",
                "filter_path": "/tmp/custom.filter",
                "backup_path": "/tmp/custom.filter.bak",
            },
        )

    @patch.object(ui_client.LedgerApiClient, "_request")
    def test_remote_request_adds_manual_token_when_configured(
        self, mock_request: MagicMock
    ) -> None:
        response_payload = {
            "action": "clipboard_read",
            "success": False,
            "message": "manual trigger required for local bridge actions",
            "payload": {"manual_trigger": False},
        }
        mock_request.return_value = response_payload
        with patch.dict(os.environ, {"POE_LEDGER_UI_BRIDGE_MANUAL_TOKEN": "ui-token"}):
            client = ui_client.LedgerApiClient(local_mode=False)
        _ = client.bridge_clipboard_read(manual_trigger=True)
        mock_request.assert_called_once_with(
            "POST",
            "/v1/bridge/clipboard/read",
            json={"manual_trigger": True, "manual_token": "ui-token"},
        )

    def test_disabled_bridge_short_circuits_remote(self) -> None:
        with patch.dict(os.environ, {"POE_LEDGER_UI_DISABLE_LOCAL_BRIDGE": "1"}):
            client = ui_client.LedgerApiClient(local_mode=False)
        with patch.object(client, "_request") as mock_request:
            result = client.bridge_clipboard_read(manual_trigger=True)
        self.assertFalse(result.success)
        mock_request.assert_not_called()

    def test_remote_bridge_error_propagates(self) -> None:
        client = ui_client.LedgerApiClient(local_mode=False)
        request = httpx.Request("POST", "https://example")
        response = httpx.Response(500, request=request)
        error = httpx.HTTPStatusError("boom", request=request, response=response)
        with patch.object(client, "_request", side_effect=error):
            with self.assertRaises(httpx.HTTPStatusError):
                client.bridge_clipboard_read(manual_trigger=True)


if __name__ == "__main__":
    unittest.main()
