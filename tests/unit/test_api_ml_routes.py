from __future__ import annotations

import json
import os
from io import BytesIO
from unittest import mock

import pytest

from poe_trade.api import ml as api_ml
from poe_trade.api.app import ApiApp
from poe_trade.api.responses import ApiError
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError


def _settings() -> Settings:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_API_CORS_ORIGINS": "https://app.example.com",
        "POE_API_MAX_BODY_BYTES": "128",
        "POE_API_LEAGUE_ALLOWLIST": "Mirage",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        return Settings.from_env()


def _auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer phase1-token"}


def test_healthz_shape_and_no_auth_required() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/healthz",
        headers={},
        body_reader=BytesIO(b""),
    )
    assert response.status == 200
    body = json.loads(response.body.decode("utf-8"))
    assert body == {"status": "ok", "service": "api", "version": "v1"}


def test_contract_exact_top_level_keys() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ml/contract",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert set(body) == {
        "version",
        "auth_mode",
        "allowed_leagues",
        "routes",
        "non_goals",
    }


def test_unknown_route_uses_shared_error_code() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/does-not-exist",
            headers={},
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 404
    assert exc.value.code == "route_not_found"


def test_wrong_method_uses_shared_error_code() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError) as exc:
        app.handle(
            method="POST",
            raw_path="/healthz",
            headers={},
            body_reader=BytesIO(b""),
        )
    assert exc.value.status == 405
    assert exc.value.code == "method_not_allowed"


def test_ml_status_returns_stable_no_runs_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        api_ml.workflows,
        "status",
        lambda _client, league, run: {"league": league, "status": "no_runs"},
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    response = app.handle(
        method="GET",
        raw_path="/api/v1/ml/leagues/Mirage/status",
        headers=_auth_headers(),
        body_reader=BytesIO(b""),
    )
    body = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert set(body) == {
        "league",
        "run",
        "status",
        "promotion_verdict",
        "stop_reason",
        "active_model_version",
        "latest_avg_mdape",
        "latest_avg_interval_coverage",
        "candidate_vs_incumbent",
        "route_hotspots",
    }
    assert body["candidate_vs_incumbent"] == {}
    assert body["route_hotspots"] == []


def test_invalid_league_rejected() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="league is not allowed") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ml/leagues/Standard/status",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "league_not_allowed"
    assert exc.value.status == 400


def test_status_backend_failure_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(_client, league, run):
        raise ClickHouseClientError("db details should not leak")

    monkeypatch.setattr(api_ml.workflows, "status", _raise)
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="backend unavailable") as exc:
        app.handle(
            method="GET",
            raw_path="/api/v1/ml/leagues/Mirage/status",
            headers=_auth_headers(),
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "backend_unavailable"
    assert exc.value.status == 503


def test_predict_one_returns_stable_dto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_ml.workflows,
        "predict_one",
        lambda _client, league, clipboard_text: {
            "league": league,
            "route": "structured_boosted",
            "price_p10": 8.0,
            "price_p50": 10.0,
            "price_p90": 12.0,
            "confidence_percent": 62.0,
            "sale_probability_percent": 60.0,
            "price_recommendation_eligible": True,
            "fallback_reason": "",
            "internal_only": "ignore",
        },
    )
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    payload = {
        "input_format": "poe-clipboard",
        "payload": "item payload",
        "output_mode": "json",
    }
    body = json.dumps(payload).encode("utf-8")
    response = app.handle(
        method="POST",
        raw_path="/api/v1/ml/leagues/Mirage/predict-one",
        headers={**_auth_headers(), "Content-Length": str(len(body))},
        body_reader=BytesIO(body),
    )
    result = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert set(result) == {
        "league",
        "route",
        "price_p10",
        "price_p50",
        "price_p90",
        "confidence_percent",
        "sale_probability_percent",
        "price_recommendation_eligible",
        "fallback_reason",
    }


def test_predict_one_rejects_unsupported_input_format() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    payload = {"input_format": "unknown", "payload": "x", "output_mode": "json"}
    body = json.dumps(payload).encode("utf-8")
    with pytest.raises(ApiError, match="invalid input") as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/ml/leagues/Mirage/predict-one",
            headers={**_auth_headers(), "Content-Length": str(len(body))},
            body_reader=BytesIO(body),
        )
    assert exc.value.code == "invalid_input"
    assert exc.value.status == 400


def test_predict_one_rejects_malformed_json() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    body = b"{invalid"
    with pytest.raises(ApiError, match="valid JSON") as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/ml/leagues/Mirage/predict-one",
            headers={**_auth_headers(), "Content-Length": str(len(body))},
            body_reader=BytesIO(body),
        )
    assert exc.value.code == "invalid_json"
    assert exc.value.status == 400


def test_predict_one_rejects_oversized_request() -> None:
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    body = b"x" * 1024
    with pytest.raises(ApiError, match="exceeds limit") as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/ml/leagues/Mirage/predict-one",
            headers={**_auth_headers(), "Content-Length": str(len(body))},
            body_reader=BytesIO(body),
        )
    assert exc.value.code == "request_too_large"
    assert exc.value.status == 413


def test_predict_one_backend_failure_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_client, league, clipboard_text):
        raise ClickHouseClientError("sensitive backend detail")

    monkeypatch.setattr(api_ml.workflows, "predict_one", _raise)
    app = ApiApp(_settings(), clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    payload = {
        "input_format": "poe-clipboard",
        "payload": "item payload",
        "output_mode": "json",
    }
    body = json.dumps(payload).encode("utf-8")
    with pytest.raises(ApiError, match="backend unavailable") as exc:
        app.handle(
            method="POST",
            raw_path="/api/v1/ml/leagues/Mirage/predict-one",
            headers={**_auth_headers(), "Content-Length": str(len(body))},
            body_reader=BytesIO(body),
        )
    assert exc.value.status == 503
    assert exc.value.code == "backend_unavailable"
