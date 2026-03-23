from __future__ import annotations

import os
import json
import threading
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from poe_trade.api.auth_session import (
    _account_name_html_urls,
    _load_json,
    _transactions_path,
    begin_login,
    clear_credential_state,
    credential_state_path,
    consume_login_state,
    load_credential_state,
    load_oauth_credential_state,
    prune_login_transactions,
    resolve_account_name,
    refresh_oauth_access_token,
    save_oauth_credential_state,
    save_credential_state,
    OAuthExchangeError,
)
from poe_trade.config.settings import Settings


def _settings(state_dir: str) -> Settings:
    with mock.patch.dict(os.environ, {"POE_AUTH_STATE_DIR": state_dir}, clear=True):
        return Settings.from_env()


def _oauth_settings(state_dir: str) -> Settings:
    env = {
        "POE_AUTH_STATE_DIR": state_dir,
        "POE_OAUTH_CLIENT_ID": "client-id",
        "POE_OAUTH_CLIENT_SECRET": "client-secret",
        "POE_ACCOUNT_OAUTH_TOKEN_URL": "https://auth.example.com/oauth/token",
        "POE_ACCOUNT_OAUTH_SCOPE": "account:profile account:stashes",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        return Settings.from_env()


def test_credential_state_path_stable_under_auth_state_dir(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    path = credential_state_path(settings)

    assert path == tmp_path / "auth-state" / "credential-state.json"
    assert path.parent.exists()


def test_save_and_load_credential_state_round_trip(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    saved = save_credential_state(
        settings,
        account_name="qa-exile",
        cf_clearance="cf-clearance-123",
        status="token_present",
    )
    loaded = load_credential_state(settings)

    assert saved["account_name"] == "qa-exile"
    assert saved["status"] == "token_present"
    assert isinstance(saved["updated_at"], str)
    assert loaded == saved


def test_load_credential_state_defaults_when_file_is_missing(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    loaded = load_credential_state(settings)

    assert loaded["account_name"] == ""
    assert loaded["poe_session_id"] == ""
    assert loaded["cf_clearance"] == ""
    assert loaded["status"] == "unknown"
    assert isinstance(loaded["updated_at"], str)


def test_clear_credential_state_resets_sensitive_fields(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))
    _ = save_credential_state(
        settings,
        account_name="qa-exile",
        poe_session_id="POESESSID-123",
        cf_clearance="cf-clearance-123",
        status="bootstrap_connected",
    )

    cleared = clear_credential_state(settings)

    assert cleared["status"] == "logged_out"
    assert cleared["account_name"] == ""
    assert cleared["poe_session_id"] == ""
    assert cleared["cf_clearance"] == ""
    assert load_credential_state(settings) == cleared


def test_save_and_load_oauth_credential_state_round_trip(tmp_path: Path) -> None:
    settings = _oauth_settings(str(tmp_path / "auth-state"))

    saved = save_oauth_credential_state(
        settings,
        account_name="qa-exile",
        access_token="access-token-1",
        refresh_token="refresh-token-1",
        token_type="bearer",
        scope="account:profile account:stashes",
        expires_at="2026-03-23T12:00:00Z",
        status="connected",
    )
    loaded = load_oauth_credential_state(settings)

    assert saved["account_name"] == "qa-exile"
    assert saved["access_token"] == "access-token-1"
    assert saved["refresh_token"] == "refresh-token-1"
    assert saved["status"] == "connected"
    assert loaded == saved


def test_refresh_rotates_refresh_token_and_persists_atomically(tmp_path: Path) -> None:
    settings = _oauth_settings(str(tmp_path / "auth-state"))
    _ = save_oauth_credential_state(
        settings,
        account_name="qa-exile",
        access_token="access-token-1",
        refresh_token="refresh-token-1",
        token_type="bearer",
        scope="account:profile account:stashes",
        expires_at="2026-03-23T12:00:00Z",
        status="connected",
    )

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "access_token": "access-token-2",
                    "refresh_token": "refresh-token-2",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "scope": "account:profile account:stashes",
                }
            ).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=_Response()) as urlopen_mock:
        refreshed = refresh_oauth_access_token(settings)

    request = urlopen_mock.call_args[0][0]
    body = request.data.decode("utf-8")

    assert "grant_type=refresh_token" in body
    assert "refresh_token=refresh-token-1" in body
    assert "client_id=client-id" in body
    assert refreshed["access_token"] == "access-token-2"
    assert refreshed["refresh_token"] == "refresh-token-2"
    assert load_oauth_credential_state(settings)["refresh_token"] == "refresh-token-2"


