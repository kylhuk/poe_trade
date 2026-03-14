from __future__ import annotations

import hmac


def parse_bearer_token(header_value: str | None) -> str | None:
    if not header_value:
        return None
    prefix = "Bearer "
    if not header_value.startswith(prefix):
        return None
    token = header_value[len(prefix) :].strip()
    return token or None


def validate_bearer_token(header_value: str | None, expected_token: str) -> bool:
    provided = parse_bearer_token(header_value)
    if provided is None:
        return False
    return hmac.compare_digest(provided, expected_token)


def cors_headers(origin: str, allowed_methods: tuple[str, ...]) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Vary": "Origin",
        "Access-Control-Allow-Methods": ", ".join(allowed_methods),
        "Access-Control-Allow-Headers": "Authorization, Content-Type",
    }
