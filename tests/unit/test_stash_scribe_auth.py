import json
import threading
import time
import unittest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from poe_trade.ingestion.stash_scribe import (
    StashScribe,
    OAuthClient,
    OAuthToken,
    create_trigger_app,
)


class FakePoeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params, data, headers))
        if not self._responses:
            raise RuntimeError("no response")
        return self._responses.pop(0)

    def set_bearer_token(self, token):
        self.token = token


class _StubPoeClient:
    def set_bearer_token(self, token):
        self.token = token


class _StubAuthClient:
    def refresh(self):
        return OAuthToken(access_token="access", expires_in=60)


class _StubCheckpointStore:
    def read(self, key):
        return None

    def write(self, key, value):
        pass


class _StubStatusReporter:
    def report(self, *args, **kwargs):
        pass


class _StubClickHouseClient:
    def execute(self, query):
        pass


class DummyTriggerService:
    def __init__(self):
        self.calls = 0
        self.dry_runs: list[bool] = []

    def capture_snapshot(self, dry_run: bool):
        self.calls += 1
        self.dry_runs.append(dry_run)


class StashScribeAuthTests(unittest.TestCase):
    def test_refresh_uses_client_credentials_scope(self):
        fake = FakePoeClient([
            {"access_token": "abc", "refresh_token": "ref", "expires_in": 60}
        ])
        client = OAuthClient(
            fake,
            "cid",
            "secret",
            "client_credentials",
            "service:psapi",
        )
        token = client.refresh()
        self.assertIsInstance(token, OAuthToken)
        self.assertEqual(token.access_token, "abc")
        self.assertEqual(token.refresh_token, "ref")
        self.assertEqual(
            fake.calls[0][3],
            {
                "grant_type": "client_credentials",
                "client_id": "cid",
                "client_secret": "secret",
                "scope": "service:psapi",
            },
        )

    def test_refresh_defaults_expires_when_missing(self):
        fake = FakePoeClient([
            {
                "access_token": "abc",
                "refresh_token": "ref",
                "expires_in": None,
            }
        ])
        client = OAuthClient(
            fake,
            "cid",
            "secret",
            "client_credentials",
            "service:psapi",
        )
        token = client.refresh()
        self.assertIsInstance(token, OAuthToken)
        self.assertEqual(token.refresh_token, "ref")

    def test_capture_lock_blocks_concurrent_runs(self):
        service = StashScribe(
            _StubPoeClient(),
            _StubAuthClient(),
            _StubClickHouseClient(),
            _StubCheckpointStore(),
            _StubStatusReporter(),
            "Synthesis",
            "pc",
        )
        entries: list[str] = []
        started = threading.Event()
        release = threading.Event()

        def fake_perform(dry_run: bool):
            entries.append(str(len(entries)))
            if len(entries) == 1:
                started.set()
                release.wait(5)

        service._perform_capture = fake_perform

        first = threading.Thread(target=lambda: service.capture_snapshot(False))
        first.start()
        self.assertTrue(started.wait(1), "first capture did not start in time")

        second = threading.Thread(target=lambda: service.capture_snapshot(False))
        second.start()
        time.sleep(0.05)
        self.assertEqual(len(entries), 1)

        release.set()
        first.join(1)
        second.join(1)
        self.assertEqual(len(entries), 2)


class StashScribePayloadTests(unittest.TestCase):
    def test_api_path_follows_configuration(self):
        fake = FakePoeClient([
            {
                "next_change_id": "next",
                "tabs": [],
            }
        ])
        service = StashScribe(
            fake,
            _StubAuthClient(),
            _StubClickHouseClient(),
            _StubCheckpointStore(),
            _StubStatusReporter(),
            "Synthesis",
            "pc",
            stash_api_path="public-stash-tabs",
        )
        service.capture_snapshot(dry_run=True)
        self.assertEqual(fake.calls[0][1], "public-stash-tabs")

    def test_rows_handle_tabs(self):
        service = StashScribe(
            FakePoeClient([]),
            _StubAuthClient(),
            _StubClickHouseClient(),
            _StubCheckpointStore(),
            _StubStatusReporter(),
            "Synthesis",
            "pc",
        )
        now = datetime(2025, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        tab = {
            "id": 42,
            "label": "alpha",
        }
        rows = service._rows(
            {
                "next_change_id": "next",
                "tabs": [tab],
            },
            now,
        )
        captured = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.assertEqual(
            rows,
            [
                {
                    "snapshot_id": f"stash:42:{captured}",
                    "captured_at": captured,
                    "realm": "pc",
                    "league": "Synthesis",
                    "tab_id": "42",
                    "next_change_id": "next",
                    "payload_json": json.dumps(tab, ensure_ascii=False),
                }
            ],
        )

    def test_rows_handle_stashes(self):
        service = StashScribe(
            FakePoeClient([]),
            _StubAuthClient(),
            _StubClickHouseClient(),
            _StubCheckpointStore(),
            _StubStatusReporter(),
            "Synthesis",
            "pc",
        )
        now = datetime(2025, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
        stash = {
            "stash_id": "public-1",
            "label": "public",
        }
        rows = service._rows(
            {
                "next_change_id": "next",
                "stashes": [stash],
            },
            now,
        )
        captured = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        self.assertEqual(
            rows,
            [
                {
                    "snapshot_id": f"stash:public-1:{captured}",
                    "captured_at": captured,
                    "realm": "pc",
                    "league": "Synthesis",
                    "tab_id": "public-1",
                    "next_change_id": "next",
                    "payload_json": json.dumps(stash, ensure_ascii=False),
                }
            ],
        )


class TriggerEndpointTests(unittest.TestCase):
    def test_trigger_disabled_without_token(self):
        service = DummyTriggerService()
        client = TestClient(create_trigger_app(service, None))
        response = client.post("/trigger")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(service.calls, 0)

    def test_trigger_requires_valid_token(self):
        service = DummyTriggerService()
        token = "secret"
        client = TestClient(create_trigger_app(service, token))
        response = client.post("/trigger")
        self.assertEqual(response.status_code, 401)
        response = client.post("/trigger", headers={"X-Trigger-Token": "wrong"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(service.calls, 0)
        response = client.post("/trigger", headers={"X-Trigger-Token": token})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.calls, 1)


if __name__ == "__main__":
    unittest.main()