def test_refresh_failure_marks_disconnected(tmp_path: Path) -> None:
    settings = _oauth_settings(str(tmp_path / "auth-state"))
    _ = save_oauth_credential_state(
        settings,
        account_name="qa-exile",
        access_token="access-token-1",
        refresh_token="refresh-token-1",
        token_type="bearer",
        scope="account:profile account:stashes",
        expires_at="2026-03-23T12:00:00Z",
        status="connected",
    )

    class _HTTPError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__(
                url="https://auth.example.com/oauth/token",
                code=401,
                msg="unauthorized",
                hdrs=None,
                fp=None,
            )

        def read(self) -> bytes:
            return json.dumps(
                {
                    "error": "invalid_grant",
                    "error_description": "refresh token expired",
                }
            ).encode("utf-8")

    with mock.patch("urllib.request.urlopen", side_effect=_HTTPError()):
        with pytest.raises(OAuthExchangeError, match="refresh token expired"):
            refresh_oauth_access_token(settings)

    state = load_oauth_credential_state(settings)
    assert state["status"] == "disconnected"
    assert state["access_token"] == ""
    assert state["refresh_token"] == ""


def test_refresh_allows_single_inflight_request_with_waiters(tmp_path: Path) -> None:
    settings = _oauth_settings(str(tmp_path / "auth-state"))
    _ = save_oauth_credential_state(
        settings,
        account_name="qa-exile",
        access_token="access-token-1",
        refresh_token="refresh-token-1",
        token_type="bearer",
        scope="account:profile account:stashes",
        expires_at="2026-03-23T12:00:00Z",
        status="connected",
    )

    refresh_started = threading.Event()
    release_refresh = threading.Event()
    calls: list[str] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "access_token": "access-token-2",
                    "refresh_token": "refresh-token-2",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "scope": "account:profile account:stashes",
                }
            ).encode("utf-8")

    def _urlopen(request, timeout: float):
        calls.append(request.full_url)
        refresh_started.set()
        assert release_refresh.wait(1.0)
        return _Response()

    results: dict[str, dict[str, object]] = {}

    def _owner() -> None:
        results["owner"] = refresh_oauth_access_token(settings)

    def _waiter() -> None:
        assert refresh_started.wait(1.0)
        results["waiter"] = refresh_oauth_access_token(settings)

    with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
        owner = threading.Thread(target=_owner)
        waiter = threading.Thread(target=_waiter)
        owner.start()
        waiter.start()
        assert refresh_started.wait(1.0)
        release_refresh.set()
        owner.join(1.0)
        waiter.join(1.0)

    assert not owner.is_alive()
    assert not waiter.is_alive()
    assert len(calls) == 1
    assert results["owner"]["access_token"] == "access-token-2"
    assert results["waiter"]["access_token"] == "access-token-2"


def test_resolve_account_name_uses_poe_session_cookie(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"accountName": "qa-exile"}).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=_Response()) as urlopen_mock:
        account_name = resolve_account_name(settings, poe_session_id="POESESSID-123")

    request = urlopen_mock.call_args[0][0]
    assert account_name == "qa-exile"
    assert request.full_url in {
        "https://api.pathofexile.com/account/profile",
        "https://www.pathofexile.com/my-account",
        "https://www.pathofexile.com/account/profile",
    }
    assert request.get_method() == "GET"
    assert (
        request.get_header("Accept")
        == "application/json, text/html;q=0.9, text/plain;q=0.8"
    )
    assert request.get_header("Cookie") == "POESESSID=POESESSID-123"


