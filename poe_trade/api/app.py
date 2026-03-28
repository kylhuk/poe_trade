from __future__ import annotations

import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from io import BufferedIOBase
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Mapping
from typing import cast
import urllib.error
import urllib.parse
import urllib.request
from urllib.parse import parse_qs, urlparse

from poe_trade.config import settings as config_settings
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient

from .auth import cors_headers, parse_bearer_token, validate_bearer_token
from .auth_session import (
    OAuthExchangeError,
    authorize_redirect,
    clear_session,
    clear_credential_state,
    clear_oauth_token_state,
    create_session,
    begin_login,
    load_credential_state,
    load_oauth_token_state,
    get_session,
    exchange_oauth_code,
    has_connected_session_for_account,
    save_oauth_token_state,
)
from .ml import (
    BackendUnavailable,
    contract_payload,
    ensure_allowed_league,
    fetch_automation_history,
    fetch_automation_status,
    fetch_predict_one,
    fetch_status,
)
from poe_trade.ml import workflows
from poe_trade.ingestion.account_stash_harvester import AccountStashHarvester
from poe_trade.ingestion.poe_client import PoeClient
from poe_trade.ingestion.rate_limit import RateLimitPolicy
from poe_trade.ingestion.status import StatusReporter
from .ops import (
    OpsBackendUnavailable,
    ack_alert_payload,
    analytics_alerts,
    analytics_backtests,
    analytics_ingestion,
    analytics_ml,
    analytics_opportunities,
    analytics_pricing_outliers,
    analytics_report,
    analytics_scanner,
    analytics_search_history,
    analytics_search_suggestions,
    contract_payload as ops_contract_payload,
    dashboard_payload,
    scanner_recommendations_payload,
    scanner_summary_payload,
    messages_payload,
    price_check_payload,
    services_payload,
)
from .responses import ApiError, Response, json_error, json_response
from .routes import Router
from .stash import (
    StashBackendUnavailable,
    fetch_stash_item_history,
    fetch_stash_tabs,
    stash_scan_valuations_payload,
    stash_scan_status_payload,
    stash_status_payload,
)
from .service_control import (
    ServiceActionForbiddenError,
    ServiceActionInvalidError,
    ServiceControlError,
    ServiceNotFoundError,
    execute_service_action,
    list_snapshots,
)


_STASH_SCAN_START_LOCK = threading.Lock()
_PENDING_STASH_SCANS: dict[tuple[str, str, str], dict[str, object]] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _oauth_token_needs_refresh(token_state: Mapping[str, object]) -> bool:
    expires_at = _parse_iso_datetime(str(token_state.get("expires_at") or ""))
    if expires_at is None:
        return True
    return expires_at - _utcnow() <= timedelta(seconds=300)


def _refresh_oauth_token_state(
    settings: Settings,
    token_state: Mapping[str, object],
) -> dict[str, object]:
    account_name = str(token_state.get("account_name") or "").strip()
    refresh_token = str(token_state.get("refresh_token") or "").strip()
    if not account_name or not refresh_token:
        raise ApiError(
            status=401,
            code="auth_required",
            message="oauth session required",
        )

    payload = {
        "client_id": settings.oauth_client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": str(token_state.get("scope") or settings.poe_account_oauth_scope),
    }
    if settings.oauth_client_secret.strip():
        payload["client_secret"] = settings.oauth_client_secret

    request = urllib.request.Request(
        settings.poe_account_oauth_token_url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "User-Agent": settings.poe_user_agent,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=settings.poe_request_timeout
        ) as resp:
            response_body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="ignore")
        raise ApiError(
            status=502,
            code="oauth_refresh_failed",
            message=response_body or "oauth token refresh failed",
        ) from None
    except urllib.error.URLError as exc:
        raise ApiError(
            status=502,
            code="oauth_refresh_unavailable",
            message="oauth token endpoint unavailable",
        ) from exc

    try:
        response_payload = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ApiError(
            status=502,
            code="oauth_refresh_failed",
            message="invalid oauth token response",
        ) from exc
    if not isinstance(response_payload, dict):
        raise ApiError(
            status=502,
            code="oauth_refresh_failed",
            message="invalid oauth token response",
        )
    access_token = str(response_payload.get("access_token") or "").strip()
    if not access_token:
        raise ApiError(
            status=502,
            code="oauth_refresh_failed",
            message="oauth token response missing access token",
        )
    refresh_value = str(response_payload.get("refresh_token") or refresh_token).strip()
    token_type = (
        str(
            response_payload.get("token_type")
            or token_state.get("token_type")
            or "bearer"
        ).strip()
        or "bearer"
    )
    scope = str(
        response_payload.get("scope")
        or token_state.get("scope")
        or settings.poe_account_oauth_scope
    ).strip()
    expires_in = response_payload.get("expires_in")
    try:
        expires_seconds = int(expires_in) if expires_in is not None else 1800
    except (TypeError, ValueError):
        expires_seconds = 1800
    expires_at = (
        (_utcnow() + timedelta(seconds=max(expires_seconds, 0)))
        .isoformat()
        .replace("+00:00", "Z")
    )
    return save_oauth_token_state(
        settings,
        account_name=account_name,
        access_token=access_token,
        refresh_token=refresh_value,
        token_type=token_type,
        scope=scope,
        expires_at=expires_at,
        status=str(token_state.get("status") or "connected"),
    )


def _load_private_stash_token_state(
    settings: Settings,
    account_name: str,
) -> tuple[dict[str, object], str]:
    token_state = load_oauth_token_state(settings, account_name=account_name)
    if token_state is None:
        raise ApiError(
            status=401,
            code="auth_required",
            message="oauth session required",
        )

    if _oauth_token_needs_refresh(token_state):
        token_state = _refresh_oauth_token_state(settings, token_state)

    access_token = str(token_state.get("access_token") or "").strip()
    if not access_token:
        raise ApiError(
            status=401,
            code="auth_required",
            message="oauth session required",
        )
    return token_state, access_token


