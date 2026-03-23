from __future__ import annotations

import json
import os
from io import BytesIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest

from poe_trade.api.app import ApiApp
from poe_trade.api.auth_session import (
    OAuthExchangeError,
    OAuthExchangeResult,
    authorize_redirect,
    begin_login,
    create_session,
    get_session,
)
from poe_trade.api.responses import ApiError
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


def test_authorize_redirect_urlencodes_redirect_uri(tmp_path) -> None:
    env = {
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback?foo=bar&baz=qux",
        "POE_ACCOUNT_OAUTH_SCOPE": "account:profile account:stashes",
        "POE_AUTH_STATE_DIR": str(tmp_path / "auth-state"),
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    tx = begin_login(settings)
    location = authorize_redirect(settings, tx)
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query["redirect_uri"][0] == env["POE_ACCOUNT_REDIRECT_URI"]


def test_auth_login_returns_authorize_url_json() -> None:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback",
        "POE_ACCOUNT_OAUTH_AUTHORIZE_URL": "https://auth.example.com/oauth/authorize",
        "POE_ACCOUNT_OAUTH_SCOPE": "account:profile account:stashes",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    app = ApiApp(settings, clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    response = app.handle(
        method="POST",
        raw_path="/api/v1/auth/login",
        headers={"Origin": "https://app.example.com"},
        body_reader=BytesIO(b""),
    )

    payload = json.loads(response.body.decode("utf-8"))
    parsed = urlparse(payload["authorizeUrl"])
    query = parse_qs(parsed.query)

    assert response.status == 200
    assert set(payload) == {"authorizeUrl"}
    assert parsed.scheme == "https"
    assert parsed.netloc == "auth.example.com"
    assert parsed.path == "/oauth/authorize"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == [env["POE_ACCOUNT_REDIRECT_URI"]]
    assert query["scope"] == [env["POE_ACCOUNT_OAUTH_SCOPE"]]
    assert query["code_challenge_method"] == ["S256"]
    assert query["state"][0]
    assert query["code_challenge"][0]


def test_auth_callback_exchanges_code_and_sets_session_cookie(tmp_path) -> None:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback",
        "POE_AUTH_STATE_DIR": str(tmp_path / "auth-state"),
        "POE_AUTH_COOKIE_SECURE": "true",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    app = ApiApp(settings, clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    login_response = app.handle(
        method="POST",
        raw_path="/api/v1/auth/login",
        headers={"Origin": "https://app.example.com"},
        body_reader=BytesIO(b""),
    )
    login_payload = json.loads(login_response.body.decode("utf-8"))
    state = parse_qs(urlparse(login_payload["authorizeUrl"]).query)["state"][0]
    callback_body = json.dumps({"code": "code-123", "state": state}).encode("utf-8")

    exchange = OAuthExchangeResult(
        account_name="qa-exile",
        access_token="access-token",
        refresh_token="refresh-token",
        token_type="bearer",
        expires_in=3600,
        scope="account:profile account:stashes",
    )
    with mock.patch(
        "poe_trade.api.app.exchange_oauth_code", return_value=exchange
    ) as mocked_exchange:
        with mock.patch(
            "poe_trade.api.app.create_session",
            return_value={
                "session_id": "session-123",
                "account_name": "qa-exile",
                "expires_at": "2026-01-01T00:00:00Z",
                "scope": ["account:profile", "account:stashes"],
            },
        ) as mocked_session:
            response = app.handle(
                method="POST",
                raw_path="/api/v1/auth/callback",
                headers={
                    "Origin": "https://app.example.com",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(callback_body)),
                },
                body_reader=BytesIO(callback_body),
            )

    payload = json.loads(response.body.decode("utf-8"))

    assert response.status == 200
    assert payload["status"] == "connected"
    assert payload["accountName"] == "qa-exile"
    assert "Set-Cookie" in response.headers
    assert "poe_session=session-123" in response.headers["Set-Cookie"]
    assert "Secure" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]
    assert "SameSite=Lax" in response.headers["Set-Cookie"]
    assert "Path=/" in response.headers["Set-Cookie"]
    mocked_exchange.assert_called_once_with(settings, code="code-123", state=state)
    mocked_session.assert_called_once_with(settings, account_name="qa-exile")


def test_auth_callback_rotates_existing_session_cookie(tmp_path) -> None:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback",
        "POE_AUTH_STATE_DIR": str(tmp_path / "auth-state"),
        "POE_AUTH_COOKIE_SECURE": "true",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    app = ApiApp(settings, clickhouse_client=ClickHouseClient(endpoint="http://ch"))

    existing_session = create_session(settings, account_name="qa-exile")
    login_response = app.handle(
        method="POST",
        raw_path="/api/v1/auth/login",
        headers={"Origin": "https://app.example.com"},
        body_reader=BytesIO(b""),
    )
    login_payload = json.loads(login_response.body.decode("utf-8"))
    state = parse_qs(urlparse(login_payload["authorizeUrl"]).query)["state"][0]
    callback_body = json.dumps({"code": "code-123", "state": state}).encode("utf-8")

    exchange = OAuthExchangeResult(
        account_name="qa-exile",
        access_token="access-token",
        refresh_token="refresh-token",
        token_type="bearer",
        expires_in=3600,
        scope="account:profile account:stashes",
    )
    with mock.patch("poe_trade.api.app.exchange_oauth_code", return_value=exchange):
        response = app.handle(
            method="POST",
            raw_path="/api/v1/auth/callback",
            headers={
                "Origin": "https://app.example.com",
                "Cookie": f"poe_session={existing_session['session_id']}",
                "Content-Type": "application/json",
                "Content-Length": str(len(callback_body)),
            },
            body_reader=BytesIO(callback_body),
        )

    payload = json.loads(response.body.decode("utf-8"))
    new_cookie = response.headers["Set-Cookie"]
    new_session_id = new_cookie.split(";", maxsplit=1)[0].split("=", maxsplit=1)[1]

    assert response.status == 200
    assert payload["status"] == "connected"
    assert new_session_id != existing_session["session_id"]
    assert get_session(settings, session_id=existing_session["session_id"]) is None
    assert (
        get_session(settings, session_id=new_session_id)["account_name"] == "qa-exile"
    )
    assert "Secure" in new_cookie
    assert "HttpOnly" in new_cookie
    assert "SameSite=Lax" in new_cookie
    assert "Path=/" in new_cookie


@pytest.mark.parametrize(
    ("error", "description", "code", "status"),
    [
        ("access_denied", "user cancelled", "oauth_access_denied", 401),
        ("invalid_request", "bad request", "oauth_callback_failed", 400),
    ],
)
def test_auth_callback_maps_provider_errors_without_creating_session(
    error: str,
    description: str,
    code: str,
    status: int,
    tmp_path,
) -> None:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback",
        "POE_AUTH_STATE_DIR": str(tmp_path / "auth-state"),
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    app = ApiApp(settings, clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    payload = json.dumps({"error": error, "error_description": description}).encode(
        "utf-8"
    )

    with mock.patch("poe_trade.api.app.create_session") as mocked_session:
        with pytest.raises(ApiError, match=description) as exc:
            _ = app.handle(
                method="POST",
                raw_path="/api/v1/auth/callback",
                headers={
                    "Origin": "https://app.example.com",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(payload)),
                },
                body_reader=BytesIO(payload),
            )

    assert exc.value.code == code
    assert exc.value.status == status
    mocked_session.assert_not_called()


@pytest.mark.parametrize(
    ("raised", "code", "status"),
    [
        (
            OAuthExchangeError("invalid state", code="invalid_state", status=400),
            "invalid_state",
            400,
        ),
        (
            OAuthExchangeError(
                "missing code verifier", code="missing_code_verifier", status=400
            ),
            "missing_code_verifier",
            400,
        ),
        (
            OAuthExchangeError(
                "token endpoint unavailable", code="oauth_exchange_failed", status=502
            ),
            "oauth_exchange_failed",
            502,
        ),
    ],
)
def test_auth_callback_surfaces_exchange_errors_without_creating_session(
    raised: OAuthExchangeError,
    code: str,
    status: int,
    tmp_path,
) -> None:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback",
        "POE_AUTH_STATE_DIR": str(tmp_path / "auth-state"),
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    app = ApiApp(settings, clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    payload = json.dumps({"code": "code-123", "state": "state-123"}).encode("utf-8")

    with mock.patch("poe_trade.api.app.exchange_oauth_code", side_effect=raised):
        with mock.patch("poe_trade.api.app.create_session") as mocked_session:
            with pytest.raises(ApiError) as exc:
                _ = app.handle(
                    method="POST",
                    raw_path="/api/v1/auth/callback",
                    headers={
                        "Origin": "https://app.example.com",
                        "Content-Type": "application/json",
                        "Content-Length": str(len(payload)),
                    },
                    body_reader=BytesIO(payload),
                )

    assert exc.value.code == code
    assert exc.value.status == status
    mocked_session.assert_not_called()
