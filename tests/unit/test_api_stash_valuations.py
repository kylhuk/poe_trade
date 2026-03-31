from __future__ import annotations

import json
import os
from io import BytesIO
from urllib.parse import urlencode
from unittest import mock

import pytest

from poe_trade.api.app import ApiApp
from poe_trade.api.responses import ApiError
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


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


def _connected_session(session_id: str) -> dict[str, str]:
    return {
        "session_id": session_id,
        "status": "connected",
        "account_name": "qa-exile",
        "expires_at": "2099-01-01T00:00:00Z",
    }


def _request_body(**overrides: object) -> bytes:
    body: dict[str, object] = {
        "scanId": "scan-1",
        "itemId": "item-1",
        "structuredMode": False,
        "minThreshold": 10,
        "maxThreshold": 50,
        "maxAgeDays": 30,
    }
    for key, value in overrides.items():
        body[key] = value
    return json.dumps(body).encode("utf-8")


def _request_headers(body: bytes) -> dict[str, str]:
    return {
        **_auth_headers(),
        "Cookie": "poe_session=test-session",
        "Content-Length": str(len(body)),
    }


def _query_path(path: str, **params: object) -> str:
    query = urlencode(
        {key: value for key, value in params.items() if value is not None}
    )
    return f"{path}?{query}" if query else path