def _build_private_stash_harvester(
    settings: Settings,
    clickhouse_client: ClickHouseClient,
    *,
    account_name: str,
    token_state: dict[str, object],
    access_token: str,
) -> AccountStashHarvester:
    policy = RateLimitPolicy(
        settings.rate_limit_max_retries,
        settings.rate_limit_backoff_base,
        settings.rate_limit_backoff_max,
        settings.rate_limit_jitter,
    )
    poe_client = PoeClient(
        settings.poe_api_base_url,
        policy,
        settings.poe_user_agent,
        settings.poe_request_timeout,
    )
    poe_client.set_bearer_token(access_token)

    def _refresh_access_token() -> str:
        nonlocal token_state
        token_state = _refresh_oauth_token_state(settings, token_state)
        refreshed_access_token = str(token_state.get("access_token") or "").strip()
        poe_client.set_bearer_token(refreshed_access_token or None)
        return refreshed_access_token

    reporter = StatusReporter(clickhouse_client, "account_stash_harvester")
    return AccountStashHarvester(
        poe_client,
        clickhouse_client,
        reporter,
        service_name="account_stash_harvester",
        account_name=account_name,
        access_token=access_token,
        refresh_access_token=_refresh_access_token,
    )


def _scan_price_item_factory(clickhouse_client: ClickHouseClient, *, league: str):
    def _price_item(item: dict[str, object]) -> dict[str, object]:
        from poe_trade.stash_scan import serialize_stash_item_to_clipboard

        return fetch_predict_one(
            clickhouse_client,
            league=league,
            request_payload={"itemText": serialize_stash_item_to_clipboard(item)},
        )

    return _price_item


def start_private_stash_scan(
    settings: Settings,
    clickhouse_client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
) -> dict[str, object]:
    from poe_trade.stash_scan import fetch_active_scan

    with _STASH_SCAN_START_LOCK:
        scope = (account_name, league, realm)
        pending = _PENDING_STASH_SCANS.get(scope)
        if pending is not None:
            return {
                **pending,
                "deduplicated": True,
            }
        existing = fetch_active_scan(
            clickhouse_client,
            account_name=account_name,
            league=league,
            realm=realm,
            stale_timeout_seconds=settings.account_stash_scan_stale_timeout_seconds,
        )
        if existing and existing.get("isActive"):
            return {
                "scanId": str(existing.get("scanId") or ""),
                "status": "running",
                "startedAt": existing.get("startedAt"),
                "accountName": account_name,
                "league": league,
                "realm": realm,
                "deduplicated": True,
            }

        token_state, access_token = _load_private_stash_token_state(
            settings, account_name
        )

        harvester = _build_private_stash_harvester(
            settings,
            clickhouse_client,
            account_name=account_name,
            token_state=token_state,
            access_token=access_token,
        )

        scan_id = uuid.uuid4().hex
        started_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

        result_holder: dict[str, object] = {
            "scanId": scan_id,
            "status": "running",
            "startedAt": started_at,
            "accountName": account_name,
            "league": league,
            "realm": realm,
        }
        _PENDING_STASH_SCANS[scope] = dict(result_holder)

        def _runner() -> None:
            try:
                result = harvester.run_private_scan(
                    realm=realm,
                    league=league,
                    price_item=_scan_price_item_factory(
                        clickhouse_client, league=league
                    ),
                    scan_id=scan_id,
                    started_at=started_at,
                )
                result_holder.update(result)
            finally:
                with _STASH_SCAN_START_LOCK:
                    _PENDING_STASH_SCANS.pop(scope, None)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        return result_holder


