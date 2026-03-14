from __future__ import annotations

import os
from unittest import mock

import pytest

from poe_trade.api.app import create_app
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient


def test_api_settings_defaults() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = Settings.from_env()
    assert cfg.api_bind_host == "127.0.0.1"
    assert cfg.api_bind_port == 8080
    assert cfg.api_operator_token == ""
    assert cfg.api_cors_origins == ()
    assert cfg.api_max_body_bytes == 32768
    assert cfg.api_league_allowlist == ("Mirage",)
    assert cfg.enable_account_stash is False
    assert cfg.account_stash_access_token == ""
    assert cfg.account_stash_realm == "pc"
    assert cfg.account_stash_league == "Mirage"
    assert cfg.account_stash_poll_interval == 300.0


def test_api_settings_parse_values() -> None:
    env = {
        "POE_API_BIND_HOST": "0.0.0.0",
        "POE_API_BIND_PORT": "9090",
        "POE_API_OPERATOR_TOKEN": "phase1-token",
        "POE_API_CORS_ORIGINS": " https://app.example.com,https://ops.example.com ",
        "POE_API_MAX_BODY_BYTES": "16384",
        "POE_API_LEAGUE_ALLOWLIST": "Mirage, Keepers ",
        "POE_ENABLE_ACCOUNT_STASH": "true",
        "POE_ACCOUNT_STASH_ACCESS_TOKEN": "stash-token",
        "POE_ACCOUNT_STASH_REALM": "xbox",
        "POE_ACCOUNT_STASH_LEAGUE": "Settlers",
        "POE_ACCOUNT_STASH_POLL_INTERVAL": "120",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        cfg = Settings.from_env()
    assert cfg.api_bind_host == "0.0.0.0"
    assert cfg.api_bind_port == 9090
    assert cfg.api_operator_token == "phase1-token"
    assert cfg.api_cors_origins == (
        "https://app.example.com",
        "https://ops.example.com",
    )
    assert cfg.api_max_body_bytes == 16384
    assert cfg.api_league_allowlist == ("Mirage", "Keepers")
    assert cfg.enable_account_stash is True
    assert cfg.account_stash_access_token == "stash-token"
    assert cfg.account_stash_realm == "xbox"
    assert cfg.account_stash_league == "Settlers"
    assert cfg.account_stash_poll_interval == 120.0


def test_missing_token_fails_closed() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        cfg = Settings.from_env()
    with pytest.raises(ValueError, match="POE_API_OPERATOR_TOKEN"):
        create_app(cfg, clickhouse_client=ClickHouseClient(endpoint="http://ch"))
