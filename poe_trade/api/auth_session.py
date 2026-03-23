from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from contextlib import contextmanager
from typing import Any
from urllib.parse import quote, unquote, urlencode

from poe_trade.config.settings import Settings


_ACCOUNT_NAME_TEXT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._#-]{1,63}$")
_PROFILE_URL_PATTERN = re.compile(r"/account/view-profile/([^\"'/?<>=\s]+)")
_PROFILE_META_PATTERN = re.compile(
    r"content=[\"']Profile\s*-\s*([^\"']+)\s*-\s*Path of Exile[\"']",
    flags=re.IGNORECASE,
)
_PROFILE_TITLE_PATTERN = re.compile(
    r"<title>\s*([^<]+?)\s*(?:['’]s profile|[-–—]\s*Path of Exile|Profile)\s*</title>",
    flags=re.IGNORECASE,
)


class AuthSessionError(Exception):
    def __init__(self, message: str, *, code: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class AccountResolutionError(AuthSessionError, ValueError):
    pass


class OAuthExchangeError(AuthSessionError, RuntimeError):
    pass


@dataclass(frozen=True)
class OAuthExchangeResult:
    account_name: str
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int | None
    scope: str


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _state_dir(settings: Settings) -> Path:
    root = Path(settings.auth_state_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(tmp_path, path)


@contextmanager
def _transactions_locked(settings: Settings):
    lock_path = _transactions_lock_path(settings)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


@contextmanager
def _path_locked(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _transactions_path(settings: Settings) -> Path:
    return _state_dir(settings) / "oauth-state.json"


def _transactions_lock_path(settings: Settings) -> Path:
    return _state_dir(settings) / "oauth-state.lock"


def _state_path(settings: Settings) -> Path:
    return _transactions_path(settings)


def _load_login_transactions(settings: Settings) -> dict[str, dict[str, Any]]:
    payload = _load_json(_transactions_path(settings))
    if not payload:
        return {}
    if all(isinstance(value, dict) for value in payload.values()):
        return {
            key: value
            for key, value in payload.items()
            if isinstance(key, str) and isinstance(value, dict)
        }
    legacy_state = payload.get("state")
    legacy_code_verifier = payload.get("code_verifier")
    if isinstance(legacy_state, str) and isinstance(legacy_code_verifier, str):
        return {
            legacy_state: {
                "state": legacy_state,
                "code_verifier": legacy_code_verifier,
                "code_challenge": str(payload.get("code_challenge") or ""),
                "created_at": str(payload.get("created_at") or _iso(_now())),
                "expires_at": str(payload.get("expires_at") or _iso(_now())),
                "used_at": payload.get("used_at")
                if payload.get("used_at") is None
                else str(payload.get("used_at")),
            }
        }
    return {}


def _save_login_transactions(
    settings: Settings, transactions: dict[str, dict[str, Any]]
) -> None:
    _save_json(_transactions_path(settings), transactions)


def _sessions_path(settings: Settings) -> Path:
    return _state_dir(settings) / "sessions.json"


def credential_state_path(settings: Settings) -> Path:
    return _state_dir(settings) / "credential-state.json"


def load_credential_state(settings: Settings) -> dict[str, Any]:
    payload = _load_json(credential_state_path(settings))
    account_name = payload.get("account_name")
    poe_session_id = payload.get("poe_session_id")
    cf_clearance = payload.get("cf_clearance")
    status = payload.get("status")
    updated_at = payload.get("updated_at")
    if not isinstance(account_name, str):
        account_name = ""
    if not isinstance(poe_session_id, str):
        poe_session_id = ""
    if not isinstance(cf_clearance, str):
        cf_clearance = ""
    if not isinstance(status, str):
        status = "unknown"
    if not isinstance(updated_at, str):
        updated_at = _iso(_now())
    return {
        "account_name": account_name,
        "poe_session_id": poe_session_id,
        "cf_clearance": cf_clearance,
        "status": status,
        "updated_at": updated_at,
    }


def save_credential_state(
    settings: Settings,
    *,
    account_name: str,
    status: str,
    poe_session_id: str = "",
    cf_clearance: str = "",
) -> dict[str, Any]:
    with _path_locked(credential_state_path(settings)):
        payload = {
            "account_name": account_name,
            "poe_session_id": poe_session_id.strip(),
            "cf_clearance": cf_clearance.strip(),
            "status": status,
            "updated_at": _iso(_now()),
        }
        _save_json(credential_state_path(settings), payload)
        return payload


def clear_credential_state(settings: Settings) -> dict[str, Any]:
    return save_credential_state(
        settings,
        account_name="",
        poe_session_id="",
        cf_clearance="",
        status="logged_out",
    )


def oauth_credential_state_path(settings: Settings) -> Path:
    return _state_dir(settings) / "oauth-credential-state.json"


def _oauth_refresh_lock_path(settings: Settings, *, account_name: str) -> Path:
    normalized = account_name.strip() or "anonymous"
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return _state_dir(settings) / "oauth-refresh-locks" / f"{digest}.lock"


def load_oauth_credential_state(settings: Settings) -> dict[str, Any]:
    payload = _load_json(oauth_credential_state_path(settings))
    account_name = str(payload.get("account_name") or "").strip()
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    token_type = str(payload.get("token_type") or "bearer").strip() or "bearer"
    scope = str(payload.get("scope") or "").strip()
    expires_at = str(payload.get("expires_at") or "").strip()
    status = str(payload.get("status") or "").strip()
    if not status:
        status = "connected" if access_token else "disconnected"
    updated_at = str(payload.get("updated_at") or _iso(_now())).strip()
    refresh_error_code = str(payload.get("refresh_error_code") or "").strip()
    refresh_error_message = str(payload.get("refresh_error_message") or "").strip()
    refresh_error_status = payload.get("refresh_error_status")
    if not isinstance(refresh_error_status, int):
        refresh_error_status = 0
    return {
        "account_name": account_name,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": token_type,
        "scope": scope,
        "expires_at": expires_at,
        "status": status,
        "updated_at": updated_at,
        "refresh_error_code": refresh_error_code,
        "refresh_error_message": refresh_error_message,
        "refresh_error_status": refresh_error_status,
    }


def save_oauth_credential_state(
    settings: Settings,
    *,
    account_name: str,
    access_token: str,
    refresh_token: str,
    token_type: str,
    scope: str,
    expires_at: str,
    status: str,
    refresh_error_code: str = "",
    refresh_error_message: str = "",
    refresh_error_status: int = 0,
) -> dict[str, Any]:
    with _path_locked(oauth_credential_state_path(settings)):
        payload = {
            "account_name": account_name.strip(),
            "access_token": access_token.strip(),
            "refresh_token": refresh_token.strip(),
            "token_type": token_type.strip() or "bearer",
            "scope": scope.strip(),
            "expires_at": expires_at.strip(),
            "status": status.strip() or "connected",
            "updated_at": _iso(_now()),
            "refresh_error_code": refresh_error_code.strip(),
            "refresh_error_message": refresh_error_message.strip(),
            "refresh_error_status": int(refresh_error_status or 0),
        }
        _save_json(oauth_credential_state_path(settings), payload)
        return payload


def clear_oauth_credential_state(settings: Settings) -> dict[str, Any]:
    return save_oauth_credential_state(
        settings,
        account_name="",
        access_token="",
        refresh_token="",
        token_type="bearer",
        scope="",
        expires_at="",
        status="disconnected",
    )


def _oauth_refresh_terminal_error(state: dict[str, Any]) -> OAuthExchangeError | None:
    code = str(state.get("refresh_error_code") or "").strip()
    message = str(state.get("refresh_error_message") or "").strip()
    status = state.get("refresh_error_status")
    if code and message:
        status_int = int(status or 400)
        return OAuthExchangeError(message, code=code, status=status_int)
    if str(state.get("status") or "").strip() == "disconnected":
        return OAuthExchangeError(
            "oauth credential disconnected",
            code="oauth_credential_disconnected",
            status=401,
        )
    return None


def _oauth_refresh_expires_at(expires_in: object) -> str:
    if expires_in is None:
        return _iso(_now() + timedelta(hours=1))
    try:
        seconds = int(expires_in)
    except (TypeError, ValueError):
        seconds = 3600
    return _iso(_now() + timedelta(seconds=max(seconds, 0)))


def _refresh_oauth_access_token_locked(
    settings: Settings,
    *,
    state: dict[str, Any],
) -> dict[str, Any]:
    refresh_token = str(state.get("refresh_token") or "").strip()
    if not refresh_token:
        raise OAuthExchangeError(
            "missing refresh token",
            code="missing_refresh_token",
            status=400,
        )
    form: dict[str, object] = {
        "client_id": settings.oauth_client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": str(state.get("scope") or settings.poe_account_oauth_scope).strip(),
    }
    if settings.oauth_client_secret.strip():
        form["client_secret"] = settings.oauth_client_secret
    body, status = _http_post_form(
        settings.poe_account_oauth_token_url,
        form=form,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.poe_user_agent,
        },
        timeout=settings.poe_request_timeout,
    )
    if status is None:
        raise OAuthExchangeError(
            "oauth token endpoint unavailable",
            code="oauth_token_unavailable",
            status=502,
        )
    payload = _parse_json_object(body)
    if payload is None:
        raise OAuthExchangeError(
            "invalid oauth token response",
            code="oauth_invalid_response",
            status=502,
        )
    if status >= 400 or payload.get("error"):
        message = str(
            payload.get("error_description")
            or payload.get("error")
            or "oauth token refresh failed"
        )
        raise OAuthExchangeError(
            message,
            code="oauth_refresh_failed",
            status=400 if status in {400, 401, 403} else 502,
        )
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise OAuthExchangeError(
            "oauth token response missing access or refresh token",
            code="oauth_missing_token",
            status=502,
        )
    token_type = str(payload.get("token_type") or state.get("token_type") or "bearer")
    scope = str(
        payload.get("scope") or state.get("scope") or settings.poe_account_oauth_scope
    )
    account_name = str(state.get("account_name") or "").strip()
    return save_oauth_credential_state(
        settings,
        account_name=account_name,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        scope=scope,
        expires_at=_oauth_refresh_expires_at(payload.get("expires_in")),
        status="connected",
    )


def refresh_oauth_access_token(settings: Settings) -> dict[str, Any]:
    """Refresh and persist OAuth credentials for one account.

    Contract:
    - one in-flight refresh per account name
    - refresh token rotation is written atomically
    - terminal 4xx refresh failures clear tokens and mark the account disconnected
    - concurrent waiters reuse the committed state instead of re-posting
    """
    state = load_oauth_credential_state(settings)
    account_name = str(state.get("account_name") or "").strip()
    if not account_name:
        raise OAuthExchangeError(
            "account name is required",
            code="missing_account_name",
            status=400,
        )
    lock_path = _oauth_refresh_lock_path(settings, account_name=account_name)
    with _path_locked(lock_path):
        current = load_oauth_credential_state(settings)
        terminal_error = _oauth_refresh_terminal_error(current)
        if terminal_error is not None:
            raise terminal_error
        if (
            current.get("access_token")
            and current.get("refresh_token")
            and (
                str(current.get("access_token") or "").strip()
                != str(state.get("access_token") or "").strip()
                or str(current.get("refresh_token") or "").strip()
                != str(state.get("refresh_token") or "").strip()
            )
        ):
            return current
        try:
            return _refresh_oauth_access_token_locked(settings, state=current)
        except OAuthExchangeError as exc:
            terminal_status = exc.status in {400, 401, 403}
            if not terminal_status:
                raise
            _ = save_oauth_credential_state(
                settings,
                account_name=account_name,
                access_token="",
                refresh_token="",
                token_type=str(current.get("token_type") or "bearer"),
                scope=str(current.get("scope") or settings.poe_account_oauth_scope),
                expires_at=str(current.get("expires_at") or _iso(_now())),
                status="disconnected",
                refresh_error_code=exc.code,
                refresh_error_message=str(exc),
                refresh_error_status=exc.status,
            )
            raise


def build_private_stash_cookie_header(
    *, poe_session_id: str, cf_clearance: str = ""
) -> str:
    cookies = [f"POESESSID={poe_session_id.strip()}"]
    clearance = cf_clearance.strip()
    if clearance:
        cookies.append(f"cf_clearance={clearance}")
    return "; ".join(cookies)


def resolve_account_name(settings: Settings, *, poe_session_id: str) -> str:
    trimmed_session_id = poe_session_id.strip()
    if not trimmed_session_id:
        raise AccountResolutionError(
            "poeSessionId is required",
            code="missing_poe_session_id",
            status=400,
        )
    request_headers = {
        "Accept": "application/json, text/html;q=0.9, text/plain;q=0.8",
        "Cookie": f"POESESSID={trimmed_session_id}",
        "User-Agent": settings.poe_user_agent,
    }

    saw_upstream = False
    saw_invalid_session = False

    for url in _account_name_candidate_urls(settings):
        body, status = _http_get_text(
            url,
            headers=request_headers,
            timeout=settings.poe_request_timeout,
        )
        if status is None:
            continue
        saw_upstream = True
        if status in {401, 403}:
            saw_invalid_session = True
            continue
        account_name = _extract_account_name_from_response_body(body)
        if account_name:
            return account_name

    for url in _account_name_html_urls(settings):
        body, status = _http_get_text(
            url,
            headers=request_headers,
            timeout=settings.poe_request_timeout,
        )
        if status is None:
            continue
        saw_upstream = True
        if status in {401, 403}:
            saw_invalid_session = True
            continue
        account_name = _extract_account_name_from_html(body)
        if account_name:
            return account_name

    if saw_invalid_session:
        raise AccountResolutionError(
            "invalid POESESSID or account profile unavailable",
            code="invalid_poe_session",
            status=400,
        )
    if not saw_upstream:
        raise AccountResolutionError(
            "account resolution upstream unavailable",
            code="account_resolution_unavailable",
            status=502,
        )
    raise AccountResolutionError(
        "unable to resolve account name from POESESSID",
        code="account_resolution_failed",
        status=400,
    )


def exchange_oauth_code(
    settings: Settings,
    *,
    code: str,
    state: str,
) -> OAuthExchangeResult:
    if not code.strip():
        raise OAuthExchangeError("code is required", code="missing_code", status=400)
    if not settings.oauth_client_id.strip():
        raise OAuthExchangeError(
            "missing oauth client id",
            code="oauth_client_id_missing",
            status=500,
        )
    if not settings.poe_account_redirect_uri.strip():
        raise OAuthExchangeError(
            "missing oauth redirect uri",
            code="oauth_redirect_uri_missing",
            status=500,
        )
    tx_state = consume_login_state(settings, state=state)
    code_verifier = tx_state.code_verifier.strip()

    form = {
        "client_id": settings.oauth_client_id,
        "grant_type": "authorization_code",
        "code": code.strip(),
        "redirect_uri": settings.poe_account_redirect_uri,
        "scope": settings.poe_account_oauth_scope,
        "code_verifier": code_verifier,
    }
    if settings.oauth_client_secret.strip():
        form["client_secret"] = settings.oauth_client_secret

    body, status = _http_post_form(
        settings.poe_account_oauth_token_url,
        form=form,
        headers={
            "Accept": "application/json",
            "User-Agent": settings.poe_user_agent,
        },
        timeout=settings.poe_request_timeout,
    )
    if status is None:
        raise OAuthExchangeError(
            "oauth token endpoint unavailable",
            code="oauth_token_unavailable",
            status=502,
        )
    payload = _parse_json_object(body)
    if payload is None:
        raise OAuthExchangeError(
            "invalid oauth token response",
            code="oauth_invalid_response",
            status=502,
        )
    if status >= 400 or payload.get("error"):
        message = str(
            payload.get("error_description")
            or payload.get("error")
            or "oauth code exchange failed"
        )
        raise OAuthExchangeError(
            message,
            code="oauth_exchange_failed",
            status=400 if status in {400, 401, 403} else 502,
        )
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    token_type = str(payload.get("token_type") or "bearer").strip() or "bearer"
    scope = str(payload.get("scope") or settings.poe_account_oauth_scope).strip()
    account_name = _extract_account_name(payload)
    if not account_name and access_token:
        account_name = resolve_account_name_from_access_token(
            settings, access_token=access_token
        )
    if not account_name:
        raise OAuthExchangeError(
            "oauth token response missing account name",
            code="oauth_missing_account_name",
            status=502,
        )
    expires_in = payload.get("expires_in")
    expires_int: int | None
    if expires_in is None:
        expires_int = None
    else:
        try:
            expires_int = int(expires_in)
        except (TypeError, ValueError):
            expires_int = None
    return OAuthExchangeResult(
        account_name=account_name,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type=token_type,
        expires_in=expires_int,
        scope=scope,
    )


def resolve_account_name_from_access_token(
    settings: Settings,
    *,
    access_token: str,
) -> str:
    token = access_token.strip()
    if not token:
        return ""
    headers = {
        "Accept": "application/json, text/plain;q=0.9",
        "Authorization": f"Bearer {token}",
        "User-Agent": settings.poe_user_agent,
    }
    for url in _account_name_candidate_urls(settings):
        body, status = _http_get_text(
            url, headers=headers, timeout=settings.poe_request_timeout
        )
        if status is None or status >= 400:
            continue
        account_name = _extract_account_name_from_response_body(body)
        if account_name:
            return account_name
    return ""


def _account_name_candidate_urls(settings: Settings) -> tuple[str, ...]:
    api_base = settings.poe_api_base_url.rstrip("/")
    auth_base = settings.poe_auth_base_url.rstrip("/")
    candidates = (
        f"{api_base}/account/profile",
        f"{api_base}/account-profile",
        f"{api_base}/account",
        f"{auth_base}/api/account-profile",
    )
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        deduped.append(candidate)
        seen.add(candidate)
    return tuple(deduped)


def _account_name_html_urls(settings: Settings) -> tuple[str, ...]:
    auth_base = settings.poe_auth_base_url.rstrip("/")
    if auth_base.endswith("/oauth"):
        auth_base = auth_base[: -len("/oauth")]
    return (
        f"{auth_base}/my-account",
        f"{auth_base}/account/profile",
    )


def _extract_account_name(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in (
            "accountName",
            "account_name",
            "name",
            "username",
            "display_name",
        ):
            candidate = payload.get(key)
            normalized = _normalize_account_name(candidate)
            if normalized:
                return normalized
        nested = payload.get("account")
        if isinstance(nested, dict):
            return _extract_account_name(nested)
    return None


def _extract_account_name_from_response_body(payload: str) -> str | None:
    parsed = _parse_json_object(payload)
    if parsed is not None:
        account_name = _extract_account_name(parsed)
        if account_name:
            return account_name
    account_name = _extract_account_name_from_text(payload)
    if account_name:
        return account_name
    return _extract_account_name_from_html(payload)


def _extract_account_name_from_text(payload: str) -> str | None:
    candidate = payload.strip()
    if not candidate:
        return None
    if "<" in candidate or "\n" in candidate or "\r" in candidate:
        return None
    return _normalize_account_name(candidate)


def _extract_account_name_from_html(payload: str) -> str | None:
    if not payload:
        return None
    for pattern in (
        _PROFILE_URL_PATTERN,
        _PROFILE_META_PATTERN,
        _PROFILE_TITLE_PATTERN,
    ):
        match = pattern.search(payload)
        if not match:
            continue
        candidate = _normalize_account_name(match.group(1))
        if candidate:
            return candidate
    json_patterns = (
        r'"accountName"\s*:\s*"([^\"]+)"',
        r'"account_name"\s*:\s*"([^\"]+)"',
        r'"username"\s*:\s*"([^\"]+)"',
    )
    for pattern in json_patterns:
        match = re.search(pattern, payload)
        if not match:
            continue
        candidate = _normalize_account_name(match.group(1))
        if candidate:
            return candidate
    return None


def _normalize_account_name(candidate: object) -> str | None:
    if not isinstance(candidate, str):
        return None
    value = unquote(candidate).strip()
    if not value:
        return None
    value = value.split("?", 1)[0].split("/", 1)[0].strip()
    if not value:
        return None
    if not _ACCOUNT_NAME_TEXT_PATTERN.match(value):
        return None
    return value


def _parse_json_object(payload: str) -> dict[str, Any] | None:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if isinstance(decoded, dict):
        return decoded
    return None


def _http_get_text(
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
) -> tuple[str, int | None]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = getattr(resp, "status", None)
            if status is None:
                getcode = getattr(resp, "getcode", None)
                if callable(getcode):
                    status = getcode()
            if status is None:
                status = 200
            return body, int(status)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        return body, int(exc.code)
    except (UnicodeDecodeError, urllib.error.URLError):
        return "", None


def _http_post_form(
    url: str,
    *,
    form: dict[str, object],
    headers: dict[str, str],
    timeout: float,
) -> tuple[str, int | None]:
    encoded = urlencode(
        {key: value for key, value in form.items() if value is not None}
    ).encode("utf-8")
    request_headers = {
        **headers,
        "Content-Type": "application/x-www-form-urlencoded",
    }
    request = urllib.request.Request(
        url,
        headers=request_headers,
        method="POST",
        data=encoded,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            status = getattr(resp, "status", None)
            if status is None:
                getcode = getattr(resp, "getcode", None)
                if callable(getcode):
                    status = getcode()
            if status is None:
                status = 200
            return body, int(status)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:
            body = ""
        return body, int(exc.code)
    except (UnicodeDecodeError, urllib.error.URLError):
        return "", None


@dataclass(frozen=True)
class LoginTransaction:
    state: str
    code_verifier: str
    code_challenge: str
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class ConsumedLoginTransaction:
    state: str
    code_verifier: str
    created_at: str
    expires_at: str
    used_at: str


def begin_login(settings: Settings) -> LoginTransaction:
    raw_verifier = secrets.token_urlsafe(48)
    code_verifier = raw_verifier[:128]
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(24)
    created = _now()
    expires = created + timedelta(minutes=10)
    tx = LoginTransaction(
        state=state,
        code_verifier=code_verifier,
        code_challenge=code_challenge,
        created_at=_iso(created),
        expires_at=_iso(expires),
    )
    with _transactions_locked(settings):
        _prune_login_transactions_locked(settings, now=_now())
        transactions = _load_login_transactions(settings)
        transactions[tx.state] = {
            "state": tx.state,
            "code_verifier": tx.code_verifier,
            "code_challenge": tx.code_challenge,
            "created_at": tx.created_at,
            "expires_at": tx.expires_at,
            "used_at": None,
        }
        _save_login_transactions(settings, transactions)
    return tx


def consume_login_state(
    settings: Settings,
    *,
    state: str,
) -> ConsumedLoginTransaction:
    with _transactions_locked(settings):
        transactions = _load_login_transactions(settings)
        row = transactions.get(state)
        if not isinstance(row, dict) or row.get("state") != state:
            raise OAuthExchangeError("invalid state", code="invalid_state", status=400)
        expires = _parse_iso_datetime(str(row.get("expires_at") or ""))
        if expires is None:
            raise OAuthExchangeError("invalid state", code="invalid_state", status=400)
        now = _now()
        if now > expires:
            raise OAuthExchangeError("invalid state", code="invalid_state", status=400)
        code_verifier = str(row.get("code_verifier") or "").strip()
        if not code_verifier:
            raise OAuthExchangeError(
                "missing code verifier",
                code="missing_code_verifier",
                status=400,
            )
        used_at = row.get("used_at")
        if isinstance(used_at, str) and used_at.strip():
            raise OAuthExchangeError(
                "state already used", code="state_already_used", status=400
            )
        consumed_at = _iso(now)
        row = {
            **row,
            "used_at": consumed_at,
        }
        transactions[state] = row
        _save_login_transactions(settings, transactions)
        return ConsumedLoginTransaction(
            state=state,
            code_verifier=code_verifier,
            created_at=str(row.get("created_at") or ""),
            expires_at=str(row.get("expires_at") or ""),
            used_at=consumed_at,
        )


def prune_login_transactions(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    with _transactions_locked(settings):
        return _prune_login_transactions_locked(settings, now=now or _now())


def _prune_login_transactions_locked(
    settings: Settings,
    *,
    now: datetime,
) -> int:
    current = now
    transactions = _load_login_transactions(settings)
    kept: dict[str, dict[str, Any]] = {}
    removed = 0
    for state, row in transactions.items():
        if not isinstance(row, dict):
            removed += 1
            continue
        expires = _parse_iso_datetime(str(row.get("expires_at") or ""))
        used_at = row.get("used_at")
        if (
            expires is None
            or current > expires
            or (isinstance(used_at, str) and used_at.strip())
        ):
            removed += 1
            continue
        kept[state] = row
    if removed:
        _save_login_transactions(settings, kept)
    return removed


def validate_state(settings: Settings, *, state: str) -> bool:
    transactions = _load_login_transactions(settings)
    row = transactions.get(state)
    if not isinstance(row, dict) or row.get("state") != state:
        return False
    expires = _parse_iso_datetime(str(row.get("expires_at") or ""))
    if expires is None:
        return False
    used_at = row.get("used_at")
    return _now() <= expires and not (isinstance(used_at, str) and used_at.strip())


def create_session(settings: Settings, *, account_name: str) -> dict[str, Any]:
    with _path_locked(_sessions_path(settings)):
        sessions = _load_json(_sessions_path(settings))
        session_id = secrets.token_urlsafe(32)
        expires = _now() + timedelta(days=7)
        session = {
            "session_id": session_id,
            "account_name": account_name,
            "status": "connected",
            "created_at": _iso(_now()),
            "expires_at": _iso(expires),
            "scope": [
                part.strip()
                for part in settings.poe_account_oauth_scope.split(" ")
                if part.strip()
            ],
        }
        sessions[session_id] = session
        _save_json(_sessions_path(settings), sessions)
        return session


def get_session(settings: Settings, *, session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    sessions = _load_json(_sessions_path(settings))
    row = sessions.get(session_id)
    if not isinstance(row, dict):
        return None
    expires_raw = row.get("expires_at")
    if not isinstance(expires_raw, str):
        return None
    try:
        expires = datetime.fromisoformat(expires_raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if _now() > expires:
        return {
            "session_id": session_id,
            "status": "session_expired",
            "account_name": row.get("account_name") or "",
            "expires_at": expires_raw,
            "scope": row.get("scope") or [],
        }
    return row


def clear_session(settings: Settings, *, session_id: str | None) -> None:
    if not session_id:
        return
    with _path_locked(_sessions_path(settings)):
        sessions = _load_json(_sessions_path(settings))
        if session_id in sessions:
            del sessions[session_id]
            _save_json(_sessions_path(settings), sessions)


def authorize_redirect(settings: Settings, tx: LoginTransaction) -> str:
    base = settings.poe_account_oauth_authorize_url
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.oauth_client_id,
            "redirect_uri": settings.poe_account_redirect_uri,
            "scope": settings.poe_account_oauth_scope,
            "state": tx.state,
            "code_challenge": tx.code_challenge,
            "code_challenge_method": "S256",
        },
        quote_via=quote,
    )
    return f"{base}?{query}"
