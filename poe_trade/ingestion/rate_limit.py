"""Rate limit helpers for PoE ingestion clients."""

from __future__ import annotations

import logging
import random
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
            base = min(self.backoff_base * (2 ** attempt), self.backoff_max)
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


def _lower_keys(headers: Mapping[str, str]) -> Mapping[str, str]:
    return {key.lower(): value for key, value in headers.items()}


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
    return result
