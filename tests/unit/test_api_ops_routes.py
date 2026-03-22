from __future__ import annotations

import json
import os
from io import BytesIO
from threading import Event
from unittest import mock

import pytest

from poe_trade.api.app import ApiApp
import poe_trade.api.app as api_app_module
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
    assert body["deployment"] == {
        "backendVersion": "0.1.0",
        "backendSha": None,
        "frontendBuildSha": None,
        "recommendationContractVersion": 3,
        "contractMatchState": "unknown",
    }


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
        raise ServiceControlError(f"docker compose {action} failed for {service_id}")

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
    assert exc.value.details == {
        "reason": "docker compose restart failed for market_harvester"
    }
    assert (
        exc.value.headers.get("Access-Control-Allow-Origin")
        == "https://app.example.com"
    )


def test_service_action_forbidden_preserves_cors_headers() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/actions/services/api/stop",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )

    assert exc.value.status == 403
    assert exc.value.code == "service_action_forbidden"
    assert (
        exc.value.headers.get("Access-Control-Allow-Origin")
        == "https://app.example.com"
    )


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


def test_stash_status_reports_feature_flag_when_disabled() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/stash/status?league=Mirage&realm=pc",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))

    assert response.status == 200
    assert body["status"] == "feature_unavailable"
    assert body["connected"] is False
    assert body["reason"] == "set POE_ENABLE_ACCOUNT_STASH=true to enable stash APIs"
    assert body["featureFlag"] == "POE_ENABLE_ACCOUNT_STASH"


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


