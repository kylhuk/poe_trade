import logging
from types import SimpleNamespace

from poe_trade.services import market_harvester


class _DummyPoeClient:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummyClickHouseClient:
    def __init__(self, url: str):
        self.url = url

    @classmethod
    def from_env(cls, url: str):
        return cls(url)


class _DummyStatusReporter:
    def __init__(self, client, service_name: str):
        self.client = client
        self.service_name = service_name


class _DummyCheckpointStore:
    def __init__(self, path: str):
        self.path = path


class _DummyRateLimitPolicy:
    def __init__(self, *_args, **_kwargs):
        pass


def test_main_returns_error_when_oauth_precheck_fails(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=market_harvester.LOGGER.name)

    monkeypatch.setattr(market_harvester, "PoeClient", _DummyPoeClient)
    monkeypatch.setattr(market_harvester, "ClickHouseClient", _DummyClickHouseClient)
    monkeypatch.setattr(market_harvester, "StatusReporter", _DummyStatusReporter)
    monkeypatch.setattr(market_harvester, "CheckpointStore", _DummyCheckpointStore)
    monkeypatch.setattr(market_harvester, "RateLimitPolicy", _DummyRateLimitPolicy)

    instantiated = []

    class _DummyMarketHarvester:
        def __init__(self, *_args, **_kwargs):
            instantiated.append(True)

        def run(self, *_args, **_kwargs):
            raise AssertionError("MarketHarvester should not run when OAuth is missing")

    monkeypatch.setattr(market_harvester, "MarketHarvester", _DummyMarketHarvester)

    monkeypatch.setattr(
        market_harvester.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            realms=("pc",),
            leagues=("Synthesis",),
            market_poll_interval=1.0,
            stash_bootstrap_until_league="",
            stash_bootstrap_from_beginning=False,
            rate_limit_max_retries=1,
            rate_limit_backoff_base=0.1,
            rate_limit_backoff_max=0.2,
            rate_limit_jitter=0.0,
            poe_api_base_url="https://poe.example",
            poe_user_agent="test-agent",
            poe_request_timeout=1.0,
            clickhouse_url="http://clickhouse",
            checkpoint_dir="/tmp",
        ),
    )

    def _raise_missing(oauth_settings):
        raise ValueError("missing oauth")

    monkeypatch.setattr(market_harvester, "oauth_client_factory", _raise_missing)

    result = market_harvester.main([])

    assert result == 1
    assert "Missing or invalid OAuth configuration" in caplog.text
    assert "POE_OAUTH_CLIENT_ID" in caplog.text
    assert "POE_OAUTH_CLIENT_SECRET" in caplog.text
    assert not instantiated


def test_main_runs_harvester_when_oauth_precheck_succeeds(monkeypatch):
    sentinel_auth = object()

    monkeypatch.setattr(market_harvester, "PoeClient", _DummyPoeClient)
    monkeypatch.setattr(market_harvester, "ClickHouseClient", _DummyClickHouseClient)
    monkeypatch.setattr(market_harvester, "StatusReporter", _DummyStatusReporter)
    monkeypatch.setattr(market_harvester, "CheckpointStore", _DummyCheckpointStore)
    monkeypatch.setattr(market_harvester, "RateLimitPolicy", _DummyRateLimitPolicy)

    instances = []
    run_calls = []

    class _DummyMarketHarvester:
        def __init__(self, *_args, auth_client=None, **_kwargs):
            instances.append(auth_client)

        def run(self, realms, leagues, poll_interval, dry_run=False, once=False):
            run_calls.append(
                {
                    "realms": realms,
                    "leagues": leagues,
                    "poll_interval": poll_interval,
                    "dry_run": dry_run,
                    "once": once,
                }
            )

    monkeypatch.setattr(market_harvester, "MarketHarvester", _DummyMarketHarvester)

    monkeypatch.setattr(
        market_harvester.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            realms=("pc",),
            leagues=("Synthesis",),
            market_poll_interval=1.0,
            stash_bootstrap_until_league="",
            stash_bootstrap_from_beginning=False,
            rate_limit_max_retries=1,
            rate_limit_backoff_base=0.1,
            rate_limit_backoff_max=0.2,
            rate_limit_jitter=0.0,
            poe_api_base_url="https://poe.example",
            poe_user_agent="test-agent",
            poe_request_timeout=1.0,
            clickhouse_url="http://clickhouse",
            checkpoint_dir="/tmp",
        ),
    )

    monkeypatch.setattr(
        market_harvester, "oauth_client_factory", lambda _: sentinel_auth
    )

    result = market_harvester.main([])

    assert result == 0
    assert instances == [sentinel_auth]
    assert len(run_calls) == 1
    assert run_calls[0]["realms"] == ["pc"]
    assert run_calls[0]["leagues"] == ["Synthesis"]
    assert run_calls[0]["poll_interval"] == 1.0
    assert run_calls[0]["dry_run"] is False
    assert run_calls[0]["once"] is False