def test_account_name_html_urls_use_non_oauth_profile_pages(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    urls = _account_name_html_urls(settings)

    assert urls == (
        "https://www.pathofexile.com/my-account",
        "https://www.pathofexile.com/account/profile",
    )


def test_resolve_account_name_uses_plain_text_fallback_after_404(
    tmp_path: Path,
) -> None:
    settings = _settings(str(tmp_path / "auth-state"))
    attempted_urls: list[str] = []

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'<a href="/account/view-profile/qa-exile">qa-exile</a>'

    def _urlopen(request, timeout: float):
        attempted_urls.append(str(request.full_url))
        if request.full_url.endswith("/my-account"):
            return _Response()
        raise urllib.error.URLError("not found")

    with mock.patch("urllib.request.urlopen", side_effect=_urlopen):
        account_name = resolve_account_name(settings, poe_session_id="POESESSID-123")

    assert account_name == "qa-exile"
    assert attempted_urls[0].endswith("/account/profile")
    assert attempted_urls[-1].endswith("/my-account")


def test_resolve_account_name_reads_nested_profile_shape(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"account": {"name": "qa-exile"}}).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=_Response()):
        account_name = resolve_account_name(settings, poe_session_id="POESESSID-123")

    assert account_name == "qa-exile"


def test_resolve_account_name_raises_for_unresolvable_payload(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"unexpected": "shape"}).encode("utf-8")

    with mock.patch("urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(ValueError, match="unable to resolve"):
            _ = resolve_account_name(settings, poe_session_id="POESESSID-123")


def test_resolve_account_name_rejects_html_error_bodies(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b"<html><title>Not Found</title></html>"

    with mock.patch("urllib.request.urlopen", return_value=_Response()):
        with pytest.raises(ValueError, match="unable to resolve"):
            _ = resolve_account_name(settings, poe_session_id="POESESSID-123")


def test_begin_login_persists_keyed_transaction_record(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    tx = begin_login(settings)
    rows = _load_json(_transactions_path(settings))
    row = rows[tx.state]

    assert row["state"] == tx.state
    assert row["code_verifier"] == tx.code_verifier
    assert row["created_at"] == tx.created_at
    assert row["expires_at"] == tx.expires_at
    assert row["used_at"] is None


def test_consume_login_state_is_one_time_use(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    tx = begin_login(settings)

    consumed = consume_login_state(settings, state=tx.state)

    assert consumed.state == tx.state
    assert consumed.code_verifier == tx.code_verifier
    assert _load_json(_transactions_path(settings))[tx.state]["used_at"] is not None

    with pytest.raises(OAuthExchangeError, match="state already used"):
        consume_login_state(settings, state=tx.state)


def test_consume_login_state_rejects_unknown_or_expired_state(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    with pytest.raises(OAuthExchangeError, match="invalid state"):
        consume_login_state(settings, state="missing")

    tx = begin_login(settings)
    rows = _load_json(_transactions_path(settings))
    rows[tx.state]["expires_at"] = "2000-01-01T00:00:00Z"
    _transactions_path(settings).write_text(json.dumps(rows), encoding="utf-8")

    with pytest.raises(OAuthExchangeError, match="invalid state"):
        consume_login_state(settings, state=tx.state)


def test_prune_login_transactions_removes_used_and_expired_rows(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    fresh_tx = begin_login(settings)
    used_tx = begin_login(settings)
    _ = consume_login_state(settings, state=used_tx.state)

    rows = _load_json(_transactions_path(settings))
    rows[fresh_tx.state]["expires_at"] = "2000-01-01T00:00:00Z"
    _transactions_path(settings).write_text(json.dumps(rows), encoding="utf-8")

    removed = prune_login_transactions(settings)

    assert removed == 2
    assert _load_json(_transactions_path(settings)) == {}


def test_begin_login_prunes_stale_transactions(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))

    existing = {
        "expired": {
            "state": "expired",
            "code_verifier": "v1",
            "code_challenge": "c1",
            "created_at": "2000-01-01T00:00:00Z",
            "expires_at": "2000-01-01T00:10:00Z",
            "used_at": None,
        },
        "used": {
            "state": "used",
            "code_verifier": "v2",
            "code_challenge": "c2",
            "created_at": "2026-03-01T00:00:00Z",
            "expires_at": "2026-03-01T00:10:00Z",
            "used_at": "2026-03-01T00:01:00Z",
        },
    }
    _transactions_path(settings).write_text(json.dumps(existing), encoding="utf-8")

    _ = begin_login(settings)

    rows = _load_json(_transactions_path(settings))
    assert "expired" not in rows
    assert "used" not in rows
