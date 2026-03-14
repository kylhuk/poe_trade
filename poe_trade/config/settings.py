"""Settings resolved from the environment with sane defaults."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

from . import constants


load_dotenv(override=False)


def _parse_env_list(env_name: str, default: list[str]) -> tuple[str, ...]:
    raw = os.getenv(env_name)
    if not raw:
        return tuple(default)
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    return tuple(tokens) if tokens else tuple(default)


def _get_env_str(env_name: str, default: str) -> str:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    return raw


def _get_env_alias(env_names: tuple[str, ...], default: str) -> str:
    for env_name in env_names:
        raw = os.getenv(env_name)
        if raw is not None and raw != "":
            return raw
    return default


def _resolve_clickhouse_url() -> str:
    direct = _get_env_alias(("POE_CLICKHOUSE_URL",), "")
    if direct:
        return direct
    host = _get_env_alias(("CH_HOST",), "")
    if host:
        scheme = _get_env_alias(("CH_SCHEME",), "http")
        port = _get_env_alias(("CH_PORT",), "8123")
        return f"{scheme}://{host}:{port}"
    return constants.DEFAULT_CLICKHOUSE_URL


def _parse_env_int(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _parse_env_float(env_name: str, default: float) -> float:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_env_bool(env_name: str, default: bool) -> bool:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "t", "yes", "y", "on", "enabled", "enable"):
        return True
    if value in ("0", "false", "f", "no", "n", "off", "disabled", "disable"):
        return False
    return default


def _parse_thresholds() -> dict[str, Any]:
    raw = os.getenv("POE_THRESHOLDS")
    if not raw:
        return dict(constants.DEFAULT_THRESHOLDS)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            thresholds = {str(k): float(v) for k, v in parsed.items()}
            default = dict(constants.DEFAULT_THRESHOLDS)
            default.update(thresholds)
            return default
    except ValueError:  # pragma: no cover
        pass
    return dict(constants.DEFAULT_THRESHOLDS)


def _parse_service_ports() -> dict[str, int]:
    raw = os.getenv("POE_SERVICE_PORTS")
    ports = dict(constants.DEFAULT_SERVICE_PORTS)
    if not raw:
        return ports
    for entry in raw.split(","):
        pair = entry.strip().split("=")
        if len(pair) != 2:
            continue
        name, value = pair
        try:
            ports[name.strip()] = int(value.strip())
        except ValueError:
            continue
    return ports


def _read_file_trimmed(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError as exc:
        raise ValueError(f"unable to read OAuth secret file {path!r}: {exc}") from exc


def _resolve_oauth_client_secret() -> str:
    env_secret = os.getenv("POE_OAUTH_CLIENT_SECRET", "").strip()
    file_path = (os.getenv("POE_OAUTH_CLIENT_SECRET_FILE") or "").strip()
    if not file_path:
        return env_secret
    try:
        secret = _read_file_trimmed(file_path)
    except ValueError:
        return env_secret
    return secret or env_secret


@dataclass(frozen=True)
class Settings:
    realms: tuple[str, ...]
    leagues: tuple[str, ...]
    ingest_contract_version: int
    enable_psapi: bool
    enable_cxapi: bool
    chaos_currency: str
    time_buckets: tuple[str, ...]
    thresholds: dict[str, float]
    clickhouse_url: str
    service_ports: dict[str, int]
    poe_api_base_url: str
    poe_auth_base_url: str
    poe_user_agent: str
    rate_limit_max_retries: int
    rate_limit_backoff_base: float
    rate_limit_backoff_max: float
    rate_limit_jitter: float
    poe_request_timeout: float
    checkpoint_dir: str
    market_poll_interval: float
    stash_poll_interval: float
    psapi_poll_seconds: float
    cxapi_backfill_hours: int
    cxapi_hour_offset_seconds: int
    refresh_refs_minutes: int
    scan_minutes: int
    raw_psapi_ttl_days: int
    raw_cx_ttl_days: int
    silver_ttl_days: int
    stash_api_path: str
    stash_bootstrap_until_league: str
    stash_bootstrap_from_beginning: bool
    stash_trigger_token: str
    oauth_client_id: str
    oauth_client_secret: str
    oauth_grant_type: str
    oauth_scope: str
    api_bind_host: str
    api_bind_port: int
    api_operator_token: str
    api_cors_origins: tuple[str, ...]
    api_max_body_bytes: int
    api_league_allowlist: tuple[str, ...]
    enable_account_stash: bool
    account_stash_access_token: str
    account_stash_realm: str
    account_stash_league: str
    account_stash_poll_interval: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            realms=_parse_env_list("POE_REALMS", constants.DEFAULT_REALMS),
            leagues=_parse_env_list("POE_LEAGUES", constants.DEFAULT_LEAGUES),
            ingest_contract_version=constants.INGEST_CONTRACT_VERSION,
            enable_psapi=_parse_env_bool(
                "POE_ENABLE_PSAPI", constants.DEFAULT_ENABLE_PSAPI
            ),
            enable_cxapi=_parse_env_bool(
                "POE_ENABLE_CXAPI", constants.DEFAULT_ENABLE_CXAPI
            ),
            chaos_currency=os.getenv(
                "POE_CHAOS_CURRENCY", constants.DEFAULT_CHAOS_CURRENCY
            ),
            time_buckets=_parse_env_list(
                "POE_TIME_BUCKETS", constants.DEFAULT_TIME_BUCKETS
            ),
            thresholds=_parse_thresholds(),
            clickhouse_url=_resolve_clickhouse_url(),
            service_ports=_parse_service_ports(),
            poe_api_base_url=_get_env_str(
                "POE_API_BASE_URL", constants.DEFAULT_POE_API_BASE_URL
            ),
            poe_auth_base_url=_get_env_str(
                "POE_AUTH_BASE_URL", constants.DEFAULT_POE_AUTH_BASE_URL
            ),
            poe_user_agent=_get_env_str(
                "POE_USER_AGENT", constants.DEFAULT_POE_USER_AGENT
            ),
            rate_limit_max_retries=_parse_env_int(
                "POE_RATE_LIMIT_MAX_RETRIES",
                constants.DEFAULT_RATE_LIMIT_MAX_RETRIES,
            ),
            rate_limit_backoff_base=_parse_env_float(
                "POE_RATE_LIMIT_BACKOFF_BASE",
                constants.DEFAULT_RATE_LIMIT_BACKOFF_BASE,
            ),
            rate_limit_backoff_max=_parse_env_float(
                "POE_RATE_LIMIT_BACKOFF_MAX",
                constants.DEFAULT_RATE_LIMIT_BACKOFF_MAX,
            ),
            rate_limit_jitter=_parse_env_float(
                "POE_RATE_LIMIT_JITTER",
                constants.DEFAULT_RATE_LIMIT_JITTER,
            ),
            poe_request_timeout=_parse_env_float(
                "POE_REQUEST_TIMEOUT",
                constants.DEFAULT_POE_REQUEST_TIMEOUT,
            ),
            checkpoint_dir=_get_env_alias(
                ("POE_CHECKPOINT_DIR", "POE_CURSOR_DIR"),
                constants.DEFAULT_CHECKPOINT_DIR,
            ),
            market_poll_interval=_parse_env_float(
                "POE_MARKET_POLL_INTERVAL",
                constants.DEFAULT_MARKET_POLL_INTERVAL,
            ),
            stash_poll_interval=_parse_env_float(
                "POE_STASH_POLL_INTERVAL",
                constants.DEFAULT_STASH_POLL_INTERVAL,
            ),
            psapi_poll_seconds=_parse_env_float(
                "POE_PSAPI_POLL_SECONDS",
                _parse_env_float(
                    "POE_MARKET_POLL_INTERVAL", constants.DEFAULT_PSAPI_POLL_SECONDS
                ),
            ),
            cxapi_backfill_hours=_parse_env_int(
                "POE_CXAPI_BACKFILL_HOURS",
                constants.DEFAULT_CXAPI_BACKFILL_HOURS,
            ),
            cxapi_hour_offset_seconds=_parse_env_int(
                "POE_CXAPI_HOUR_OFFSET_SECONDS",
                constants.DEFAULT_CXAPI_HOUR_OFFSET_SECONDS,
            ),
            refresh_refs_minutes=_parse_env_int(
                "POE_REFRESH_REFS_MINUTES",
                constants.DEFAULT_REFRESH_REFS_MINUTES,
            ),
            scan_minutes=_parse_env_int(
                "POE_SCAN_MINUTES", constants.DEFAULT_SCAN_MINUTES
            ),
            raw_psapi_ttl_days=_parse_env_int(
                "POE_RAW_PSAPI_TTL_DAYS", constants.DEFAULT_RAW_PSAPI_TTL_DAYS
            ),
            raw_cx_ttl_days=_parse_env_int(
                "POE_RAW_CX_TTL_DAYS", constants.DEFAULT_RAW_CX_TTL_DAYS
            ),
            silver_ttl_days=_parse_env_int(
                "POE_SILVER_TTL_DAYS", constants.DEFAULT_SILVER_TTL_DAYS
            ),
            stash_api_path=_get_env_str(
                "POE_STASH_API_PATH",
                constants.DEFAULT_POE_STASH_API_PATH,
            ),
            stash_bootstrap_until_league=_get_env_str(
                "POE_STASH_BOOTSTRAP_UNTIL_LEAGUE",
                constants.DEFAULT_STASH_BOOTSTRAP_UNTIL_LEAGUE,
            ).strip(),
            stash_bootstrap_from_beginning=_parse_env_bool(
                "POE_STASH_BOOTSTRAP_FROM_BEGINNING",
                constants.DEFAULT_STASH_BOOTSTRAP_FROM_BEGINNING,
            ),
            stash_trigger_token=_get_env_str(
                "POE_STASH_TRIGGER_TOKEN",
                constants.DEFAULT_STASH_TRIGGER_TOKEN,
            ),
            oauth_client_id=os.getenv("POE_OAUTH_CLIENT_ID", ""),
            oauth_client_secret=_resolve_oauth_client_secret(),
            oauth_grant_type=_get_env_str(
                "POE_OAUTH_GRANT_TYPE", constants.DEFAULT_OAUTH_GRANT_TYPE
            ),
            oauth_scope=_get_env_str("POE_OAUTH_SCOPE", constants.DEFAULT_OAUTH_SCOPE),
            api_bind_host=_get_env_str(
                "POE_API_BIND_HOST", constants.DEFAULT_API_BIND_HOST
            ),
            api_bind_port=_parse_env_int(
                "POE_API_BIND_PORT", constants.DEFAULT_API_BIND_PORT
            ),
            api_operator_token=_get_env_str(
                "POE_API_OPERATOR_TOKEN", constants.DEFAULT_API_OPERATOR_TOKEN
            ),
            api_cors_origins=_parse_env_list(
                "POE_API_CORS_ORIGINS", list(constants.DEFAULT_API_CORS_ORIGINS)
            ),
            api_max_body_bytes=_parse_env_int(
                "POE_API_MAX_BODY_BYTES", constants.DEFAULT_API_MAX_BODY_BYTES
            ),
            api_league_allowlist=_parse_env_list(
                "POE_API_LEAGUE_ALLOWLIST", list(constants.DEFAULT_API_LEAGUE_ALLOWLIST)
            ),
            enable_account_stash=_parse_env_bool(
                "POE_ENABLE_ACCOUNT_STASH", constants.DEFAULT_ENABLE_ACCOUNT_STASH
            ),
            account_stash_access_token=_get_env_str(
                "POE_ACCOUNT_STASH_ACCESS_TOKEN", ""
            ),
            account_stash_realm=_get_env_str(
                "POE_ACCOUNT_STASH_REALM", constants.DEFAULT_ACCOUNT_STASH_REALM
            ),
            account_stash_league=_get_env_str(
                "POE_ACCOUNT_STASH_LEAGUE", constants.DEFAULT_ACCOUNT_STASH_LEAGUE
            ),
            account_stash_poll_interval=_parse_env_float(
                "POE_ACCOUNT_STASH_POLL_INTERVAL",
                constants.DEFAULT_ACCOUNT_STASH_POLL_INTERVAL,
            ),
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


__all__ = ["Settings", "get_settings"]