class ApiApp:
    settings: Settings
    client: ClickHouseClient
    router: Router

    def __init__(self, settings: Settings, clickhouse_client: ClickHouseClient) -> None:
        if not settings.api_operator_token:
            raise ValueError("POE_API_OPERATOR_TOKEN is required")
        self.settings = settings
        self.client = clickhouse_client
        self._ml_warmup_state: dict[str, dict[str, object]] = {}
        self.router = Router()
        self._register_routes()
        self._warmup_models()

    def _register_routes(self) -> None:
        self.router.add("/healthz", ("GET",), self._healthz)
        self.router.add("/api/v1/ops/contract", ("GET", "OPTIONS"), self._ops_contract)
        self.router.add("/api/v1/ops/services", ("GET", "OPTIONS"), self._ops_services)
        self.router.add(
            "/api/v1/ops/dashboard", ("GET", "OPTIONS"), self._ops_dashboard
        )
        self.router.add("/api/v1/ops/messages", ("GET", "OPTIONS"), self._ops_messages)
        self.router.add(
            "/api/v1/ops/scanner/summary",
            ("GET", "OPTIONS"),
            self._ops_scanner_summary,
        )
        self.router.add(
            "/api/v1/ops/scanner/recommendations",
            ("GET", "OPTIONS"),
            self._ops_scanner_recommendations,
        )
        self.router.add(
            "/api/v1/ops/alerts/{alert_id}/ack",
            ("POST", "OPTIONS"),
            self._ops_ack_alert,
        )
        self.router.add(
            "/api/v1/ops/analytics/search-suggestions",
            ("GET", "OPTIONS"),
            self._ops_analytics_search_suggestions,
        )
        self.router.add(
            "/api/v1/ops/analytics/search-history",
            ("GET", "OPTIONS"),
            self._ops_analytics_search_history,
        )
        self.router.add(
            "/api/v1/ops/analytics/pricing-outliers",
            ("GET", "OPTIONS"),
            self._ops_analytics_pricing_outliers,
        )
        self.router.add(
            "/api/v1/ops/analytics/{kind}",
            ("GET", "OPTIONS"),
            self._ops_analytics,
        )
        self.router.add(
            "/api/v1/actions/services/{service_id}/{verb}",
            ("POST", "OPTIONS"),
            self._service_action,
        )
        self.router.add(
            "/api/v1/ops/leagues/{league}/price-check",
            ("POST", "OPTIONS"),
            self._price_check,
        )
        self.router.add("/api/v1/stash/tabs", ("GET", "OPTIONS"), self._stash_tabs)
        self.router.add(
            "/api/v1/stash/status",
            ("GET", "OPTIONS"),
            self._stash_status,
        )
        self.router.add(
            "/api/v1/stash/scan",
            ("POST", "OPTIONS"),
            self._stash_scan_start,
        )
        self.router.add(
            "/api/v1/stash/scan/valuations",
            ("POST", "OPTIONS"),
            self._stash_scan_valuations,
        )
        self.router.add(
            "/api/v1/stash/scan/status",
            ("GET", "OPTIONS"),
            self._stash_scan_status,
        )
        self.router.add(
            "/api/v1/stash/items/{fingerprint}/history",
            ("GET", "OPTIONS"),
            self._stash_item_history,
        )
        self.router.add("/api/v1/auth/login", ("GET", "OPTIONS"), self._auth_login)
        self.router.add(
            "/api/v1/auth/callback",
            ("GET", "OPTIONS"),
            self._auth_callback,
        )
        self.router.add(
            "/api/v1/auth/session",
            ("GET", "POST", "OPTIONS"),
            self._auth_session,
        )
        self.router.add(
            "/api/v1/auth/logout",
            ("POST", "OPTIONS"),
            self._auth_logout,
        )
        self.router.add("/api/v1/ml/contract", ("GET", "OPTIONS"), self._ml_contract)
        self.router.add(
            "/api/v1/ml/leagues/{league}/status",
            ("GET", "OPTIONS"),
            self._ml_status,
        )
        self.router.add(
            "/api/v1/ml/leagues/{league}/predict-one",
            ("POST", "OPTIONS"),
            self._ml_predict_one,
        )
        self.router.add(
            "/api/v1/ml/leagues/{league}/automation/status",
            ("GET", "OPTIONS"),
            self._ml_automation_status,
        )
        self.router.add(
            "/api/v1/ml/leagues/{league}/automation/history",
            ("GET", "OPTIONS"),
            self._ml_automation_history,
        )

    def _warmup_models(self) -> None:
        for league in self.settings.api_league_allowlist:
            try:
                self._ml_warmup_state[league] = workflows.warmup_active_models(
                    self.client, league=league
                )
            except Exception as exc:
                self._ml_warmup_state[league] = {
                    "lastAttemptAt": None,
                    "routes": {"_global": f"warmup_failed:{type(exc).__name__}"},
                }
                logging.getLogger(__name__).warning(
                    "ml service warmup failed for league=%s: %s",
                    league,
                    exc,
                )

    def _ml_readiness_payload(self) -> dict[str, object]:
        leagues: dict[str, object] = {}
        degraded = False
        for league in self.settings.api_league_allowlist:
            warmup = self._ml_warmup_state.get(
                league
            ) or workflows._warmup_status_payload(league)
            routes_obj = warmup.get("routes") if isinstance(warmup, dict) else {}
            routes = routes_obj if isinstance(routes_obj, dict) else {}
            degraded_routes = {
                str(route): str(state)
                for route, state in routes.items()
                if str(state) not in {"warm", "inactive"}
            }
            if degraded_routes:
                degraded = True
            leagues[league] = {
                "ready": not degraded_routes,
                "routes": routes,
                "degradedRoutes": degraded_routes,
            }
        return {"ready": not degraded, "leagues": leagues}

    def handle(
        self,
        *,
        method: str,
        raw_path: str,
        headers: dict[str, str],
        body_reader: BufferedIOBase,
    ) -> Response:
        parsed = urlparse(raw_path)
        path = parsed.path
        query_params = {
            str(key): [str(v) for v in values]
            for key, values in parse_qs(parsed.query).items()
        }
        origin = headers.get("Origin")
        cors = self._cors_headers(origin=origin, path=path)
        match = self.router.match(method, path)
        if match.route is None:
            if match.allowed_methods:
                raise ApiError(
                    status=405,
                    code="method_not_allowed",
                    message="method not allowed",
                    headers=dict(cors),
                )
            raise ApiError(
                status=404,
                code="route_not_found",
                message="route not found",
                headers=dict(cors),
            )

        context: dict[str, object] = {
            "method": method,
            "path": path,
            "headers": headers,
            "body_reader": body_reader,
            "cors_headers": cors,
            "query_params": query_params,
            **match.params,
        }
        protected = _is_protected_path(path)

        if protected and origin and not cors:
            raise ApiError(
                status=403,
                code="origin_denied",
                message="origin is not allowed",
            )

        if protected and method != "OPTIONS":
            self._require_auth(path=path, headers=headers, cors_headers_for_error=cors)

        if method == "OPTIONS":
            if protected and not cors:
                raise ApiError(
                    status=403,
                    code="origin_denied",
                    message="origin is not allowed",
                )
            response = json_response({}, status=204, headers=cors)
            return response

        response = match.route.handler(context)
        if cors:
            response.headers.update(cors)
        return response

    def _require_auth(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
        cors_headers_for_error: Mapping[str, str],
    ) -> None:
        authorization = headers.get("Authorization")
        if parse_bearer_token(
            authorization
        ) is None and self._allow_trusted_origin_without_bearer(
            path=path, headers=headers
        ):
            return
        if parse_bearer_token(authorization) is None:
            raise ApiError(
                status=401,
                code="auth_required",
                message="bearer token required",
                headers=dict(cors_headers_for_error),
            )
        if not validate_bearer_token(authorization, self.settings.api_operator_token):
            raise ApiError(
                status=401,
                code="auth_invalid",
                message="invalid bearer token",
                headers=dict(cors_headers_for_error),
            )

    def _allow_trusted_origin_without_bearer(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
    ) -> bool:
        if not self.settings.api_trusted_origin_bypass:
            return False
        if not _is_protected_path(path):
            return False
        origin = headers.get("Origin", "")
        if not origin or origin not in self.settings.api_cors_origins:
            return False
        referer = headers.get("Referer", "")
        if not referer:
            return False
        origin_parts = urlparse(origin)
        referer_parts = urlparse(referer)
        if not origin_parts.scheme or not origin_parts.netloc:
            return False
        if not referer_parts.scheme or not referer_parts.netloc:
            return False
        return (
            referer_parts.scheme == origin_parts.scheme
            and referer_parts.netloc == origin_parts.netloc
        )

    def _cors_headers(self, *, origin: str | None, path: str) -> dict[str, str]:
        if not origin or not _is_cors_path(path):
            return {}
        if origin not in self.settings.api_cors_origins:
            return {}
        return cors_headers(origin, ("GET", "POST", "OPTIONS"))

    def _healthz(self, _context: Mapping[str, object]) -> Response:
        ml = self._ml_readiness_payload()
        healthy = bool(ml.get("ready", False))
        return json_response(
            {
                "status": "ok" if healthy else "degraded",
                "service": "api",
                "version": "v1",
                "ml": ml,
            },
            status=200 if healthy else 503,
        )

    def _ml_contract(self, _context: Mapping[str, object]) -> Response:
        return json_response(contract_payload(self.settings))

    def _ops_contract(self, _context: Mapping[str, object]) -> Response:
        snapshots = list_snapshots(self.client)
        visible = [row.id for row in snapshots]
        controllable = [row.id for row in snapshots if row.allowed_actions]
        return json_response(
            ops_contract_payload(
                self.settings,
                visible_service_ids=visible,
                controllable_service_ids=controllable,
            )
        )

    def _ops_services(self, _context: Mapping[str, object]) -> Response:
        snapshots = list_snapshots(self.client)
        return json_response({"services": services_payload(snapshots)})

    def _ops_dashboard(self, _context: Mapping[str, object]) -> Response:
        snapshots = list_snapshots(self.client)
        try:
            payload = dashboard_payload(self.client, snapshots)
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _ops_messages(self, _context: Mapping[str, object]) -> Response:
        try:
            messages = messages_payload(self.client)
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response({"messages": messages})

    def _ops_scanner_summary(self, _context: Mapping[str, object]) -> Response:
        try:
            payload = scanner_summary_payload(self.client)
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _ops_scanner_recommendations(self, _context: Mapping[str, object]) -> Response:
        query_params = _query_params_from_context(_context)
        sort_by = _first_query_param(
            query_params,
            "sort",
            default="expected_profit_per_operation_chaos",
        )
        league = _optional_query_param(query_params, "league")
        strategy_id = _optional_query_param(query_params, "strategy_id")
        cursor = _optional_query_param(query_params, "cursor")
        try:
            limit = _int_query_param(query_params, "limit", default=50)
            min_confidence = _optional_float_query_param(query_params, "min_confidence")
        except ValueError:
            raise ApiError(status=400, code="invalid_input", message="invalid input")
        try:
            payload = scanner_recommendations_payload(
                self.client,
                limit=limit,
                sort_by=sort_by,
                min_confidence=min_confidence,
                league=league,
                strategy_id=strategy_id,
                cursor=cursor,
            )
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        except ValueError:
            raise ApiError(status=400, code="invalid_input", message="invalid input")
        return json_response(payload)

    def _ops_ack_alert(self, context: Mapping[str, object]) -> Response:
        alert_id = str(context.get("alert_id") or "")
        if not alert_id:
            raise ApiError(status=400, code="invalid_input", message="invalid input")
        try:
            payload = ack_alert_payload(self.client, alert_id=alert_id)
        except ValueError:
            raise ApiError(
                status=400, code="invalid_input", message="invalid input"
            ) from None
        except Exception:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _ops_analytics_search_suggestions(
        self, context: Mapping[str, object]
    ) -> Response:
        league = (
            self.settings.api_league_allowlist[0]
            if self.settings.api_league_allowlist
            else ""
        )
        query_params = cast(dict[str, list[str]], context.get("query_params") or {})
        try:
            payload = analytics_search_suggestions(
                self.client,
                query=str((query_params.get("query") or [""])[0] or ""),
            )
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _ops_analytics_search_history(self, context: Mapping[str, object]) -> Response:
        league = (
            self.settings.api_league_allowlist[0]
            if self.settings.api_league_allowlist
            else ""
        )
        query_params = cast(dict[str, list[str]], context.get("query_params") or {})
        try:
            payload = analytics_search_history(
                self.client,
                query_params=query_params,
                default_league=league,
            )
        except ValueError:
            raise ApiError(status=400, code="invalid_input", message="invalid input")
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _ops_analytics_pricing_outliers(
        self, context: Mapping[str, object]
    ) -> Response:
        league = (
            self.settings.api_league_allowlist[0]
            if self.settings.api_league_allowlist
            else ""
        )
        query_params = cast(dict[str, list[str]], context.get("query_params") or {})
        try:
            payload = analytics_pricing_outliers(
                self.client,
                query_params=query_params,
                default_league=league,
            )
        except ValueError:
            raise ApiError(status=400, code="invalid_input", message="invalid input")
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _ops_analytics(self, context: Mapping[str, object]) -> Response:
        kind = str(context.get("kind") or "")
        league = (
            self.settings.api_league_allowlist[0]
            if self.settings.api_league_allowlist
            else ""
        )
        query_params = cast(dict[str, list[str]], context.get("query_params") or {})
        try:
            if kind == "ingestion":
                payload = analytics_ingestion(self.client)
            elif kind == "scanner":
                payload = analytics_scanner(self.client)
            elif kind == "opportunities":
                payload = analytics_opportunities(self.client)
            elif kind == "alerts":
                payload = analytics_alerts(self.client)
            elif kind == "backtests":
                payload = analytics_backtests(self.client)
            elif kind == "ml":
                payload = analytics_ml(self.client, league=league)
            elif kind == "report":
                payload = analytics_report(self.client, league=league)
            elif kind == "search-suggestions":
                payload = analytics_search_suggestions(
                    self.client,
                    query=str((query_params.get("query") or [""])[0] or ""),
                )
            elif kind == "search-history":
                payload = analytics_search_history(
                    self.client,
                    query_params=query_params,
                    default_league=league,
                )
            elif kind == "pricing-outliers":
                payload = analytics_pricing_outliers(
                    self.client,
                    query_params=query_params,
                    default_league=league,
                )
            else:
                raise ApiError(
                    status=404,
                    code="route_not_found",
                    message="route not found",
                )
        except OpsBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        except BackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _service_action(self, context: Mapping[str, object]) -> Response:
        service_id = str(context.get("service_id") or "")
        verb = str(context.get("verb") or "")
        cors = _cors_from_context(context)
        try:
            snapshot = execute_service_action(
                self.client,
                service_id=service_id,
                action=verb,
            )
        except ServiceNotFoundError:
            raise ApiError(
                status=404,
                code="service_not_found",
                message="service not found",
                headers=cors,
            ) from None
        except ServiceActionInvalidError:
            raise ApiError(
                status=400,
                code="service_action_invalid",
                message="invalid service action",
                headers=cors,
            ) from None
        except ServiceActionForbiddenError:
            raise ApiError(
                status=403,
                code="service_action_forbidden",
                message="service action is forbidden",
                headers=cors,
            ) from None
        except ServiceControlError as exc:
            raise ApiError(
                status=503,
                code="service_action_failed",
                message="service action failed",
                details=_safe_service_action_details(exc),
                headers=cors,
            ) from None
        return json_response({"service": services_payload([snapshot])[0]})

    def _price_check(self, context: Mapping[str, object]) -> Response:
        league = str(context.get("league") or "")
        cors = _cors_from_context(context)
        try:
            ensure_allowed_league(league, self.settings)
        except ValueError:
            raise ApiError(
                status=400,
                code="league_not_allowed",
                message="league is not allowed",
                headers=cors,
            ) from None
        try:
            body = _read_json_body(
                _headers_from_context(context),
                _body_reader_from_context(context),
                max_body_bytes=self.settings.api_max_body_bytes,
            )
        except ApiError as exc:
            if not exc.headers:
                exc.headers = dict(cors)
            raise
        raw_text = body.get("itemText")
        if not isinstance(raw_text, str) or not raw_text.strip():
            raise ApiError(
                status=400,
                code="invalid_input",
                message="invalid input",
                headers=cors,
            )
        try:
            payload = price_check_payload(
                self.client,
                league=league,
                item_text=raw_text,
            )
        except (BackendUnavailable, OpsBackendUnavailable, ValueError):
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
                headers=cors,
            ) from None
        return json_response(payload)

    def _stash_tabs(self, context: Mapping[str, object]) -> Response:
        if not self.settings.enable_account_stash:
            raise ApiError(
                status=503,
                code="feature_unavailable",
                message="stash feature is unavailable; set POE_ENABLE_ACCOUNT_STASH=true",
            )
        params = _query_params_from_context(context)
        league = _first_query_param(
            params,
            "league",
            default=(self.settings.account_stash_league or ""),
        )
        realm = _first_query_param(
            params,
            "realm",
            default=(self.settings.account_stash_realm or "pc"),
        )
        if not league:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="league is required",
            )
        session_cookie = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        session = get_session(self.settings, session_id=session_cookie)
        if session is None or str(session.get("status") or "") == "disconnected":
            raise ApiError(
                status=401,
                code="auth_required",
                message="session required",
            )
        if str(session.get("status") or "") == "session_expired":
            raise ApiError(
                status=401,
                code="session_expired",
                message="session expired",
            )
        account_name = str(session.get("account_name") or "")
        if not account_name:
            raise ApiError(
                status=401,
                code="auth_required",
                message="session required",
            )
        try:
            return json_response(
                fetch_stash_tabs(
                    self.client,
                    league=league,
                    realm=realm,
                    account_name=account_name,
                )
            )
        except StashBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None

    def _stash_status(self, context: Mapping[str, object]) -> Response:
        params = _query_params_from_context(context)
        league = _first_query_param(
            params,
            "league",
            default=(self.settings.account_stash_league or ""),
        )
        realm = _first_query_param(
            params,
            "realm",
            default=(self.settings.account_stash_realm or "pc"),
        )
        session_cookie = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        session = get_session(self.settings, session_id=session_cookie)
        try:
            payload = stash_status_payload(
                self.client,
                league=league,
                realm=realm,
                enable_account_stash=self.settings.enable_account_stash,
                session=session,
            )
        except StashBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _stash_scan_start(self, context: Mapping[str, object]) -> Response:
        if not self.settings.enable_account_stash:
            raise ApiError(
                status=503,
                code="feature_unavailable",
                message="stash feature is unavailable; set POE_ENABLE_ACCOUNT_STASH=true",
            )
        account_name, league, realm = self._stash_account_scope(context)
        result = start_private_stash_scan(
            self.settings,
            self.client,
            account_name=account_name,
            league=league,
            realm=realm,
        )
        return json_response(result, status=202)

    def _stash_scan_valuations(self, context: Mapping[str, object]) -> Response:
        if not self.settings.enable_account_stash:
            raise ApiError(
                status=503,
                code="feature_unavailable",
                message="stash feature is unavailable; set POE_ENABLE_ACCOUNT_STASH=true",
            )
        account_name, league, realm = self._stash_account_scope(context)
        try:
            body = _read_json_body(
                _headers_from_context(context),
                _body_reader_from_context(context),
                max_body_bytes=self.settings.api_max_body_bytes,
            )
        except ApiError as exc:
            if not exc.headers:
                exc.headers = dict(_cors_from_context(context))
            raise

        def _require_string(field: str) -> str:
            value = body.get(field)
            text = str(value or "").strip()
            if not text:
                raise ApiError(
                    status=400,
                    code="invalid_input",
                    message="invalid input",
                )
            return text

        def _require_float(field: str) -> float:
            value = body.get(field)
            if isinstance(value, bool) or value is None:
                raise ApiError(
                    status=400,
                    code="invalid_input",
                    message="invalid input",
                )
            try:
                return float(str(value))
            except (TypeError, ValueError) as exc:
                raise ApiError(
                    status=400,
                    code="invalid_input",
                    message="invalid input",
                ) from exc

        def _require_int(field: str) -> int:
            value = body.get(field)
            if isinstance(value, bool) or value is None:
                raise ApiError(
                    status=400,
                    code="invalid_input",
                    message="invalid input",
                )
            try:
                parsed = float(str(value))
            except (TypeError, ValueError) as exc:
                raise ApiError(
                    status=400,
                    code="invalid_input",
                    message="invalid input",
                ) from exc
            if not parsed.is_integer():
                raise ApiError(
                    status=400,
                    code="invalid_input",
                    message="invalid input",
                )
            return int(parsed)

        scan_id = _require_string("scanId")
        structured_mode = body.get("structuredMode", False)
        if not isinstance(structured_mode, bool):
            raise ApiError(
                status=400,
                code="invalid_input",
                message="invalid input",
            )
        item_id = str(body.get("itemId") or "").strip()
        if not structured_mode and not item_id:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="invalid input",
            )
        min_threshold = _require_float("minThreshold")
        max_threshold = _require_float("maxThreshold")
        max_age_days = _require_int("maxAgeDays")
        if min_threshold > max_threshold or max_age_days <= 0:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="invalid input",
            )

        try:
            payload = stash_scan_valuations_payload(
                self.client,
                account_name=account_name,
                league=league,
                realm=realm,
                scan_id=scan_id,
                item_id=item_id or None,
                structured_mode=structured_mode,
                min_threshold=min_threshold,
                max_threshold=max_threshold,
                max_age_days=max_age_days,
            )
        except LookupError:
            raise ApiError(
                status=404,
                code="item_not_found",
                message="item not found",
            ) from None
        except StashBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _stash_scan_status(self, context: Mapping[str, object]) -> Response:
        account_name, league, realm = self._stash_account_scope(context)
        try:
            payload = stash_scan_status_payload(
                self.client,
                account_name=account_name,
                league=league,
                realm=realm,
                stale_timeout_seconds=self.settings.account_stash_scan_stale_timeout_seconds,
            )
        except StashBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _stash_item_history(self, context: Mapping[str, object]) -> Response:
        account_name, league, realm = self._stash_account_scope(context)
        fingerprint = str(context.get("fingerprint") or "")
        if not fingerprint:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="fingerprint is required",
            )
        params = _query_params_from_context(context)
        limit_raw = _first_query_param(params, "limit", default="20")
        try:
            limit = int(limit_raw)
        except ValueError as exc:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="limit must be an integer",
            ) from exc
        try:
            payload = fetch_stash_item_history(
                self.client,
                account_name=account_name,
                league=league,
                realm=realm,
                fingerprint=fingerprint,
                limit=max(limit, 1),
            )
        except StashBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None
        return json_response(payload)

    def _stash_account_scope(
        self, context: Mapping[str, object]
    ) -> tuple[str, str, str]:
        params = _query_params_from_context(context)
        league = _first_query_param(
            params,
            "league",
            default=(self.settings.account_stash_league or ""),
        )
        realm = _first_query_param(
            params,
            "realm",
            default=(self.settings.account_stash_realm or "pc"),
        )
        if not league:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="league is required",
            )
        session_cookie = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        session = get_session(self.settings, session_id=session_cookie)
        if session is None or str(session.get("status") or "") == "disconnected":
            raise ApiError(
                status=401,
                code="auth_required",
                message="session required",
            )
        if str(session.get("status") or "") == "session_expired":
            raise ApiError(
                status=401,
                code="session_expired",
                message="session expired",
            )
        account_name = str(session.get("account_name") or "")
        if not account_name:
            raise ApiError(
                status=401,
                code="auth_required",
                message="session required",
            )
        return account_name, league, realm

    def _auth_login(self, _context: Mapping[str, object]) -> Response:
        tx = begin_login(self.settings)
        return json_response({"authorizeUrl": authorize_redirect(self.settings, tx)})

    def _auth_callback(self, context: Mapping[str, object]) -> Response:
        params = _query_params_from_context(context)
        code = _first_query_param(params, "code", default="").strip()
        state = _first_query_param(params, "state", default="").strip()
        error = _first_query_param(params, "error", default="").strip()
        error_description = _first_query_param(
            params, "error_description", default=""
        ).strip()

        if error:
            message = error_description or error
            if error == "access_denied":
                raise ApiError(status=401, code="oauth_access_denied", message=message)
            raise ApiError(status=400, code="oauth_callback_failed", message=message)

        if not code:
            raise ApiError(status=400, code="invalid_input", message="code is required")
        if not state:
            raise ApiError(
                status=400, code="invalid_input", message="state is required"
            )

        try:
            exchange = exchange_oauth_code(self.settings, code=code, state=state)
        except OAuthExchangeError as exc:
            raise ApiError(status=exc.status, code=exc.code, message=str(exc)) from None
        if not exchange.access_token.strip():
            raise ApiError(
                status=502,
                code="oauth_missing_access_token",
                message="oauth token response missing access token",
            )

        existing_session_id = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        clear_session(self.settings, session_id=existing_session_id)
        expires_at = ""
        if exchange.expires_in is not None:
            expires_at = (
                (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=max(exchange.expires_in, 0))
                )
                .isoformat()
                .replace("+00:00", "Z")
            )
        _ = save_oauth_token_state(
            self.settings,
            account_name=exchange.account_name,
            access_token=exchange.access_token,
            refresh_token=exchange.refresh_token,
            token_type=exchange.token_type,
            scope=exchange.scope,
            expires_at=expires_at,
            status="connected",
        )
        session = create_session(self.settings, account_name=exchange.account_name)
        cookie = _session_set_cookie(
            self.settings.auth_cookie_name,
            str(session.get("session_id") or ""),
            secure=self.settings.auth_cookie_secure,
        )
        return json_response(
            {
                "status": "connected",
                "accountName": str(session.get("account_name") or ""),
                "expiresAt": session.get("expires_at"),
                "scope": session.get("scope") or [],
            },
            headers={"Set-Cookie": cookie},
        )

    def _auth_session(self, context: Mapping[str, object]) -> Response:
        if str(context.get("method") or "") == "POST":
            raise ApiError(
                status=400,
                code="invalid_input",
                message="OAuth-only login; POESESSID bootstrap is not supported",
            )
        session_id = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        session = get_session(self.settings, session_id=session_id)
        if session is None:
            return json_response({"status": "disconnected", "accountName": None})
        if str(session.get("status") or "") == "session_expired":
            clear_session(self.settings, session_id=session_id)
            clear_cookie = _session_clear_cookie(
                self.settings.auth_cookie_name,
                secure=self.settings.auth_cookie_secure,
            )
            return json_response(
                {
                    "status": "session_expired",
                    "accountName": str(session.get("account_name") or ""),
                    "expiresAt": session.get("expires_at"),
                },
                headers={"Set-Cookie": clear_cookie},
            )
        return json_response(
            {
                "status": "connected",
                "accountName": str(session.get("account_name") or ""),
                "expiresAt": session.get("expires_at"),
                "scope": session.get("scope") or [],
            }
        )

    def _auth_logout(self, context: Mapping[str, object]) -> Response:
        session_id = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        session = get_session(self.settings, session_id=session_id)
        clear_session(self.settings, session_id=session_id)
        account_name = str(session.get("account_name") or "") if session else ""
        should_clear_account_state = (
            account_name
            and not has_connected_session_for_account(
                self.settings,
                account_name=account_name,
                exclude_session_id=session_id,
            )
        )
        if should_clear_account_state:
            clear_oauth_token_state(self.settings, account_name=account_name)
        credential_state = load_credential_state(self.settings)
        credential_account_name = str(credential_state.get("account_name") or "")
        if (not account_name and not credential_account_name) or (
            should_clear_account_state and credential_account_name == account_name
        ):
            _ = clear_credential_state(self.settings)
        clear_cookie = _session_clear_cookie(
            self.settings.auth_cookie_name,
            secure=self.settings.auth_cookie_secure,
        )
        return Response(
            status=200,
            headers={"Set-Cookie": clear_cookie, "Content-Type": "application/json"},
            body=b'{"status":"logged_out"}',
        )

    def _ml_status(self, context: Mapping[str, object]) -> Response:
        league = str(context.get("league") or "")
        cors = _cors_from_context(context)
        try:
            ensure_allowed_league(league, self.settings)
        except ValueError:
            raise ApiError(
                status=400,
                code="league_not_allowed",
                message="league is not allowed",
                headers=cors,
            ) from None
        try:
            return json_response(fetch_status(self.client, league=league))
        except BackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
                headers=cors,
            ) from None

    def _ml_predict_one(self, context: Mapping[str, object]) -> Response:
        league = str(context.get("league") or "")
        cors = _cors_from_context(context)
        try:
            ensure_allowed_league(league, self.settings)
        except ValueError:
            raise ApiError(
                status=400,
                code="league_not_allowed",
                message="league is not allowed",
                headers=cors,
            ) from None

        try:
            body = _read_json_body(
                _headers_from_context(context),
                _body_reader_from_context(context),
                max_body_bytes=self.settings.api_max_body_bytes,
            )
        except ApiError as exc:
            if not exc.headers:
                exc.headers = dict(cors)
            raise
        try:
            payload = fetch_predict_one(
                self.client, league=league, request_payload=body
            )
        except ValueError:
            raise ApiError(
                status=400,
                code="invalid_input",
                message="invalid input",
                headers=cors,
            ) from None
        except BackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
                headers=cors,
            ) from None
        return json_response(payload)

    def _ml_automation_status(self, context: Mapping[str, object]) -> Response:
        league = str(context.get("league") or "")
        cors = _cors_from_context(context)
        try:
            ensure_allowed_league(league, self.settings)
        except ValueError:
            raise ApiError(
                status=400,
                code="league_not_allowed",
                message="league is not allowed",
                headers=cors,
            ) from None
        try:
            payload = fetch_automation_status(self.client, league=league)
        except BackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
                headers=cors,
            ) from None
        return json_response(payload)

    def _ml_automation_history(self, context: Mapping[str, object]) -> Response:
        league = str(context.get("league") or "")
        cors = _cors_from_context(context)
        try:
            ensure_allowed_league(league, self.settings)
        except ValueError:
            raise ApiError(
                status=400,
                code="league_not_allowed",
                message="league is not allowed",
                headers=cors,
            ) from None
        try:
            payload = fetch_automation_history(self.client, league=league)
        except BackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
                headers=cors,
            ) from None
        return json_response(payload)