def test_stash_scan_valuations_route_returns_single_item_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_valuations_payload",
        lambda _client, **kwargs: (
            captured.update(kwargs)
            or {
                "structuredMode": False,
                "stashId": "scan-1",
                "itemId": "item-1",
                "scanDatetime": "2026-03-21T12:00:00Z",
                "chaosMedian": 42.0,
                "daySeries": [
                    {"date": "2026-03-12", "chaosMedian": None},
                    {"date": "2026-03-13", "chaosMedian": 42.0},
                ],
                "items": [
                    {
                        "stashId": "scan-1",
                        "itemId": "item-1",
                        "scanDatetime": "2026-03-21T12:00:00Z",
                        "chaosMedian": 42.0,
                        "daySeries": [
                            {"date": "2026-03-12", "chaosMedian": None},
                            {"date": "2026-03-13", "chaosMedian": 42.0},
                        ],
                    }
                ],
            }
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    body = _request_body()
    response = app.handle(
        method="POST",
        raw_path="/api/v1/stash/scan/valuations?league=Mirage&realm=pc",
        headers=_request_headers(body),
        body_reader=BytesIO(body),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["structuredMode"] is False
    assert body["items"][0]["itemId"] == "item-1"
    assert captured == {
        "account_name": "qa-exile",
        "league": "Mirage",
        "realm": "pc",
        "scan_id": "scan-1",
        "item_id": "item-1",
        "structured_mode": False,
        "min_threshold": 10.0,
        "max_threshold": 50.0,
        "max_age_days": 30,
    }


def test_stash_scan_valuations_route_accepts_stash_id_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_valuations_payload",
        lambda _client, **kwargs: (
            captured.update(kwargs)
            or {
                "structuredMode": False,
                "scanId": "scan-1",
                "stashId": "scan-1",
                "itemId": "item-1",
                "scanDatetime": "2026-03-21T12:00:00Z",
                "chaosMedian": 42.0,
                "daySeries": [],
                "items": [],
            }
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    body = json.dumps(
        {
            "stashId": "scan-1",
            "itemId": "item-1",
            "structuredMode": False,
            "minThreshold": 10,
            "maxThreshold": 50,
            "maxAgeDays": 30,
        }
    ).encode("utf-8")
    response = app.handle(
        method="POST",
        raw_path="/api/v1/stash/scan/valuations?league=Mirage&realm=pc",
        headers=_request_headers(body),
        body_reader=BytesIO(body),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["scanId"] == "scan-1"
    assert body["stashId"] == "scan-1"
    assert captured["scan_id"] == "scan-1"


@pytest.mark.parametrize(
    "raw_path",
    [
        _query_path(
            "/api/v1/stash/scan/valuations/status",
            league="Mirage",
            realm="pc",
            scanId="scan-1",
            structuredMode="true",
            minThreshold="10",
            maxThreshold="50",
            maxAgeDays="30",
        ),
        _query_path(
            "/api/v1/stash/scan/valuations/result",
            league="Mirage",
            realm="pc",
            scanId="scan-1",
            structuredMode="true",
            minThreshold="10",
            maxThreshold="50",
            maxAgeDays="30",
        ),
    ],
)
def test_stash_scan_valuations_canonical_get_routes_use_query_parameters(
    monkeypatch: pytest.MonkeyPatch,
    raw_path: str,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_valuations_payload",
        lambda _client, **kwargs: (
            captured.update(kwargs)
            or {
                "structuredMode": True,
                "scanId": "scan-1",
                "stashId": "scan-1",
                "itemId": None,
                "scanDatetime": None,
                "chaosMedian": None,
                "daySeries": [],
                "items": [],
            }
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    response = app.handle(
        method="GET",
        raw_path=raw_path,
        headers={
            "Origin": "https://app.example.com",
            "Cookie": "poe_session=test-session",
        },
        body_reader=BytesIO(b""),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["structuredMode"] is True
    assert captured == {
        "account_name": "qa-exile",
        "league": "Mirage",
        "realm": "pc",
        "scan_id": "scan-1",
        "item_id": None,
        "structured_mode": True,
        "min_threshold": 10.0,
        "max_threshold": 50.0,
        "max_age_days": 30,
    }


def test_stash_scan_valuations_start_route_returns_202_with_same_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_valuations_payload",
        lambda _client, **kwargs: (
            captured.update(kwargs)
            or {
                "structuredMode": True,
                "scanId": "scan-1",
                "stashId": "scan-1",
                "itemId": None,
                "scanDatetime": None,
                "chaosMedian": None,
                "daySeries": [],
                "items": [],
            }
        ),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    body = _request_body(structuredMode=True, itemId="")
    response = app.handle(
        method="POST",
        raw_path="/api/v1/stash/scan/valuations/start",
        headers=_request_headers(body),
        body_reader=BytesIO(body),
    )

    assert response.status == 202
    assert json.loads(response.body.decode("utf-8"))["scanId"] == "scan-1"
    assert captured["scan_id"] == "scan-1"
    assert captured["structured_mode"] is True


def test_stash_scan_valuations_route_returns_structured_batch_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_valuations_payload",
        lambda _client, **kwargs: {
            "structuredMode": True,
            "stashId": "scan-1",
            "itemId": None,
            "scanDatetime": None,
            "chaosMedian": None,
            "daySeries": [],
            "items": [
                {
                    "stashId": "scan-1",
                    "itemId": "item-1",
                    "scanDatetime": "2026-03-21T12:00:00Z",
                    "chaosMedian": 42.0,
                    "daySeries": [],
                },
                {
                    "stashId": "scan-1",
                    "itemId": "item-2",
                    "scanDatetime": "2026-03-21T12:00:00Z",
                    "chaosMedian": 55.0,
                    "daySeries": [],
                },
            ],
        },
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    body = _request_body(structuredMode=True, itemId="")
    response = app.handle(
        method="POST",
        raw_path="/api/v1/stash/scan/valuations?league=Mirage&realm=pc",
        headers=_request_headers(body),
        body_reader=BytesIO(body),
    )

    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert body["structuredMode"] is True
    assert len(body["items"]) == 2


def test_stash_scan_valuations_route_rejects_unknown_item(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    monkeypatch.setattr(
        "poe_trade.api.app.stash_scan_valuations_payload",
        lambda _client, **_kwargs: (_ for _ in ()).throw(LookupError("item not found")),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    body = _request_body(itemId="missing-item")
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/stash/scan/valuations?league=Mirage&realm=pc",
            headers=_request_headers(body),
            body_reader=BytesIO(body),
        )

    assert exc.value.status == 404
    assert exc.value.code == "item_not_found"


@pytest.mark.parametrize(
    "body",
    [
        _request_body(maxAgeDays="bad"),
        _request_body(minThreshold="bad"),
        _request_body(maxThreshold="bad"),
    ],
)
def test_stash_scan_valuations_route_rejects_invalid_numeric_input(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: _connected_session(session_id),
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/stash/scan/valuations?league=Mirage&realm=pc",
            headers=_request_headers(body),
            body_reader=BytesIO(body),
        )

    assert exc.value.status == 400
    assert exc.value.code == "invalid_input"


@pytest.mark.parametrize(
    "session_status,expected_code",
    [("disconnected", "auth_required"), ("session_expired", "session_expired")],
)
def test_stash_scan_valuations_route_requires_connected_session(
    monkeypatch: pytest.MonkeyPatch,
    session_status: str,
    expected_code: str,
) -> None:
    monkeypatch.setattr(
        "poe_trade.api.app.get_session",
        lambda _settings, *, session_id: {
            "session_id": session_id,
            "status": session_status,
            "account_name": "qa-exile",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )
    app = ApiApp(
        _settings_with_stash_enabled(),
        clickhouse_client=ClickHouseClient(endpoint="http://ch"),
    )

    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/stash/scan/valuations?league=Mirage&realm=pc",
            headers=_request_headers(_request_body()),
            body_reader=BytesIO(_request_body()),
        )

    assert exc.value.status == 401
    assert exc.value.code == expected_code
