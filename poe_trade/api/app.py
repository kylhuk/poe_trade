from __future__ import annotations

import json
import logging
from io import BufferedIOBase
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Mapping
from typing import cast
from urllib.parse import parse_qs, urlparse

from poe_trade.config import settings as config_settings
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient

from .auth import cors_headers, parse_bearer_token, validate_bearer_token
from .auth_session import (
    AccountResolutionError,
    OAuthExchangeError,
    authorize_redirect,
    clear_credential_state,
    begin_login,
    clear_session,
    create_session,
    exchange_oauth_code,
    get_session,
    resolve_account_name,
    save_credential_state,
    validate_state,
)
from .ml import (
    BackendUnavailable,
    contract_payload,
    ensure_allowed_league,
    fetch_automation_history,
    fetch_automation_status,
    fetch_predict_one,
    fetch_rollout_controls,
    fetch_status,
    update_rollout_controls,
)
from poe_trade.ml import workflows
from .ops import (
    OpsBackendUnavailable,
    ack_alert_payload,
    analytics_alerts,
    analytics_backtests,
    analytics_ingestion,
    analytics_ml,
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
from .stash import StashBackendUnavailable, fetch_stash_tabs, stash_status_payload
from .service_control import (
    ServiceActionForbiddenError,
    ServiceActionInvalidError,
    ServiceControlError,
    ServiceNotFoundError,
    execute_service_action,
    list_snapshots,
)


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
            "/api/v1/ml/leagues/{league}/rollout",
            ("GET", "POST", "OPTIONS"),
            self._ml_rollout,
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
        sort_by = _first_query_param(query_params, "sort", default="recorded_at")
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
        except (BackendUnavailable, ValueError):
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

    def _auth_login(self, _context: Mapping[str, object]) -> Response:
        tx = begin_login(self.settings)
        if not self.settings.oauth_client_id:
            location = f"/api/v1/auth/callback?state={tx.state}&code=qa-simulated"
        else:
            if not self.settings.poe_account_redirect_uri:
                raise ApiError(
                    status=500,
                    code="oauth_config_invalid",
                    message="POE_ACCOUNT_REDIRECT_URI must exactly match your registered OAuth redirect URI",
                )
            location = authorize_redirect(self.settings, tx)
        return Response(
            status=302,
            headers={"Location": location},
            body=b"",
        )

    def _auth_callback(self, context: Mapping[str, object]) -> Response:
        params = _query_params_from_context(context)
        state = _first_query_param(params, "state", default="")
        code = _first_query_param(params, "code", default="")
        if not code:
            raise ApiError(status=400, code="invalid_input", message="code is required")

        if not self.settings.oauth_client_id:
            if not validate_state(self.settings, state=state):
                raise ApiError(
                    status=400, code="invalid_state", message="invalid state"
                )
            session = create_session(self.settings, account_name="qa-exile")
            location = (
                f"{self.settings.poe_account_frontend_complete_uri}?status=success"
            )
            cookie = _session_set_cookie(
                self.settings.auth_cookie_name,
                str(session.get("session_id") or ""),
                secure=self.settings.auth_cookie_secure,
            )
            return Response(
                status=302,
                headers={"Location": location, "Set-Cookie": cookie},
                body=b"",
            )

        try:
            exchange = exchange_oauth_code(self.settings, code=code, state=state)
        except OAuthExchangeError as exc:
            location = (
                f"{self.settings.poe_account_frontend_complete_uri}"
                f"?status=error&reason={str(exc.code)}"
            )
            return Response(status=302, headers={"Location": location}, body=b"")

        _ = save_credential_state(
            self.settings,
            account_name=exchange.account_name,
            poe_session_id="",
            status="oauth_connected",
        )
        session = create_session(self.settings, account_name=exchange.account_name)
        location = f"{self.settings.poe_account_frontend_complete_uri}?status=success"
        cookie = _session_set_cookie(
            self.settings.auth_cookie_name,
            str(session.get("session_id") or ""),
            secure=self.settings.auth_cookie_secure,
        )
        return Response(
            status=302, headers={"Location": location, "Set-Cookie": cookie}, body=b""
        )

    def _auth_session(self, context: Mapping[str, object]) -> Response:
        if str(context.get("method") or "") == "POST":
            return self._auth_session_bootstrap(context)
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

    def _auth_session_bootstrap(self, context: Mapping[str, object]) -> Response:
        cors = _cors_from_context(context)
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
        poe_session_id = next(
            (
                value
                for key in ("poeSessionId", "poeSESSID", "POESESSID", "poesessid")
                for value in [body.get(key)]
                if isinstance(value, str) and value.strip()
            ),
            None,
        )
        if not isinstance(poe_session_id, str) or not poe_session_id.strip():
            raise ApiError(
                status=400,
                code="invalid_input",
                message="poeSessionId is required",
                headers=cors,
            )
        try:
            account_name = resolve_account_name(
                self.settings,
                poe_session_id=poe_session_id,
            )
        except AccountResolutionError as exc:
            raise ApiError(
                status=exc.status,
                code=exc.code,
                message=str(exc),
                headers=cors,
            ) from None
        except ValueError as exc:
            raise ApiError(
                status=400,
                code="invalid_input",
                message=str(exc),
                headers=cors,
            ) from None
        _ = save_credential_state(
            self.settings,
            account_name=account_name,
            poe_session_id=poe_session_id,
            status="bootstrap_connected",
        )
        session = create_session(self.settings, account_name=account_name)
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

    def _auth_logout(self, context: Mapping[str, object]) -> Response:
        session_id = _session_cookie_from_headers(
            _headers_from_context(context),
            cookie_name=self.settings.auth_cookie_name,
        )
        clear_session(self.settings, session_id=session_id)
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

    def _ml_rollout(self, context: Mapping[str, object]) -> Response:
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

        method = str(context.get("method") or "GET")
        if method == "GET":
            try:
                return json_response(fetch_rollout_controls(self.client, league=league))
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
            payload = update_rollout_controls(
                self.client,
                league=league,
                request_payload=body,
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
