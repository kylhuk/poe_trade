import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from poe_trade.api import get_app

client = TestClient(get_app())


class BridgeRoutesTest(unittest.TestCase):
    def test_manual_trigger_guard_for_every_bridge_route(self):
        cases = [
            ("/v1/bridge/capture-screen", {"manual_trigger": False}),
            ("/v1/bridge/clipboard/read", {"manual_trigger": False}),
            ("/v1/bridge/clipboard/write", {"manual_trigger": False, "value": "text"}),
            (
                "/v1/bridge/overlay/push",
                {"manual_trigger": False, "payload": {"items": []}},
            ),
            (
                "/v1/bridge/filter/write",
                {"manual_trigger": False, "contents": ""},
            ),
        ]
        for path, payload in cases:
            response = client.post(path, json=payload)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data.get("success"))
            self.assertFalse(data.get("payload", {}).get("manual_trigger"))
            self.assertIn("action", data)
            self.assertIn("manual trigger required", data.get("message", "").lower())

    def test_missing_manual_trigger_defaults_to_guarded_failure(self):
        response = client.post("/v1/bridge/capture-screen", json={})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data.get("success"))
        self.assertFalse(data.get("payload", {}).get("manual_trigger"))
        self.assertIn("manual trigger required", data.get("message", "").lower())

    def test_manual_token_guard_when_server_token_set(self):
        with patch.dict("os.environ", {"POE_LEDGER_BRIDGE_MANUAL_TOKEN": "token-123"}):
            response = client.post(
                "/v1/bridge/overlay/push",
                json={"manual_trigger": True, "payload": {"items": []}},
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertFalse(data.get("success"))
            self.assertIn("token", data.get("message", "").lower())

    def test_manual_token_allows_progress_past_guard(self):
        with patch.dict("os.environ", {"POE_LEDGER_BRIDGE_MANUAL_TOKEN": "token-123"}):
            response = client.post(
                "/v1/bridge/overlay/push",
                json={
                    "manual_trigger": True,
                    "manual_token": "token-123",
                    "payload": {"items": []},
                },
            )
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertNotIn(
                "token missing or invalid", data.get("message", "").lower()
            )