def create_app(
    settings: Settings | None = None,
    *,
    clickhouse_client: ClickHouseClient | None = None,
) -> ApiApp:
    cfg = settings or config_settings.get_settings()
    client = clickhouse_client or ClickHouseClient.from_env(cfg.clickhouse_url)
    return ApiApp(cfg, client)


def make_handler(app: ApiApp) -> type[BaseHTTPRequestHandler]:
    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_OPTIONS(self) -> None:
            self._handle("OPTIONS")

        def log_message(self, format: str, *args: object) -> None:
            return

        def _handle(self, method: str) -> None:
            headers = {key: value for key, value in self.headers.items()}
            try:
                response = app.handle(
                    method=method,
                    raw_path=self.path,
                    headers=headers,
                    body_reader=self.rfile,
                )
            except ApiError as exc:
                response = json_error(
                    status=exc.status,
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                    headers=exc.headers,
                )
            except Exception:
                response = json_error(
                    status=500,
                    code="internal_error",
                    message="internal server error",
                )
            self.send_response(response.status)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.end_headers()
            try:
                _ = self.wfile.write(response.body)
            except BrokenPipeError:
                return

    return _Handler


def serve(app: ApiApp, *, host: str, port: int) -> None:
    handler = make_handler(app)
    server = ThreadingHTTPServer((host, port), handler)
    server.serve_forever()


