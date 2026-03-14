from __future__ import annotations

import json
import os
from io import BytesIO
from unittest import mock

import pytest

from poe_trade.api.app import ApiApp
from poe_trade.api.responses import ApiError
from poe_trade.api.service_control import ServiceControlError, ServiceSnapshot
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


def _settings() -> Settings:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_API_CORS_ORIGINS": "https://app.example.com",
        "POE_API_MAX_BODY_BYTES": "32768",
        "POE_API_LEAGUE_ALLOWLIST": "Mirage",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        return Settings.from_env()


def _settings_with_stash_enabled() -> Settings:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_API_CORS_ORIGINS": "https://app.example.com",
        "POE_API_MAX_BODY_BYTES": "32768",
        "POE_API_LEAGUE_ALLOWLIST": "Mirage",
        "POE_ENABLE_ACCOUNT_STASH": "true",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        return Settings.from_env()


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer phase1-token",
        "Origin": "https://app.example.com",
    }


def _snapshot_rows() -> list[ServiceSnapshot]:
    return [
        ServiceSnapshot(
            id="market_harvester",
            name="Market Harvester",
            description="Public stash and exchange ingestion daemon",
            status="running",
            uptime=None,
            last_crawl="2026-03-13T00:00:00Z",
            rows_in_db=123,
            container_info="market_harvester",
            type="crawler",
            allowed_actions=("start", "stop", "restart"),
        ),
        ServiceSnapshot(
            id="api",
            name="API",
            description="Protected backend API service",
            status="running",
            uptime=None,
            last_crawl=None,
            rows_in_db=None,
            container_info="api",
            type="analytics",
            allowed_actions=(),
        ),
    ]


def test_ops_contract_requires_auth() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/contract",
            headers={"Origin": "https://app.example.com"},
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "auth_required"
    assert exc.value.status == 401


def test_ops_contract_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.list_snapshots", lambda _client: _snapshot_rows()
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/contract",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["primary_league"] == "Mirage"
    assert "/api/v1/ops/services" == body["routes"]["ops_services"]
    assert body["visible_service_ids"] == ["market_harvester", "api"]
    assert body["controllable_service_ids"] == ["market_harvester"]


def test_ops_services_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.list_snapshots", lambda _client: _snapshot_rows()
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/services",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert len(body["services"]) == 2
    assert body["services"][0]["allowedActions"] == ["start", "stop", "restart"]


def test_service_action_maps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    def _raise_not_found(_client, *, service_id: str, action: str):
        raise ServiceControlError("failed")

    monkeypatch.setattr(
        "poe_trade.api.app.execute_service_action",
        _raise_not_found,
    )

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/actions/services/market_harvester/restart",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 503
    assert exc.value.code == "service_action_failed"


def test_stash_route_is_explicitly_unavailable() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/stash/tabs?league=Mirage&realm=pc",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 503
    assert exc.value.code == "feature_unavailable"


def test_stash_route_returns_empty_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.fetch_stash_tabs",
        lambda _client, *, league, realm: {"stashTabs": []},
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )
    response = app.handle(
        method="GET",
        raw_path="/api/v1/stash/tabs?league=Mirage&realm=pc",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body == {"stashTabs": []}
