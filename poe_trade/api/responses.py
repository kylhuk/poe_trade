from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

JSON_CONTENT_TYPE = "application/json; charset=utf-8"


ERROR_CODES = {
    "route_not_found",
    "method_not_allowed",
    "auth_required",
    "auth_invalid",
    "origin_denied",
    "league_not_allowed",
    "invalid_json",
    "invalid_input",
    "request_too_large",
    "backend_unavailable",
    "feature_unavailable",
    "service_not_found",
    "service_action_invalid",
    "service_action_forbidden",
    "service_action_failed",
    "internal_error",
}


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


class ApiError(RuntimeError):
    def __init__(
        self,
        *,
        status: int,
        code: str,
        message: str,
        details: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers or {}


def json_response(
    payload: dict[str, Any],
    *,
    status: int = 200,
    headers: dict[str, str] | None = None,
) -> Response:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response_headers = {
        "Content-Type": JSON_CONTENT_TYPE,
        "Content-Length": str(len(body)),
    }
    if headers:
        response_headers.update(headers)
    return Response(status=status, headers=response_headers, body=body)


def json_error(
    *,
    status: int,
    code: str,
    message: str,
    details: object | None = None,
    headers: dict[str, str] | None = None,
) -> Response:
    if code not in ERROR_CODES:
        raise ValueError(f"unsupported error code {code!r}")
    return json_response(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
        status=status,
        headers=headers,
    )
