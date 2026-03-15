from __future__ import annotations

import json
import os
from io import BytesIO
from unittest import mock

import pytest

from poe_trade.api.app import ApiApp
from poe_trade.api.ml import BackendUnavailable
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
    assert "opportunities" in body["tabs"]


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
    captured: dict[str, str] = {}

    monkeypatch.setattr(
        "poe_trade.api.app.fetch_stash_tabs",
        lambda _client, *, league, realm, account_name: (
            captured.update(
                {"league": league, "realm": realm, "account_name": account_name}
            )
            or {"stashTabs": []}
        ),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: (
            {
                "session_id": session_id,
                "status": "connected",
                "account_name": "qa-exile",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            if session_id
            else None
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )
    response = app.handle(
        method="GET",
        raw_path="/api/v1/stash/tabs?league=Mirage&realm=pc",
        headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body == {"stashTabs": []}
    assert captured == {
        "league": "Mirage",
        "realm": "pc",
        "account_name": "qa-exile",
    }


def test_stash_route_returns_scoped_rows_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.fetch_stash_tabs",
        lambda _client, *, league, realm, account_name: {
            "stashTabs": [
                {
                    "id": "1",
                    "name": f"{league}:{realm}:{account_name}",
                    "type": "normal",
                    "items": [],
                }
            ]
        },
    )
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: (
            {
                "session_id": session_id,
                "status": "connected",
                "account_name": "qa-exile",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            if session_id
            else None
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )
    response = app.handle(
        method="GET",
        raw_path="/api/v1/stash/tabs?league=Mirage&realm=pc",
        headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["stashTabs"][0]["name"] == "Mirage:pc:qa-exile"


def test_stash_route_requires_connected_session_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: (
            {
                "session_id": session_id,
                "status": "disconnected",
                "account_name": "qa-exile",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            if session_id
            else None
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/stash/tabs?league=Mirage&realm=pc",
            headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 401
    assert exc.value.code == "auth_required"


def test_stash_route_rejects_expired_session_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: (
            {
                "session_id": session_id,
                "status": "session_expired",
                "account_name": "qa-exile",
                "expires_at": "2099-01-01T00:00:00Z",
            }
            if session_id
            else None
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/stash/tabs?league=Mirage&realm=pc",
            headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 401
    assert exc.value.code == "session_expired"


def test_scanner_summary_route_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.scanner_summary_payload",
        lambda _client: {"status": "ok", "lastRunAt": None, "recommendationCount": 0},
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/scanner/summary",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["status"] == "ok"


def test_scanner_recommendations_route_rejects_unknown_sort() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/scanner/recommendations?sort=not_a_field",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 400
    assert exc.value.code == "invalid_input"


def test_scanner_recommendations_route_forwards_sort_and_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _payload(_client, **kwargs):
        captured.update(kwargs)
        return {
            "recommendations": [],
            "meta": {
                "source": "scanner_recommendations",
                "primaryLeague": "Mirage",
                "generatedAt": "2026-03-14T00:00:00Z",
            },
        }

    monkeypatch.setattr("poe_trade.api.app.scanner_recommendations_payload", _payload)
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path=(
            "/api/v1/ops/scanner/recommendations?sort=expected_profit_chaos"
            "&min_confidence=0.65&league=Mirage&strategy_id=bulk_essence&limit=25"
        ),
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["recommendations"] == []
    assert captured == {
        "limit": 25,
        "sort_by": "expected_profit_chaos",
        "min_confidence": 0.65,
        "league": "Mirage",
        "strategy_id": "bulk_essence",
    }


def test_ack_alert_route_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.ack_alert_payload",
        lambda _client, *, alert_id: {"alertId": alert_id, "status": "acked"},
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="POST",
        raw_path="/api/v1/ops/alerts/alert-1/ack",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body == {"alertId": "alert-1", "status": "acked"}


def test_ops_analytics_ml_keeps_hold_no_model_states_healthy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.analytics_ml",
        lambda _client, *, league: {
            "status": {
                "league": league,
                "status": "failed_gates",
                "promotion_verdict": "hold",
                "stop_reason": "hold_no_material_improvement",
                "active_model_version": None,
            }
        },
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/analytics/ml",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["status"]["status"] == "failed_gates"
    assert body["status"]["promotion_verdict"] == "hold"
    assert body["status"]["active_model_version"] is None


def test_ops_analytics_ml_backend_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_client, *, league: str):
        raise BackendUnavailable("status backend unavailable")

    monkeypatch.setattr("poe_trade.api.app.analytics_ml", _raise)
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    with pytest.raises(ApiError, match="backend unavailable") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/analytics/ml",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )

    assert exc.value.status == 503
    assert exc.value.code == "backend_unavailable"
