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


def test_ml_routes_require_bearer_token() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="bearer token required") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ml/contract",
            headers={"Origin": "https://app.example.com"},
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "auth_required"
    assert exc.value.status == 401
    assert (
        exc.value.headers.get("Access-Control-Allow-Origin")
        == "https://app.example.com"
    )


def test_ml_routes_reject_invalid_bearer_token() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="invalid bearer token") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ml/contract",
            headers={
                "Authorization": "Bearer wrong",
                "Origin": "https://app.example.com",
            },
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "auth_invalid"
    assert exc.value.status == 401
    assert (
        exc.value.headers.get("Access-Control-Allow-Origin")
        == "https://app.example.com"
    )


def test_ml_routes_accept_valid_bearer_token() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ml/contract",
        headers={"Authorization": "Bearer phase1-token"},
        body_reader=BytesIO(b""),
    )
    assert response.status == 200


def test_ops_routes_require_bearer_token() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="bearer token required") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ops/services",
            headers={"Origin": "https://app.example.com"},
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "auth_required"
    assert exc.value.status == 401