def test_stash_scan_start_route_returns_async_scan_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(
        "poe_trade.api.app.start_private_stash_scan",
        lambda settings, clickhouse, *, account_name, league, realm: {
            "scanId": "scan-2",
            "status": "running",
            "startedAt": "2026-03-21T12:01:00Z",
            "accountName": account_name,
            "league": league,
            "realm": realm,
        },
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    response = app.handle(
        method="POST",
        raw_path="/api/v1/stash/scan?league=Mirage&realm=pc",
        headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
        body_reader=BytesIO(b""),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 202
    assert body["scanId"] == "scan-2"
    assert body["accountName"] == "qa-exile"


def test_stash_scan_start_route_rejects_invalid_poe_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(
        "poe_trade.api.app.load_credential_state",
        lambda _settings: {
            "account_name": "qa-exile",
            "poe_session_id": "POESESSID-123",
        },
    )
    monkeypatch.setattr(
        "poe_trade.stash_scan.fetch_active_scan", lambda *_args, **_kwargs: None
    )

    def _raise_invalid(_settings, *, poe_session_id):
        raise api_app_module.AccountResolutionError(
            "invalid POESESSID or account profile unavailable",
            code="invalid_poe_session",
            status=400,
        )

    monkeypatch.setattr("poe_trade.api.app.resolve_account_name", _raise_invalid)
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/stash/scan?league=Mirage&realm=pc",
            headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
            body_reader=BytesIO(b""),
        )

    assert exc.value.status == 400
    assert exc.value.code == "invalid_poe_session"


def test_stash_scan_status_route_returns_progress_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_status_payload",
        lambda _client, *, account_name, league, realm: {
            "status": "running",
            "activeScanId": "scan-2",
            "publishedScanId": "scan-1",
            "startedAt": "2026-03-21T12:01:00Z",
            "updatedAt": "2026-03-21T12:02:00Z",
            "publishedAt": None,
            "progress": {
                "tabsTotal": 8,
                "tabsProcessed": 3,
                "itemsTotal": 120,
                "itemsProcessed": 44,
            },
            "error": None,
        },
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    response = app.handle(
        method="GET",
        raw_path="/api/v1/stash/scan/status?league=Mirage&realm=pc",
        headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
        body_reader=BytesIO(b""),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["activeScanId"] == "scan-2"
    assert body["progress"]["tabsProcessed"] == 3


def test_stash_item_history_route_returns_popup_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
    monkeypatch.setattr(
        "poe_trade.api.app.fetch_stash_item_history",
        lambda _client, *, account_name, league, realm, fingerprint, limit=20: {
            "fingerprint": fingerprint,
            "item": {
                "name": "Grim Bane",
                "itemClass": "Helmet",
                "rarity": "rare",
                "iconUrl": "https://web.poecdn.com/item.png",
            },
            "history": [
                {
                    "scanId": "scan-2",
                    "pricedAt": "2026-03-21T12:00:00Z",
                    "predictedValue": 45.0,
                    "confidence": 82.0,
                    "interval": {"p10": 39.0, "p90": 51.0},
                }
            ],
        },
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    response = app.handle(
        method="GET",
        raw_path="/api/v1/stash/items/sig%3Aitem-1/history?league=Mirage&realm=pc",
        headers={**_auth_headers(), "Cookie": "poe_session=test-session"},
        body_reader=BytesIO(b""),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["item"]["name"] == "Grim Bane"
    assert body["history"][0]["interval"] == {"p10": 39.0, "p90": 51.0}


def test_start_private_stash_scan_deduplicates_pending_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = Event()
    release = Event()
    runs: list[tuple[str | None, str | None]] = []

    monkeypatch.setattr(
        api_app_module,
        "load_credential_state",
        lambda _settings: {
            "account_name": "qa-exile",
            "poe_session_id": "POESESSID-123",
        },
    )
    monkeypatch.setattr(
        "poe_trade.stash_scan.fetch_active_scan", lambda *_args, **_kwargs: None
    )

    class _DummyPoeClient:
        def __init__(self, *_args, **_kwargs):
            return None

    class _DummyStatusReporter:
        def __init__(self, *_args, **_kwargs):
            return None

    class _DummyHarvester:
        def __init__(self, *_args, **_kwargs):
            return None

        def run_private_scan(self, **kwargs):
            runs.append((kwargs.get("scan_id"), kwargs.get("started_at")))
            started.set()
            release.wait(timeout=5)
            return {"scanId": kwargs.get("scan_id"), "status": "published"}

    monkeypatch.setattr(api_app_module, "PoeClient", _DummyPoeClient)
    monkeypatch.setattr(api_app_module, "StatusReporter", _DummyStatusReporter)
    monkeypatch.setattr(api_app_module, "AccountStashHarvester", _DummyHarvester)
    monkeypatch.setattr(
        api_app_module,
        "resolve_account_name",
        lambda _settings, *, poe_session_id: "qa-exile",
    )

    settings = _settings_with_stash_enabled()
    clickhouse = ClickHouseClient(endpoint="http://ch")
    first = api_app_module.start_private_stash_scan(
        settings,
        clickhouse,
        account_name="qa-exile",
        league="Mirage",
        realm="pc",
    )
    assert started.wait(timeout=5)
    second = api_app_module.start_private_stash_scan(
        settings,
        clickhouse,
        account_name="qa-exile",
        league="Mirage",
        realm="pc",
    )
    release.set()

    assert first["scanId"] == second["scanId"]
    assert second["status"] == "running"
    assert second["deduplicated"] is True
    assert len(runs) == 1


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
            "&cursor=scan-cursor"
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
        "cursor": "scan-cursor",
    }


def test_scanner_recommendations_route_invalid_cursor_maps_to_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _payload(_client, **kwargs):
        assert kwargs.get("cursor") == "bad-cursor"
        raise ValueError("invalid cursor")

    monkeypatch.setattr(
        "poe_trade.api.app.scanner_recommendations_payload",
        _payload,
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/scanner/recommendations?cursor=bad-cursor",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )

    assert exc.value.status == 400
    assert exc.value.code == "invalid_input"


def test_scanner_recommendations_route_forwards_operation_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _payload(_client, **kwargs):
        captured.update(kwargs)
        return {"recommendations": [], "meta": {"source": "scanner_recommendations"}}

    monkeypatch.setattr("poe_trade.api.app.scanner_recommendations_payload", _payload)
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path=(
            "/api/v1/ops/scanner/recommendations"
            "?sort=expected_profit_per_operation_chaos"
        ),
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )

    assert response.status == 200
    assert captured["sort_by"] == "expected_profit_per_operation_chaos"


def test_scanner_recommendations_route_defaults_to_operation_aware_sort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _payload(_client, **kwargs):
        captured.update(kwargs)
        return {"recommendations": [], "meta": {"source": "scanner_recommendations"}}

    monkeypatch.setattr("poe_trade.api.app.scanner_recommendations_payload", _payload)
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/scanner/recommendations",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )

    assert response.status == 200
    assert captured["sort_by"] == "expected_profit_per_operation_chaos"


def test_ops_analytics_opportunities_route_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.analytics_opportunities",
        lambda _client: {
            "distributions": {
                "opportunityType": [{"opportunity_type": "bulk_flip", "count": 1}],
                "complexityTier": [{"complexity_tier": "medium", "count": 1}],
            },
            "decisionLog": {
                "rejections": [
                    {"decision_reason": "rejected_min_confidence", "count": 1}
                ],
                "suppressions": [],
            },
            "topOpportunities": [{"scannerRunId": "scan-1"}],
        },
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="GET",
        raw_path="/api/v1/ops/analytics/opportunities",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["topOpportunities"][0]["scannerRunId"] == "scan-1"
    assert (
        body["decisionLog"]["rejections"][0]["decision_reason"]
        == "rejected_min_confidence"
    )


def test_ops_analytics_search_history_route_rejects_invalid_filters() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/analytics/search-history?price_min=abc&time_from=bad",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )

    assert exc.value.status == 400
    assert exc.value.code == "invalid_input"


def test_ops_analytics_pricing_outliers_route_rejects_invalid_limit() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/analytics/pricing-outliers?limit=oops",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )

    assert exc.value.status == 400
    assert exc.value.code == "invalid_input"


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
