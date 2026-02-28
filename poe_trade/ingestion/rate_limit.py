"""Rate limit helpers for PoE ingestion clients."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RateLimitPolicy:
    max_retries: int
    backoff_base: float
    backoff_max: float
    jitter: float

    def next_backoff(self, attempt: int, headers: Mapping[str, str]) -> float:
        retry = parse_retry_after(headers)
        if retry is not None:
            base = retry
            jitter = 0.0
            delay = max(0.0, retry)
        else:
            base = min(self.backoff_base * (2**attempt), self.backoff_max)
            if self.jitter > 0:
                jitter = random.uniform(-self.jitter, self.jitter)
            else:
                jitter = 0.0
            delay = max(0.0, base + jitter)
        logger.debug(
            "Computed rate-limit backoff (attempt=%s base=%s jitter=%s) -> %s",
            attempt,
            base,
            jitter,
            delay,
        )
        return delay


@dataclass(frozen=True)
class RateLimitWindow:
    rule: str
    limit: int
    period_seconds: int
    penalty_seconds: int
    used: int = 0
    restricted_seconds: int = 0

    @property
    def requests_per_second(self) -> float:
        return float(self.limit) / float(self.period_seconds)

    @property
    def minimum_interval(self) -> float:
        return float(self.period_seconds) / float(self.limit)


@dataclass
class AdaptiveRateLimiter:
    windows: tuple[RateLimitWindow, ...] = ()
    min_interval_seconds: float = 0.0
    restricted_until: float = 0.0
    last_request_at: float | None = None

    def update(self, headers: Mapping[str, str], now: float | None = None) -> None:
        parsed_windows = parse_rate_limit_windows(headers)
        if not parsed_windows:
            return
        self.windows = tuple(parsed_windows)
        self.min_interval_seconds = max(
            window.minimum_interval for window in self.windows
        )
        instant = now if now is not None else time.monotonic()
        restricted_seconds = max(
            (window.restricted_seconds for window in self.windows), default=0
        )
        if restricted_seconds > 0:
            self.restricted_until = max(
                self.restricted_until, instant + restricted_seconds
            )

    def next_delay(self, now: float | None = None) -> float:
        instant = now if now is not None else time.monotonic()
        delay = 0.0
        if self.restricted_until > instant:
            delay = self.restricted_until - instant
        if self.last_request_at is not None and self.min_interval_seconds > 0:
            interval_delay = (
                self.last_request_at + self.min_interval_seconds
            ) - instant
            if interval_delay > delay:
                delay = interval_delay
        return max(0.0, delay)

    def mark_request(self, now: float | None = None) -> None:
        self.last_request_at = now if now is not None else time.monotonic()

    def apply_retry_after(self, delay_seconds: float, now: float | None = None) -> None:
        if delay_seconds <= 0:
            return
        instant = now if now is not None else time.monotonic()
        self.restricted_until = max(self.restricted_until, instant + delay_seconds)


def _lower_keys(headers: Mapping[str, str]) -> Mapping[str, str]:
    return {key.lower(): value for key, value in headers.items()}


def _parse_triples(value: str | None) -> list[tuple[int, int, int]]:
    if not value:
        return []
    triples: list[tuple[int, int, int]] = []
    for chunk in value.split(","):
        parts = [part.strip() for part in chunk.split(":") if part.strip()]
        if len(parts) < 2:
            continue
        if len(parts) == 2:
            parts.append("0")
        try:
            first = int(parts[0])
            second = int(parts[1])
            third = int(parts[2])
        except ValueError:
            continue
        triples.append((first, second, third))
    return triples


def parse_rate_limit_windows(headers: Mapping[str, str]) -> list[RateLimitWindow]:
    normalized = _lower_keys(headers)
    rules = [
        rule.strip().lower()
        for rule in (normalized.get("x-rate-limit-rules") or "").split(",")
        if rule.strip()
    ]
    if not rules:
        rules = [
            rule
            for rule in ("client", "account", "ip")
            if normalized.get(f"x-rate-limit-{rule}")
        ]

    windows: list[RateLimitWindow] = []
    for rule in rules:
        limits = _parse_triples(normalized.get(f"x-rate-limit-{rule}"))
        if not limits:
            continue
        states = _parse_triples(normalized.get(f"x-rate-limit-{rule}-state"))
        state_by_period = {
            period: (used, restricted) for used, period, restricted in states
        }
        for index, (limit, period_seconds, penalty_seconds) in enumerate(limits):
            if limit <= 0 or period_seconds <= 0:
                continue
            used = 0
            restricted = 0
            if index < len(states) and states[index][1] == period_seconds:
                used = max(0, states[index][0])
                restricted = max(0, states[index][2])
            elif period_seconds in state_by_period:
                used, restricted = state_by_period[period_seconds]
                used = max(0, used)
                restricted = max(0, restricted)
            windows.append(
                RateLimitWindow(
                    rule=rule,
                    limit=limit,
                    period_seconds=period_seconds,
                    penalty_seconds=max(0, penalty_seconds),
                    used=used,
                    restricted_seconds=restricted,
                )
            )
    return windows


def parse_retry_after(headers: Mapping[str, str]) -> float | None:
    candidate = _lower_keys(headers).get("retry-after")
    if not candidate:
        return None
    candidate = candidate.strip()
    if not candidate:
        return None
    try:
        return float(candidate)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError, OverflowError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = (parsed - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, delta)


def glean_rate_limit(headers: Mapping[str, str]) -> dict[str, int | None]:
    normalized = _lower_keys(headers)
    result: dict[str, int | None] = {}
    for key in ("x-rate-limit-limit", "x-rate-limit-remaining", "x-rate-limit-reset"):
        value = normalized.get(key)
        if value is None:
            result[key] = None
            continue
        try:
            result[key] = int(value.split(",", 1)[0])
        except ValueError:
            result[key] = None
    if all(value is None for value in result.values()):
        windows = parse_rate_limit_windows(normalized)
        if windows:
            primary = next(
                (window for window in windows if window.rule == "client"), windows[0]
            )
            result["x-rate-limit-limit"] = primary.limit
            result["x-rate-limit-remaining"] = max(0, primary.limit - primary.used)
            result["x-rate-limit-reset"] = (
                primary.restricted_seconds
                if primary.restricted_seconds > 0
                else primary.period_seconds
            )
    return result