def _read_json_body(
    headers: Mapping[str, str],
    body_reader: BufferedIOBase,
    *,
    max_body_bytes: int,
) -> dict[str, object]:
    raw_length = headers.get("Content-Length")
    if raw_length is None:
        raise ApiError(
            status=400,
            code="invalid_input",
            message="content-length header is required",
        )
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise ApiError(
            status=400,
            code="invalid_input",
            message="content-length must be an integer",
        ) from exc
    if length < 0:
        raise ApiError(
            status=400,
            code="invalid_input",
            message="content-length must be non-negative",
        )
    if length > max_body_bytes:
        raise ApiError(
            status=413,
            code="request_too_large",
            message="request body exceeds limit",
        )
    body_bytes = body_reader.read(length)
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApiError(
            status=400,
            code="invalid_json",
            message="request body must be valid JSON",
        ) from exc
    if not isinstance(payload, dict):
        raise ApiError(
            status=400,
            code="invalid_input",
            message="request body must be a JSON object",
        )
    return {str(k): v for k, v in payload.items()}


def _headers_from_context(context: Mapping[str, object]) -> dict[str, str]:
    headers = context.get("headers")
    if not isinstance(headers, dict):
        raise ApiError(
            status=500, code="internal_error", message="internal server error"
        )
    return {str(key): str(value) for key, value in headers.items()}


