import logging
from types import SimpleNamespace
import types

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


class _DummySyncStateStore:
    def __init__(self, client):
        self.client = client


class _DummyRateLimitPolicy:
    def __init__(self, *_args, **_kwargs):
        pass


class _DummyCxapiSync:
    def __init__(self, *_args, **_kwargs):
        pass


def test_main_returns_error_when_oauth_precheck_fails(monkeypatch, caplog):
    caplog.set_level(logging.ERROR, logger=market_harvester.LOGGER.name)

    monkeypatch.setattr(market_harvester, "PoeClient", _DummyPoeClient)
    monkeypatch.setattr(market_harvester, "ClickHouseClient", _DummyClickHouseClient)
    monkeypatch.setattr(market_harvester, "StatusReporter", _DummyStatusReporter)
    monkeypatch.setattr(market_harvester, "SyncStateStore", _DummySyncStateStore)
    monkeypatch.setattr(market_harvester, "RateLimitPolicy", _DummyRateLimitPolicy)
    monkeypatch.setattr(market_harvester, "CxapiSync", _DummyCxapiSync)

    instantiated = []

    class _DummyMarketHarvester:
        def __init__(self, *_args, **_kwargs):
            instantiated.append(True)

    monkeypatch.setattr(market_harvester, "MarketHarvester", _DummyMarketHarvester)

    def _unexpected_scheduler(**_kwargs):
        raise AssertionError("scheduler should not run when OAuth is missing")

    monkeypatch.setattr(
        market_harvester.importlib,
        "import_module",
        lambda _name: types.SimpleNamespace(run_market_sync=_unexpected_scheduler),
    )

    monkeypatch.setattr(
        market_harvester.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            realms=("pc",),
            leagues=("Synthesis",),
            market_poll_interval=1.0,
            psapi_poll_seconds=1.0,
            enable_psapi=True,
            enable_cxapi=False,
            cxapi_hour_offset_seconds=15,
            refresh_refs_minutes=5,
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
    monkeypatch.setattr(market_harvester, "SyncStateStore", _DummySyncStateStore)
    monkeypatch.setattr(market_harvester, "RateLimitPolicy", _DummyRateLimitPolicy)
    monkeypatch.setattr(market_harvester, "CxapiSync", _DummyCxapiSync)

    instances = []
    scheduler_calls = []

    class _DummyMarketHarvester:
        def __init__(self, *_args, auth_client=None, **_kwargs):
            instances.append(auth_client)

    monkeypatch.setattr(market_harvester, "MarketHarvester", _DummyMarketHarvester)

    def _record_scheduler(**kwargs):
        scheduler_calls.append(kwargs)

    monkeypatch.setattr(
        market_harvester.importlib,
        "import_module",
        lambda _name: types.SimpleNamespace(run_market_sync=_record_scheduler),
    )

    monkeypatch.setattr(
        market_harvester.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            realms=("pc",),
            leagues=("Synthesis",),
            market_poll_interval=1.0,
            psapi_poll_seconds=1.0,
            enable_psapi=True,
            enable_cxapi=False,
            cxapi_hour_offset_seconds=15,
            refresh_refs_minutes=5,
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
    assert len(scheduler_calls) == 1
    assert scheduler_calls[0]["realms"] == ("pc",)
    assert scheduler_calls[0]["leagues"] == ("Synthesis",)
    assert scheduler_calls[0]["poll_interval"] == 1.0
    assert scheduler_calls[0]["dry_run"] is False
    assert scheduler_calls[0]["once"] is False
    assert scheduler_calls[0]["harvester"] is not None
    assert scheduler_calls[0]["cx_sync"] is None
    assert scheduler_calls[0]["refresh_client"] is not None
    assert scheduler_calls[0]["refresh_refs_minutes"] == 5


def test_main_exits_cleanly_when_both_feeds_disabled(monkeypatch):
    monkeypatch.setattr(
        market_harvester.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            realms=("pc",),
            leagues=("Synthesis",),
            market_poll_interval=1.0,
            psapi_poll_seconds=1.0,
            enable_psapi=False,
            enable_cxapi=False,
            cxapi_hour_offset_seconds=15,
            refresh_refs_minutes=5,
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

    called = []
    monkeypatch.setattr(
        market_harvester, "oauth_client_factory", lambda _: called.append(True)
    )

    result = market_harvester.main([])

    assert result == 0
    assert called == []


def test_main_runs_cx_only_when_psapi_disabled(monkeypatch):
    sentinel_auth = object()

    monkeypatch.setattr(market_harvester, "PoeClient", _DummyPoeClient)
    monkeypatch.setattr(market_harvester, "ClickHouseClient", _DummyClickHouseClient)
    monkeypatch.setattr(market_harvester, "StatusReporter", _DummyStatusReporter)
    monkeypatch.setattr(market_harvester, "SyncStateStore", _DummySyncStateStore)
    monkeypatch.setattr(market_harvester, "RateLimitPolicy", _DummyRateLimitPolicy)

    created_cx = []
    scheduler_calls = []

    class _RecordingCxapiSync:
        def __init__(self, *_args, **_kwargs):
            created_cx.append(_kwargs)

    monkeypatch.setattr(market_harvester, "CxapiSync", _RecordingCxapiSync)

    class _UnexpectedHarvester:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError(
                "PSAPI harvester should not be created for CX-only mode"
            )

    monkeypatch.setattr(market_harvester, "MarketHarvester", _UnexpectedHarvester)

    def _record_scheduler(**kwargs):
        scheduler_calls.append(kwargs)

    monkeypatch.setattr(
        market_harvester.importlib,
        "import_module",
        lambda _name: types.SimpleNamespace(run_market_sync=_record_scheduler),
    )
    monkeypatch.setattr(
        market_harvester.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            realms=("pc",),
            leagues=("Synthesis",),
            market_poll_interval=1.0,
            psapi_poll_seconds=1.0,
            enable_psapi=False,
            enable_cxapi=True,
            cxapi_hour_offset_seconds=15,
            refresh_refs_minutes=5,
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
    assert len(created_cx) == 1
    assert created_cx[0]["auth_client"] is sentinel_auth
    assert len(scheduler_calls) == 1
    assert scheduler_calls[0]["harvester"] is None
    assert scheduler_calls[0]["cx_sync"] is not None
    assert scheduler_calls[0]["refresh_client"] is not None
    assert scheduler_calls[0]["refresh_refs_minutes"] == 5
