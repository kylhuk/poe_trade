import unittest
from types import SimpleNamespace

from poe_trade.db import ClickHouseClient
from poe_trade.ingestion.market_harvester import (
    MarketHarvester,
    OAuthClient,
    OAuthToken,
    oauth_client_factory,
)
from poe_trade.ingestion.poe_client import PoeClient, PoeResponse
from poe_trade.ingestion.rate_limit import RateLimitPolicy
from poe_trade.ingestion.status import StatusReporter
from poe_trade.ingestion.sync_state import QueueState, SyncStateStore


class _DummyMetadataResponse(PoeResponse):
    def __init__(self, payload):
        super().__init__(payload, {}, 200, 1, 0.0)


class _StubPoeClient(PoeClient):
    def __init__(self):
        super().__init__(
            "http://poe.example", RateLimitPolicy(1, 0.1, 0.2, 0.0), "test-agent", 1.0
        )
        self.bearer = None
        self.calls: list[
            tuple[str, str, object | None, object | None, object | None]
        ] = []

    def set_bearer_token(self, token: str | None) -> None:
        self.bearer = token

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params, data, headers))
        return {"next_change_id": "abc", "stashes": []}

    def request_with_metadata(self, method, path, params=None, data=None, headers=None):
        payload = self.request(method, path, params=params, data=data, headers=headers)
        return _DummyMetadataResponse(payload)


class _StubClickHouseClient(ClickHouseClient):
    def __init__(self):
        super().__init__(endpoint="http://clickhouse")

    def execute(self, query):
        return ""


class _StubSyncStateStore(SyncStateStore):
    def __init__(self):
        super().__init__(_StubClickHouseClient())
        self.calls = []

    def latest_cursor(self, queue_key, *, statuses=("success", "idle")):
        self.calls.append((queue_key, tuple(statuses)))
        return None

    def latest_state(self, queue_key, *, statuses=("success", "idle")):
        return None


class _StubStatusReporter(StatusReporter):
    def __init__(self):
        super().__init__(_StubClickHouseClient(), "test")

    def report(self, *args, **kwargs):
        return None


class _StubAuthClient(OAuthClient):
    def __init__(self) -> None:
        super().__init__(
            _StubPoeClient(), "client", "secret", "client_credentials", "service:psapi"
        )
        self.calls = 0

    def refresh(self) -> OAuthToken:
        self.calls += 1
        return OAuthToken(access_token=f"token-{self.calls}", expires_in=60)


class MarketHarvesterAuthTests(unittest.TestCase):
    def test_oauth_factory_requires_enabled_feed_scopes(self):
        settings = SimpleNamespace(
            oauth_client_id="client",
            oauth_client_secret="secret",
            oauth_grant_type="client_credentials",
            oauth_scope="service:psapi",
            enable_psapi=True,
            enable_cxapi=True,
            rate_limit_max_retries=1,
            rate_limit_backoff_base=0.1,
            rate_limit_backoff_max=0.2,
            rate_limit_jitter=0.0,
            poe_auth_base_url="https://auth.example",
            poe_user_agent="test-agent",
            poe_request_timeout=1.0,
        )

        with self.assertRaisesRegex(ValueError, "service:cxapi"):
            oauth_client_factory(settings)

    def test_refreshes_token_before_harvest(self):
        client = _StubPoeClient()
        auth_client = _StubAuthClient()
        harvester = MarketHarvester(
            client,
            _StubClickHouseClient(),
            _StubSyncStateStore(),
            _StubStatusReporter(),
            auth_client=auth_client,
        )
        harvester._harvest("pc", "Synthesis", dry_run=True)
        self.assertEqual(auth_client.calls, 1)
        self.assertEqual(client.bearer, "token-1")

    def test_token_cached_while_valid(self):
        client = _StubPoeClient()
        auth_client = _StubAuthClient()
        harvester = MarketHarvester(
            client,
            _StubClickHouseClient(),
            _StubSyncStateStore(),
            _StubStatusReporter(),
            auth_client=auth_client,
        )
        harvester._harvest("pc", "Synthesis", dry_run=True)
        harvester._harvest("pc", "Synthesis", dry_run=True)
        self.assertEqual(auth_client.calls, 1)