def _body_reader_from_context(context: Mapping[str, object]) -> BufferedIOBase:
    body_reader = context.get("body_reader")
    if not isinstance(body_reader, BufferedIOBase):
        raise ApiError(
            status=500, code="internal_error", message="internal server error"
        )
    return cast(BufferedIOBase, body_reader)


def _cors_from_context(context: Mapping[str, object]) -> dict[str, str]:
    cors_headers = context.get("cors_headers")
    if not isinstance(cors_headers, dict):
        return {}
    return {str(key): str(value) for key, value in cors_headers.items()}


def _is_protected_path(path: str) -> bool:
    return path.startswith(
        (
            "/api/v1/ml/",
            "/api/v1/ops/",
            "/api/v1/actions/",
        )
    )


def _is_cors_path(path: str) -> bool:
    return _is_protected_path(path) or path.startswith(
        ("/api/v1/stash/", "/api/v1/auth/")
    )


def _query_params_from_context(context: Mapping[str, object]) -> dict[str, list[str]]:
    raw = context.get("query_params")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(value, list):
            continue
        result[str(key)] = [str(item) for item in value]
    return result


def _first_query_param(
    query_params: Mapping[str, list[str]],
    key: str,
    *,
    default: str,
) -> str:
    values = query_params.get(key)
    if not values:
        return default
    return values[0]


