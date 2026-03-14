from __future__ import annotations

import os
from io import BytesIO
from unittest import mock

import pytest

from poe_trade.api.app import ApiApp
from poe_trade.api.responses import ApiError
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


def test_allowed_origin_receives_allow_origin_header() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ml/contract",
        headers={
            "Authorization": "Bearer phase1-token",
            "Origin": "https://app.example.com",
        },
        body_reader=BytesIO(b""),
    )
    assert response.status == 200
    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"


def test_denied_origin_fails_closed() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="origin is not allowed") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ml/contract",
            headers={
                "Authorization": "Bearer phase1-token",
                "Origin": "https://evil.example.com",
            },
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "origin_denied"
    assert exc.value.status == 403


def test_options_preflight_supports_allowed_origin() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="OPTIONS",
        raw_path="/api/v1/ml/leagues/Mirage/status",
        headers={"Origin": "https://app.example.com"},
        body_reader=BytesIO(b""),
    )
    assert response.status == 204
    assert response.headers["Access-Control-Allow-Origin"] == "https://app.example.com"


def test_ops_route_denied_origin_fails_closed() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="origin is not allowed") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/services",
            headers={
                "Authorization": "Bearer phase1-token",
                "Origin": "https://evil.example.com",
            },
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "origin_denied"
    assert exc.value.status == 403
