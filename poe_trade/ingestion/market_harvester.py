"""Public stash harvester logic."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from ..db import ClickHouseClient
from .checkpoints import CheckpointStore
from .poe_client import PoeClient
from .rate_limit import glean_rate_limit, parse_retry_after
from .stash_scribe import OAuthClient, OAuthToken
from .status import StatusReporter

logger = logging.getLogger(__name__)


_CHECKPOINT_LAG_THRESHOLD_SECONDS = 20.0
_DIVINES_ESTIMATE_BASE = 0.5
_DIVINES_PENALTY_PER_SECOND = 0.01


class MarketHarvester:
    def __init__(
        self,
        client: PoeClient,
        ck_client: ClickHouseClient,
        checkpoint_store: CheckpointStore,
        status_reporter: StatusReporter,
        auth_client: OAuthClient | None = None,
        service_name: str = "market_harvester",
    ) -> None:
        self._client = client
        self._auth_client = auth_client
        self._clickhouse = ck_client
        self._checkpoints = checkpoint_store
        self._status = status_reporter
        self._token: OAuthToken | None = None
        self._error_counts: dict[str, int] = {}
        self._stalled_since: dict[str, datetime] = {}
        self._paused_until: dict[str, datetime] = {}
        self._lock = threading.Lock()
        self._service_name = service_name

    def run(
        self,
        realms: Iterable[str],
        leagues: Iterable[str],
        interval: float,
        dry_run: bool,
        once: bool,
    ) -> None:
        realms = tuple(realms)
        leagues = tuple(leagues)
        logger.info(
            "MarketHarvester starting realms=%s leagues=%s dry_run=%s",
            realms,
            leagues,
            dry_run,
        )
        stop_event = threading.Event()
        try:
            while not stop_event.is_set():
                for realm in realms:
                    for league in leagues:
                        self._harvest(realm, league, dry_run)
                if once:
                    return
                stop_event.wait(interval)
        except KeyboardInterrupt:
            logger.info("MarketHarvester interrupted")

    def _harvest(self, realm: str, league: str, dry_run: bool) -> None:
        key = f"{realm}:{league}"
        start = time.monotonic()
        cursor = self._checkpoints.read(key)
        next_change_id: str | None = None
        status_text = "success"
        error_msg: str | None = None
        now = datetime.now(timezone.utc)
        response_status = 0
        response_ms = 0.0
        public_attempts: int | None = None
        metadata_rows: list[dict[str, Any]] = []
        checkpoint_lag_seconds: float | None = None

        paused_until = self._active_pause_until(key, now)
        if paused_until is not None:
            status_text = "rate_limited"
            error_msg = (
                "rate_limited: polling paused until "
                f"{paused_until.astimezone(timezone.utc).isoformat()}"
            )
            self._status.report(
                league=league,
                realm=realm,
                cursor=cursor,
                next_change_id=next_change_id,
                last_ingest_at=now,
                request_rate=0.0,
                status=status_text,
                error=error_msg,
                error_count=self._error_counts.get(key, 0),
                stalled_since=self._stalled_since.get(key),
            )
            if not dry_run:
                self._write_checkpoint_entry(
                    realm=realm,
                    league=league,
                    endpoint="public-stash-tabs",
                    last_cursor=cursor,
                    next_cursor=next_change_id,
                    retrieved_at=now,
                    status=status_text,
                    error=error_msg,
                    http_status=429,
                    response_ms=0.0,
                    attempts=0,
                )
            return

        try:
            self._ensure_token()
            params: dict[str, str] = {"league": league}
            if realm:
                params["realm"] = realm
            if cursor:
                params["id"] = cursor
            response = self._client.request_with_metadata(
                "GET", "public-stash-tabs", params=params
            )
            response_status = response.status_code
            response_ms = response.duration_ms
            public_attempts = response.attempts
            if response_status == 429:
                retry_after = self._pause_after_rate_limit(key, response.headers, now)
                status_text = "rate_limited"
                error_msg = f"rate_limited: retry_after_seconds={retry_after:.1f}"
                if not dry_run:
                    self._write_request_entry(
                        realm=realm,
                        league=league,
                        endpoint="public-stash-tabs",
                        http_method="GET",
                        requested_at=now,
                        status=429,
                        attempts=public_attempts,
                        response_ms=response_ms,
                        headers=response.headers,
                        error=error_msg,
                    )
                return
            payload = response.payload
            if isinstance(payload, dict):
                next_change_id, stashes = self._validate_payload(payload, key)
                if cursor and next_change_id == cursor:
                    logger.warning(
                        "Stale cursor for %s: %s matches checkpoint, skipping emit",
                        key,
                        next_change_id,
                    )
                    status_text = "stale cursor"
                else:
                    rows = self._rows_from_payload(
                        stashes=stashes,
                        realm=realm,
                        league=league,
                        cursor=cursor,
                        next_change_id=next_change_id,
                    )
                    if rows and not dry_run:
                        self._write(rows)
                    if next_change_id and not dry_run:
                        self._checkpoints.write(key, next_change_id)
                    metadata_identifier = self._trade_metadata_identifier_from_payload(
                        payload
                    )
                    if metadata_identifier and not dry_run:
                        metadata_rows = self._fetch_trade_metadata(
                            cursor=metadata_identifier,
                            realm=realm,
                            league=league,
                            retrieved_at=now,
                        )
                    elif not metadata_identifier and not dry_run:
                        # TODO: re-enable deterministic metadata fetch once the
                        # public-stash payload exposes a concrete trade-data
                        # identifier in `payload` instead of reusing stash cursors.
                        logger.info(
                            "Skipping trade metadata fetch for %s/%s: no trade-data identifier available",
                            realm,
                            league,
                        )
            else:
                logger.warning("Unexpected payload from PoE: %s", payload)
                status_text = "unexpected payload"
        except Exception as exc:  # pragma: no cover - best effort
            status_code = self._extract_http_status(exc)
            if status_code == 429:
                response_status = 429
                retry_after = self._pause_after_rate_limit(key, {}, now)
                status_text = "rate_limited"
                error_msg = (
                    f"rate_limited: retry_after_seconds={retry_after:.1f}; {exc}"
                )
                if not dry_run:
                    self._write_request_entry(
                        realm=realm,
                        league=league,
                        endpoint="public-stash-tabs",
                        http_method="GET",
                        requested_at=now,
                        status=429,
                        attempts=self._client.last_attempts,
                        response_ms=response_ms,
                        headers={},
                        error=str(exc),
                    )
            else:
                error_msg = str(exc)
                status_text = "error"
            with self._lock:
                self._error_counts[key] = self._error_counts.get(key, 0) + 1
                self._stalled_since.setdefault(key, now)
            logger.exception("MarketHarvester failed for %s", key)
        else:
            with self._lock:
                self._error_counts[key] = 0
                self._stalled_since.pop(key, None)
        finally:
            duration = time.monotonic() - start
            rate = 1.0 / max(duration, 1e-3)
            self._status.report(
                league=league,
                realm=realm,
                cursor=cursor,
                next_change_id=next_change_id,
                last_ingest_at=now,
                request_rate=rate,
                status=status_text,
                error=error_msg,
                error_count=self._error_counts.get(key, 0),
                stalled_since=self._stalled_since.get(key),
            )
            if not dry_run:
                checkpoint_lag_seconds = self._checkpoint_lag_seconds(key)
                self._write_checkpoint_entry(
                    realm=realm,
                    league=league,
                    endpoint="public-stash-tabs",
                    last_cursor=cursor,
                    next_cursor=next_change_id,
                    retrieved_at=now,
                    status=status_text,
                    error=error_msg,
                    http_status=response_status,
                    response_ms=response_ms,
                    attempts=public_attempts,
                )
                if metadata_rows:
                    self._write_trade_metadata(metadata_rows)
                self._maybe_log_checkpoint_lag(key, checkpoint_lag_seconds)

    def _ensure_token(self) -> None:
        if not self._auth_client:
            return
        if self._token is None or self._token.is_expired():
            self._token = self._auth_client.refresh()
            self._client.set_bearer_token(self._token.access_token)

    def _validate_payload(
        self, payload: dict[str, Any], key: str
    ) -> tuple[str, list[dict[str, Any]]]:
        next_change_id = payload.get("next_change_id")
        if not isinstance(next_change_id, str) or not next_change_id:
            raise ValueError(f"next_change_id missing or empty for {key}")
        stashes = payload.get("stashes")
        if not isinstance(stashes, list):
            raise ValueError(f"stashes list missing for {key}")
        return next_change_id, stashes

    def _trade_metadata_identifier_from_payload(
        self, payload: Mapping[str, Any]
    ) -> str | None:
        identifier = payload.get("trade_data_id") or payload.get("trade_data_identifier")
        if isinstance(identifier, str) and identifier:
            return identifier
        return None

    def _fetch_trade_metadata(
        self,
        cursor: str,
        realm: str,
        league: str,
        retrieved_at: datetime,
    ) -> list[dict[str, Any]]:
        try:
            response = self._client.request_with_metadata(
                "GET", f"api/trade/data/{cursor}"
            )
        except Exception as exc:  # pragma: no cover - best effort
            status_code = self._extract_http_status(exc)
            if status_code == 429:
                retry_after = self._pause_after_rate_limit(
                    f"{realm}:{league}", {}, retrieved_at
                )
                self._write_request_entry(
                    realm=realm,
                    league=league,
                    endpoint=f"api/trade/data/{cursor}",
                    http_method="GET",
                    requested_at=retrieved_at,
                    status=429,
                    attempts=self._client.last_attempts,
                    response_ms=0.0,
                    headers={},
                    error=(
                        "rate_limited: retry_after_seconds="
                        f"{retry_after:.1f} while fetching trade metadata"
                    ),
                )
            logger.warning("Failed to fetch trade metadata for %s/%s", realm, cursor)
            return []
        if response.status_code == 429:
            retry_after = self._pause_after_rate_limit(
                f"{realm}:{league}", response.headers, retrieved_at
            )
            self._write_request_entry(
                realm=realm,
                league=league,
                endpoint=f"api/trade/data/{cursor}",
                http_method="GET",
                requested_at=retrieved_at,
                status=429,
                attempts=response.attempts,
                response_ms=response.duration_ms,
                headers=response.headers,
                error=f"rate_limited: retry_after_seconds={retry_after:.1f}",
            )
            logger.warning(
                "Trade metadata request rate-limited for %s/%s", realm, cursor
            )
            return []
        payload = response.payload
        if not isinstance(payload, dict):
            logger.warning(
                "Trade metadata payload missing result for %s/%s: %s",
                realm,
                cursor,
                payload,
            )
            return []
        return self._rows_from_trade_metadata_payload(
            payload,
            realm,
            league,
            cursor,
            retrieved_at,
            response.headers,
            response.status_code,
        )

    def _rows_from_trade_metadata_payload(
        self,
        payload: dict[str, Any],
        realm: str,
        league: str,
        cursor: str,
        retrieved_at: datetime,
        headers: Mapping[str, str],
        http_status: int,
    ) -> list[dict[str, Any]]:
        results = payload.get("result") or payload.get("entries") or []
        rows: list[dict[str, Any]] = []
        rate_limit_raw = json.dumps(headers, ensure_ascii=False, sort_keys=True)
        rate_limit_parsed = json.dumps(
            glean_rate_limit(headers), ensure_ascii=False, sort_keys=True
        )
        for entry in results:
            trade = entry.get("trade") or {}
            listing = entry.get("listing") or {}
            item = entry.get("item") or {}
            trade_id = str(
                entry.get("trade_id")
                or trade.get("id")
                or listing.get("id")
                or entry.get("id")
                or ""
            )
            item_id = str(
                entry.get("item_id") or item.get("id") or listing.get("item_id") or ""
            )
            listing_ts = self._parse_timestamp(
                entry.get("listing_ts")
                or listing.get("indexed")
                or listing.get("listed_at")
                or trade.get("indexed")
                or trade.get("listed_at")
            )
            delist_ts = self._parse_timestamp(
                entry.get("delist_ts")
                or listing.get("delisted_at")
                or listing.get("delist_at")
                or entry.get("delist_at")
            )
            trade_data_hash = hashlib.sha256(
                json.dumps(entry, sort_keys=True).encode("utf-8")
            ).hexdigest()
            row: dict[str, Any] = {
                "retrieved_at": self._format_ts(retrieved_at),
                "service": self._service_name,
                "realm": realm,
                "league": league,
                "cursor": cursor,
                "trade_id": trade_id,
                "item_id": item_id,
                "listing_ts": self._format_ts(listing_ts) if listing_ts else None,
                "delist_ts": self._format_ts(delist_ts) if delist_ts else None,
                "trade_data_hash": trade_data_hash,
                "rate_limit_raw": rate_limit_raw,
                "rate_limit_parsed": rate_limit_parsed,
                "http_status": http_status,
                "payload_json": json.dumps(entry, ensure_ascii=False),
            }
            rows.append(row)
        return rows

    def _rows_from_payload(
        self,
        stashes: list[dict[str, Any]],
        realm: str,
        league: str,
        cursor: str | None,
        next_change_id: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        seen_stash_ids: set[str] = set()
        for stash in stashes:
            stash_id_value = stash.get("id") or stash.get("stash_id")
            stash_id = str(stash_id_value) if stash_id_value is not None else ""
            if stash_id:
                if stash_id in seen_stash_ids:
                    continue
                seen_stash_ids.add(stash_id)
            rows.append(
                {
                    "ingested_at": now,
                    "realm": realm,
                    "league": league,
                    "stash_id": stash_id,
                    "checkpoint": cursor or "",
                    "next_change_id": next_change_id,
                    "payload_json": json.dumps(stash, ensure_ascii=False),
                }
            )
        return rows

    def _write(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        query = (
            "INSERT INTO poe_trade.raw_public_stash_pages "
            "(ingested_at, realm, league, stash_id, checkpoint, next_change_id, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)

    def _write_checkpoint_entry(
        self,
        realm: str,
        league: str,
        endpoint: str,
        last_cursor: str | None,
        next_cursor: str | None,
        retrieved_at: datetime,
        status: str,
        error: str | None,
        http_status: int,
        response_ms: float,
        attempts: int | None = None,
    ) -> None:
        attempt_count = attempts if attempts is not None else self._client.last_attempts
        retry_count = max(0, attempt_count - 1)
        cursor_source = next_cursor or last_cursor or ""
        cursor_hash = hashlib.sha256(cursor_source.encode("utf-8")).hexdigest()
        row = {
            "service": self._service_name,
            "realm": realm,
            "league": league,
            "endpoint": endpoint,
            "last_cursor_id": last_cursor or "",
            "next_cursor_id": next_cursor or "",
            "cursor_hash": cursor_hash,
            "retrieved_at": self._format_ts(retrieved_at),
            "retry_count": retry_count,
            "status": status,
            "error": error or "",
            "http_status": int(http_status or 0),
            "response_ms": int(response_ms),
        }
        payload = json.dumps(row, ensure_ascii=False)
        query = (
            "INSERT INTO poe_trade.bronze_ingest_checkpoints "
            "(service, realm, league, endpoint, last_cursor_id, next_cursor_id, cursor_hash, retrieved_at, retry_count, status, error, http_status, response_ms)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)

    def _write_trade_metadata(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        query = (
            "INSERT INTO poe_trade.bronze_trade_metadata "
            "(retrieved_at, service, realm, league, cursor, trade_id, item_id, listing_ts, delist_ts, trade_data_hash, rate_limit_raw, rate_limit_parsed, http_status, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)

    def _write_request_entry(
        self,
        realm: str,
        league: str,
        endpoint: str,
        http_method: str,
        requested_at: datetime,
        status: int,
        attempts: int | None,
        response_ms: float,
        headers: Mapping[str, str],
        error: str | None,
    ) -> None:
        retry_after_seconds = parse_retry_after(headers)
        row = {
            "requested_at": self._format_ts(requested_at),
            "service": self._service_name,
            "realm": realm,
            "league": league,
            "endpoint": endpoint,
            "http_method": http_method,
            "status": int(status),
            "attempts": int(max(0, attempts or 0)),
            "response_ms": int(max(0.0, response_ms)),
            "rate_limit_raw": json.dumps(
                dict(headers), ensure_ascii=False, sort_keys=True
            ),
            "rate_limit_parsed": json.dumps(
                glean_rate_limit(headers), ensure_ascii=False, sort_keys=True
            ),
            "retry_after_seconds": retry_after_seconds,
            "error": error or "",
        }
        payload = json.dumps(row, ensure_ascii=False)
        query = (
            "INSERT INTO poe_trade.bronze_requests "
            "(requested_at, service, realm, league, endpoint, http_method, status, attempts, response_ms, rate_limit_raw, rate_limit_parsed, retry_after_seconds, error)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)

    def _active_pause_until(self, key: str, now: datetime) -> datetime | None:
        with self._lock:
            paused_until = self._paused_until.get(key)
            if paused_until is None:
                return None
            if paused_until <= now:
                self._paused_until.pop(key, None)
                return None
            return paused_until

    def _pause_after_rate_limit(
        self, key: str, headers: Mapping[str, str], now: datetime
    ) -> float:
        retry_after = parse_retry_after(headers)
        pause_seconds = retry_after if retry_after is not None else 60.0
        pause_until = now + timedelta(seconds=max(0.0, pause_seconds))
        with self._lock:
            existing = self._paused_until.get(key)
            if existing is None or pause_until > existing:
                self._paused_until[key] = pause_until
        return float(max(0.0, pause_seconds))

    @staticmethod
    def _extract_http_status(exc: Exception) -> int | None:
        match = re.search(r"PoE client error\s+(\d{3})", str(exc))
        if not match:
            return None
        return int(match.group(1))

    def _maybe_log_checkpoint_lag(
        self, key: str, lag_seconds: float | None = None
    ) -> None:
        actual_lag = (
            lag_seconds
            if lag_seconds is not None
            else self._checkpoint_lag_seconds(key)
        )
        if actual_lag is None or actual_lag <= _CHECKPOINT_LAG_THRESHOLD_SECONDS:
            return
        estimate = self._divines_per_attention_minute_estimate(actual_lag)
        logger.warning(
            "checkpoint lag risk for %s checkpoint_lag_seconds=%.1f divines_per_attention_minute_estimate=%.3f",
            key,
            actual_lag,
            estimate,
        )

    def _checkpoint_lag_seconds(self, key: str) -> float | None:
        checkpoint_path = self._checkpoints.path(key)
        if not checkpoint_path.exists():
            return None
        try:
            modified = checkpoint_path.stat().st_mtime
        except OSError:
            return None
        now = datetime.now(timezone.utc)
        last_modified = datetime.fromtimestamp(modified, timezone.utc)
        return max(0.0, (now - last_modified).total_seconds())

    def _divines_per_attention_minute_estimate(self, lag_seconds: float) -> float:
        # Derived from docs/v2-implementation-plan Confidence scoring heuristics until a trained model ships.
        penalty = min(_DIVINES_ESTIMATE_BASE, lag_seconds * _DIVINES_PENALTY_PER_SECOND)
        return max(0.0, _DIVINES_ESTIMATE_BASE - penalty)

    @staticmethod
    def _format_ts(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _parse_timestamp(self, value: Any | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(value, timezone.utc)
            except (OSError, ValueError):
                return None
        if isinstance(value, str):
            candidate = value.strip()
            if (
                candidate.endswith("Z")
                and "+" not in candidate
                and "-" not in candidate[-6:]
            ):
                candidate = candidate[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(candidate)
            except ValueError:
                try:
                    parsed = datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    return None
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        return None