def _optional_query_param(
    query_params: Mapping[str, list[str]],
    key: str,
) -> str | None:
    value = _first_query_param(query_params, key, default="").strip()
    return value or None


def _int_query_param(
    query_params: Mapping[str, list[str]],
    key: str,
    *,
    default: int,
) -> int:
    raw = _optional_query_param(query_params, key)
    if raw is None:
        return default
    value = int(raw)
    if value < 1:
        raise ValueError(key)
    return value


def _optional_float_query_param(
    query_params: Mapping[str, list[str]],
    key: str,
) -> float | None:
    raw = _optional_query_param(query_params, key)
    if raw is None:
        return None
    return float(raw)


def _session_cookie_from_headers(
    headers: Mapping[str, str], *, cookie_name: str
) -> str | None:
    raw = headers.get("Cookie")
    if not raw:
        return None
    parts = [chunk.strip() for chunk in raw.split(";") if chunk.strip()]
    for part in parts:
        key, sep, value = part.partition("=")
        if sep and key.strip() == cookie_name:
            return value.strip() or None
    return None


def _session_set_cookie(cookie_name: str, session_id: str, *, secure: bool) -> str:
    secure_token = "; Secure" if secure else ""
    return f"{cookie_name}={session_id}; Path=/; HttpOnly; SameSite=Lax{secure_token}; Max-Age=604800"


def _session_clear_cookie(cookie_name: str, *, secure: bool) -> str:
    secure_token = "; Secure" if secure else ""
    return f"{cookie_name}=; Path=/; HttpOnly; SameSite=Lax{secure_token}; Max-Age=0"


def _safe_service_action_details(exc: ServiceControlError) -> dict[str, str] | None:
    reason = str(exc).strip()
    if not reason:
        return None
    normalized = " ".join(reason.split())
    return {"reason": normalized[:240]}
