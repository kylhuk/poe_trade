from __future__ import annotations

import os
import json
import urllib.error
from pathlib import Path
from unittest import mock

import pytest

from poe_trade.api.auth_session import (
    clear_credential_state,
    credential_state_path,
    load_credential_state,
    resolve_account_name,
    save_credential_state,
)
from poe_trade.config.settings import Settings


def _settings(state_dir: str) -> Settings:
    with mock.patch.dict(os.environ, {"POE_AUTH_STATE_DIR": state_dir}, clear=True):
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
    assert loaded["status"] == "unknown"
    assert isinstance(loaded["updated_at"], str)


def test_clear_credential_state_resets_sensitive_fields(tmp_path: Path) -> None:
    settings = _settings(str(tmp_path / "auth-state"))
    _ = save_credential_state(
        settings,
        account_name="qa-exile",
        poe_session_id="POESESSID-123",
        status="bootstrap_connected",
    )

    cleared = clear_credential_state(settings)

    assert cleared["status"] == "logged_out"
    assert cleared["account_name"] == ""
    assert cleared["poe_session_id"] == ""
    assert load_credential_state(settings) == cleared


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
    assert request.get_header("Cookie") == "POESESSID=POESESSID-123"


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
