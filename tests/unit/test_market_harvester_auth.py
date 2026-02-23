import unittest

from poe_trade.ingestion.market_harvester import MarketHarvester
from poe_trade.ingestion.stash_scribe import OAuthToken


class _StubPoeClient:
    def __init__(self):
        self.bearer = None
        self.calls: list[tuple[str, str, dict[str, str] | None, object | None, object | None]] = []

    def set_bearer_token(self, token: str | None) -> None:
        self.bearer = token

    def request(self, method, path, params=None, data=None, headers=None):
        self.calls.append((method, path, params, data, headers))
        return {"next_change_id": "abc", "stashes": []}


class _StubClickHouseClient:
    def execute(self, query):
        pass


class _StubCheckpointStore:
    def read(self, key):
        return None

    def write(self, key, value):
        pass


class _StubStatusReporter:
    def report(self, *args, **kwargs):
        pass


class _StubAuthClient:
    def __init__(self) -> None:
        self.calls = 0

    def refresh(self) -> OAuthToken:
        self.calls += 1
        return OAuthToken(access_token=f"token-{self.calls}", expires_in=60)


class MarketHarvesterAuthTests(unittest.TestCase):
    def test_refreshes_token_before_harvest(self):
        client = _StubPoeClient()
        auth_client = _StubAuthClient()
        harvester = MarketHarvester(
            client,
            _StubClickHouseClient(),
            _StubCheckpointStore(),
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
            _StubCheckpointStore(),
            _StubStatusReporter(),
            auth_client=auth_client,
        )
        harvester._harvest("pc", "Synthesis", dry_run=True)
        harvester._harvest("pc", "Synthesis", dry_run=True)
        self.assertEqual(auth_client.calls, 1)
