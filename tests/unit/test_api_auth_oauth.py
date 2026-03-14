from __future__ import annotations

import os
from io import BytesIO
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest

from poe_trade.api.app import ApiApp
from poe_trade.api.auth_session import authorize_redirect, begin_login
from poe_trade.api.responses import ApiError
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


def test_authorize_redirect_urlencodes_redirect_uri() -> None:
    env = {
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_ACCOUNT_REDIRECT_URI": "https://api.example.com/api/v1/auth/callback?foo=bar&baz=qux",
        "POE_ACCOUNT_OAUTH_SCOPE": "account:profile account:stashes",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    tx = begin_login(settings)
    location = authorize_redirect(settings, tx)
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    assert query["redirect_uri"][0] == env["POE_ACCOUNT_REDIRECT_URI"]


def test_auth_login_requires_redirect_uri_when_oauth_client_configured() -> None:
    env = {
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_OAUTH_CLIENT_ID": "client-id",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    app = ApiApp(settings, clickhouse_client=ClickHouseClient(endpoint="http://ch"))
    with pytest.raises(ApiError, match="POE_ACCOUNT_REDIRECT_URI") as exc:
        _ = app.handle(
            method="GET",
            raw_path="/api/v1/auth/login",
            headers={},
            body_reader=BytesIO(b""),
        )
    assert exc.value.code == "oauth_config_invalid"
    assert exc.value.status == 500
