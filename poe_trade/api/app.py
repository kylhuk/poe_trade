from __future__ import annotations

import json
from io import BufferedIOBase
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from collections.abc import Mapping
from typing import cast
from urllib.parse import parse_qs, urlparse

from poe_trade.config import settings as config_settings
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient

from .auth import cors_headers, parse_bearer_token, validate_bearer_token
from .ml import (
    BackendUnavailable,
    contract_payload,
    ensure_allowed_league,
    fetch_predict_one,
    fetch_status,
)
from .ops import (
    OpsBackendUnavailable,
    analytics_alerts,
    analytics_backtests,
    analytics_ingestion,
    analytics_ml,
    analytics_report,
    analytics_scanner,
    contract_payload as ops_contract_payload,
    dashboard_payload,
    messages_payload,
    price_check_payload,
    services_payload,
)
from .responses import ApiError, Response, json_error, json_response
from .routes import Router
from .stash import StashBackendUnavailable, fetch_stash_tabs
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
        self.router = Router()
        self._register_routes()

    def _register_routes(self) -> None:
        self.router.add("/healthz", ("GET",), self._healthz)
        self.router.add("/api/v1/ops/contract", ("GET", "OPTIONS"), self._ops_contract)
        self.router.add("/api/v1/ops/services", ("GET", "OPTIONS"), self._ops_services)
        self.router.add(
            "/api/v1/ops/dashboard", ("GET", "OPTIONS"), self._ops_dashboard
        )
        self.router.add("/api/v1/ops/messages", ("GET", "OPTIONS"), self._ops_messages)
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
            self._require_auth(headers, cors)

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
        headers: Mapping[str, str],
        cors_headers_for_error: Mapping[str, str],
    ) -> None:
        authorization = headers.get("Authorization")
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

    def _cors_headers(self, *, origin: str | None, path: str) -> dict[str, str]:
        if not origin or not _is_protected_path(path):
            return {}
        if origin not in self.settings.api_cors_origins:
            return {}
        return cors_headers(origin, ("GET", "POST", "OPTIONS"))

    def _healthz(self, _context: Mapping[str, object]) -> Response:
        return json_response({"status": "ok", "service": "api", "version": "v1"})

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

    def _ops_analytics(self, context: Mapping[str, object]) -> Response:
        kind = str(context.get("kind") or "")
        league = (
            self.settings.api_league_allowlist[0]
            if self.settings.api_league_allowlist
            else ""
        )
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
            ) from None
        except ServiceActionInvalidError:
            raise ApiError(
                status=400,
                code="service_action_invalid",
                message="invalid service action",
            ) from None
        except ServiceActionForbiddenError:
            raise ApiError(
                status=403,
                code="service_action_forbidden",
                message="service action is forbidden",
            ) from None
        except ServiceControlError:
            raise ApiError(
                status=503,
                code="service_action_failed",
                message="service action failed",
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
                message="stash feature is unavailable",
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
        try:
            return json_response(
                fetch_stash_tabs(self.client, league=league, realm=realm)
            )
        except StashBackendUnavailable:
            raise ApiError(
                status=503,
                code="backend_unavailable",
                message="backend unavailable",
            ) from None

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
            "/api/v1/stash/",
        )
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
