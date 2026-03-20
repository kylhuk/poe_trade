from __future__ import annotations

from types import SimpleNamespace

from poe_trade.services import account_stash_harvester as service


def test_service_exits_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        service.config_settings,
        "get_settings",
        lambda: SimpleNamespace(enable_account_stash=False),
    )
    assert service.main([]) == 0


def test_service_no_ops_without_temporary_credential(monkeypatch) -> None:
    monkeypatch.setattr(
        service.config_settings,
        "get_settings",
        lambda: SimpleNamespace(
            enable_account_stash=True,
        ),
    )
    monkeypatch.setattr(
        service,
        "load_credential_state",
        lambda _cfg: {
            "account_name": "",
            "poe_session_id": "",
            "status": "logged_out",
            "updated_at": "2026-03-14T00:00:00Z",
        },
    )

    class _UnexpectedClient:
        def __init__(self, *_args, **_kwargs):
            raise AssertionError("PoeClient should not be created during no-op")

    monkeypatch.setattr(service, "PoeClient", _UnexpectedClient)

    assert service.main([]) == 0


def test_service_uses_server_credential_state_for_cookie_and_scope(monkeypatch) -> None:
    cfg = SimpleNamespace(
        enable_account_stash=True,
        rate_limit_max_retries=1,
        rate_limit_backoff_base=0.1,
        rate_limit_backoff_max=0.2,
        rate_limit_jitter=0.0,
        poe_api_base_url="https://poe.example",
        poe_user_agent="ua",
        poe_request_timeout=2.0,
        clickhouse_url="http://clickhouse",
        account_stash_realm="pc",
        account_stash_league="Mirage",
        account_stash_poll_interval=30.0,
    )
    monkeypatch.setattr(service.config_settings, "get_settings", lambda: cfg)
    monkeypatch.setattr(
        service,
        "load_credential_state",
        lambda _cfg: {
            "account_name": "qa-exile",
            "poe_session_id": "POESESSID-123",
            "status": "bootstrap_connected",
            "updated_at": "2026-03-14T00:00:00Z",
        },
    )

    class _DummyClient:
        def __init__(self, *_args, **_kwargs):
            return None

    class _DummyClickHouse:
        @classmethod
        def from_env(cls, _url):
            return object()

    class _DummyStatusReporter:
        def __init__(self, _client, _service_name):
            return None

    created: dict[str, object] = {}

    class _DummyHarvester:
        def __init__(self, _client, _clickhouse, _status, **kwargs):
            created["kwargs"] = kwargs

        def run(self, **kwargs):
            created["run"] = kwargs

    monkeypatch.setattr(service, "PoeClient", _DummyClient)
    monkeypatch.setattr(service, "ClickHouseClient", _DummyClickHouse)
    monkeypatch.setattr(service, "StatusReporter", _DummyStatusReporter)
    monkeypatch.setattr(service, "AccountStashHarvester", _DummyHarvester)

    assert service.main(["--once"]) == 0
    assert created["kwargs"] == {
        "service_name": "account_stash_harvester",
        "account_name": "qa-exile",
        "request_headers": {"Cookie": "POESESSID=POESESSID-123"},
    }
    assert created["run"] == {
        "realm": "pc",
        "league": "Mirage",
        "interval": 30.0,
        "dry_run": False,
        "once": True,
    }
