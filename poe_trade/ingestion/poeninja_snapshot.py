"""PoE.ninja currency overview scheduler."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Sequence

LOGGER = logging.getLogger(__name__)
Clock = Callable[[], float]
Sleeper = Callable[[float], None]
Opener = Callable[[str, float], object]


@dataclass(frozen=True)
class PoeNinjaResponse:
    status_code: int
    payload: dict[str, Any] | None
    stale: bool = False
    reason: str | None = None
    cache_age: float | None = None


@dataclass(frozen=True)
class _CacheEntry:
    payload: dict[str, Any]
    status_code: int
    timestamp: float


class PoeNinjaClient:
    """Simple HTTP client for poe.ninja currency overview."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 10.0,
        cache_ttl: float = 180.0,
        clock: Clock | None = None,
        opener: Opener | None = None,
    ) -> None:
        self._base_url = base_url or "https://poe.ninja/api/data/currencyoverview"
        self._timeout = timeout
        self._clock = clock or time.monotonic
        self._opener = opener or urllib.request.urlopen
        self._cache_ttl = min(max(cache_ttl, 0.0), 180.0)
        self._cache: dict[str, _CacheEntry] = {}

    def fetch_currency_overview(self, league: str) -> PoeNinjaResponse:
        query = urllib.parse.urlencode({"league": league, "type": "Currency"})
        url = f"{self._base_url}?{query}"
        now = self._clock()
        payload: dict[str, Any] | None = None
        status = 0
        try:
            with self._opener(url, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8")
                payload = self._parse_payload(raw)
                status = resp.getcode()
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            LOGGER.debug(
                "poe.ninja request failed league=%s status=%s", league, exc.code
            )
            status = exc.code
        except urllib.error.URLError as exc:  # pragma: no cover - network
            LOGGER.debug("poe.ninja request failed league=%s error=%s", league, exc)
        except ValueError:  # pragma: no cover - parse
            LOGGER.debug("poe.ninja league=%s returned invalid JSON", league)

        success = 200 <= status < 300
        is_empty = success and self._is_empty_payload(payload)
        if success and not is_empty and payload is not None:
            self._cache[league] = _CacheEntry(
                payload=payload, status_code=status, timestamp=now
            )
            return PoeNinjaResponse(status_code=status, payload=payload)

        fallback_reason = self._determine_reason(status, success, is_empty)
        if fallback_reason:
            return self._fallback_response(league, status, fallback_reason, now)
        return PoeNinjaResponse(status_code=status, payload=payload)

    def _fallback_response(
        self, league: str, status: int, reason: str, now: float
    ) -> PoeNinjaResponse:
        entry = self._cache.get(league)
        cache_hit = False
        cache_age = 0.0
        cached_payload: dict[str, Any] | None = None
        if entry is not None:
            cache_age = max(0.0, now - entry.timestamp)
            if cache_age <= self._cache_ttl:
                cache_hit = True
                cached_payload = entry.payload

        LOGGER.info(
            "poe.ninja league=%s fallback reason=%s cache_hit=%s cache_age=%.1fs",
            league,
            reason,
            cache_hit,
            cache_age,
        )

        if cache_hit and cached_payload is not None:
            return PoeNinjaResponse(
                status_code=status,
                payload=cached_payload,
                stale=True,
                reason=reason,
                cache_age=cache_age,
            )
        return PoeNinjaResponse(
            status_code=status,
            payload=None,
            stale=False,
            reason=reason,
            cache_age=cache_age,
        )

    @staticmethod
    def _is_empty_payload(payload: dict[str, Any] | None) -> bool:
        if not payload:
            return True
        lines = payload.get("lines")
        if lines is None:
            return False
        if isinstance(lines, list) and not lines:
            return True
        return False

    @staticmethod
    def _determine_reason(
        status: int, success: bool, is_empty: bool
    ) -> str | None:
        if status == 404:
            return "http_404"
        if status == 429:
            return "http_429"
        if success and is_empty:
            return "empty"
        return None

    @staticmethod
    def _parse_payload(raw: str) -> dict[str, Any] | None:
        if not raw:
            return None
        return json.loads(raw)


@dataclass
class _LeagueState:
    next_run: float
    backoff_multiplier: float = 1.0


class PoeNinjaSnapshotScheduler:
    """Scheduler that enforces cadence and pacing for poe.ninja pulls."""

    def __init__(
        self,
        client: PoeNinjaClient,
        leagues: Sequence[str],
        *,
        per_league_interval: float = 60.0,
        global_interval: float = 1.0,
        backoff_cap: float = 300.0,
        clock: Clock | None = None,
        sleep: Sleeper | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._client = client
        unique_leagues = tuple(dict.fromkeys([league for league in leagues if league]))
        self._leagues = unique_leagues
        self._interval = max(per_league_interval, 0.1)
        self._global_interval = max(global_interval, 0.0)
        self._backoff_cap = max(backoff_cap, self._interval)
        self._max_multiplier = max(1.0, self._backoff_cap / self._interval)
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._logger = logger or LOGGER
        self._last_request_at: float | None = None
        now = self._clock()
        self._states: dict[str, _LeagueState] = {
            league: _LeagueState(next_run=now) for league in self._leagues
        }

    @property
    def league_states(self) -> dict[str, _LeagueState]:
        return self._states

    def next_due(self) -> tuple[str, float]:
        now = self._clock()
        if not self._states:
            raise RuntimeError("no leagues configured")
        league, state = min(self._states.items(), key=lambda kv: kv[1].next_run)
        wait = max(0.0, state.next_run - now)
        return league, wait

    def run(self, *, once: bool = False, dry_run: bool = False) -> None:
        if not self._states:
            self._logger.warning("poe.ninja scheduler has no leagues configured")
            return
        if dry_run:
            self._logger.info("poe.ninja dry run: skipping persistence")
        if once:
            for league in self._leagues:
                self._ensure_global_pacing()
                response = self._client.fetch_currency_overview(league)
                now = self._clock()
                self._last_request_at = now
                self.record_response(league, response, now=now)
            return
        while True:
            league, wait = self.next_due()
            if wait > 0:
                self._sleep(wait)
                continue
            self._ensure_global_pacing()
            response = self._client.fetch_currency_overview(league)
            now = self._clock()
            self._last_request_at = now
            self.record_response(league, response, now=now)

    def record_response(
        self,
        league: str,
        response: PoeNinjaResponse,
        *,
        now: float | None = None,
    ) -> float:
        timestamp = now if now is not None else self._clock()
        state = self._states[league]
        success = 200 <= response.status_code < 300
        is_empty = success and self._is_empty_payload(response.payload)
        reason = self._determine_reason(response, success, is_empty)
        if response.status_code == 429 or is_empty:
            state.backoff_multiplier = min(
                state.backoff_multiplier * 2,
                self._max_multiplier,
            )
            delay = min(
                self._backoff_cap,
                self._interval * state.backoff_multiplier,
            )
            status = "backoff"
        else:
            state.backoff_multiplier = 1.0
            delay = self._interval
            status = "success" if success else "error"
        state.next_run = timestamp + delay
        self._logger.info(
            "poe.ninja league=%s status=%s reason=%s next_delay=%.1fs",
            league,
            status,
            reason,
            delay,
        )
        return delay

    def _ensure_global_pacing(self) -> float:
        if self._global_interval <= 0 or self._last_request_at is None:
            return 0.0
        now = self._clock()
        elapsed = now - self._last_request_at
        if elapsed >= self._global_interval:
            return 0.0
        delay = self._global_interval - elapsed
        self._sleep(delay)
        return delay

    @staticmethod
    def _is_empty_payload(payload: dict[str, Any] | None) -> bool:
        if not payload:
            return True
        lines = payload.get("lines")
        if lines is None:
            return False
        if isinstance(lines, list) and not lines:
            return True
        return False

    @staticmethod
    def _determine_reason(
        response: PoeNinjaResponse, success: bool, is_empty: bool
    ) -> str:
        if response.status_code == 429:
            return "429"
        if is_empty:
            return "empty"
        if not success:
            return f"status={response.status_code}"
        return "ok"
