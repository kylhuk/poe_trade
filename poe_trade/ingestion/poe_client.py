"""Minimal PoE HTTP client with retry/backoff handling."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .rate_limit import AdaptiveRateLimiter, RateLimitPolicy, glean_rate_limit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoeResponse:
    payload: Any
    headers: dict[str, str]
    status_code: int
    attempts: int
    duration_ms: float


@dataclass
class RateLimitState:
    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    limiter: AdaptiveRateLimiter = field(default_factory=AdaptiveRateLimiter)

    def update(self, headers: Mapping[str, str]) -> None:
        stats = glean_rate_limit(headers)
        self.limit = stats.get("x-rate-limit-limit")
        self.remaining = stats.get("x-rate-limit-remaining")
        self.reset = stats.get("x-rate-limit-reset")
        self.limiter.update(headers)

    def next_delay(self) -> float:
        return self.limiter.next_delay()

    def mark_request(self) -> None:
        self.limiter.mark_request()

    def apply_retry_after(self, delay_seconds: float) -> None:
        self.limiter.apply_retry_after(delay_seconds)


@dataclass
class PoeClient:
    base_url: str
    policy: RateLimitPolicy
    user_agent: str
    timeout: float
    _bearer_token: str | None = field(default=None, init=False)
    _state: RateLimitState = field(default_factory=RateLimitState, init=False)
    _last_attempts: int = field(default=0, init=False)

    def set_bearer_token(self, token: str | None) -> None:
        self._bearer_token = token

    @property
    def rate_state(self) -> RateLimitState:
        return self._state

    @property
    def last_attempts(self) -> int:
        return self._last_attempts

    def request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        data: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return self.request_with_metadata(method, path, params=params, data=data, headers=headers).payload

    def request_with_metadata(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        data: Any | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> PoeResponse:
        return self._execute_request(method, path, params, data, headers)

    def _execute_request(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None,
        data: Any | None,
        headers: Mapping[str, str] | None,
    ) -> PoeResponse:
        url = self._build_url(path, params)
        attempts = self.policy.max_retries + 1
        self._last_attempts = 0
        start = time.monotonic()
        for attempt in range(attempts):
            self._last_attempts = attempt + 1
            if attempt == 0:
                pacing_delay = self._state.next_delay()
                if pacing_delay > 0:
                    logger.info(
                        "PoE client pacing wait %.2fs from rate-limit headers",
                        pacing_delay,
                    )
                    time.sleep(pacing_delay)
                self._state.mark_request()
            request_headers = self._build_headers(headers)
            payload = self._prepare_body(data, request_headers)
            req = urllib.request.Request(
                url,
                data=payload,
                headers=request_headers,
                method=method.upper(),
            )
            try:
                logger.debug(
                    "PoE client request %s %s attempt=%s", method, url, attempt
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8")
                    response_headers = {k: v for k, v in resp.getheaders()}
                    self._state.update(response_headers)
                    duration_ms = (time.monotonic() - start) * 1000.0
                    return PoeResponse(
                        payload=self._parse_body(raw),
                        headers=response_headers,
                        status_code=resp.getcode(),
                        attempts=self._last_attempts,
                        duration_ms=duration_ms,
                    )
            except urllib.error.HTTPError as exc:
                response_headers = {k: v for k, v in exc.headers.items()}
                self._state.update(response_headers)
                if exc.code == 429 and attempt < attempts - 1:
                    delay = self.policy.next_backoff(attempt, response_headers)
                    self._state.apply_retry_after(delay)
                    dynamic_delay = self._state.next_delay()
                    if dynamic_delay > delay:
                        delay = dynamic_delay
                    logger.warning(
                        "PoE rate limited (attempt=%s) waiting %.1fs", attempt, delay
                    )
                    time.sleep(delay)
                    continue
                body = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(
                    "PoE client error %s: %s" % (exc.code, body)
                ) from exc
            except urllib.error.URLError as exc:
                logger.warning("PoE client url error on attempt %s: %s", attempt, exc)
                if attempt < attempts - 1:
                    delay = self.policy.next_backoff(attempt, {})
                    time.sleep(delay)
                    continue
                raise
        raise RuntimeError("PoE client exhausted retries")

    def _build_url(
        self,
        path: str,
        params: Mapping[str, str] | None,
    ) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            base = path
        else:
            base = f"{self.base_url.rstrip('/')}/{path.lstrip('/') if path else ''}"
        if not params:
            return base
        encoded = urllib.parse.urlencode(params)
        connector = "&" if "?" in base else "?"
        return f"{base}{connector}{encoded}"

    def _build_headers(
        self,
        base_headers: Mapping[str, str] | None,
    ) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        if base_headers:
            headers.update(base_headers)
        return headers

    def _prepare_body(self, data: Any | None, headers: dict[str, str]) -> bytes | None:
        if data is None:
            return None
        if isinstance(data, str):
            headers.setdefault("Content-Type", "application/json")
            return data.encode("utf-8")
        if isinstance(data, bytes):
            headers.setdefault("Content-Type", "application/octet-stream")
            return data
        if isinstance(data, Mapping):
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            return urllib.parse.urlencode(data).encode("utf-8")
        raise ValueError("Unsupported request body type")

    def _parse_body(self, body: str) -> Any:
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body
