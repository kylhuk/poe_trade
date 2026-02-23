"""Public stash harvester logic."""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any, Iterable

from ..db import ClickHouseClient
from .checkpoints import CheckpointStore
from .poe_client import PoeClient
from .stash_scribe import OAuthClient, OAuthToken
from .status import StatusReporter

logger = logging.getLogger(__name__)


class MarketHarvester:
    def __init__(
        self,
        client: PoeClient,
        ck_client: ClickHouseClient,
        checkpoint_store: CheckpointStore,
        status_reporter: StatusReporter,
        auth_client: OAuthClient | None = None,
    ) -> None:
        self._client = client
        self._auth_client = auth_client
        self._clickhouse = ck_client
        self._checkpoints = checkpoint_store
        self._status = status_reporter
        self._token: OAuthToken | None = None
        self._error_counts: dict[str, int] = {}
        self._stalled_since: dict[str, datetime] = {}
        self._lock = threading.Lock()

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
        try:
            self._ensure_token()
            params: dict[str, str] = {"league": league}
            if realm:
                params["realm"] = realm
            if cursor:
                params["id"] = cursor
            payload = self._client.request("GET", "public-stash-tabs", params=params)
            if isinstance(payload, dict):
                next_change_id = payload.get("next_change_id")
                rows = self._rows_from_payload(payload, realm, league, cursor)
                if rows and not dry_run:
                    self._write(rows)
                if next_change_id and not dry_run:
                    self._checkpoints.write(key, next_change_id)
            else:
                logger.warning("Unexpected payload from PoE: %s", payload)
                status_text = "unexpected payload"
        except Exception as exc:  # pragma: no cover - best effort
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

    def _ensure_token(self) -> None:
        if not self._auth_client:
            return
        if self._token is None or self._token.is_expired():
            self._token = self._auth_client.refresh()
            self._client.set_bearer_token(self._token.access_token)


    def _rows_from_payload(
        self,
        payload: dict[str, Any],
        realm: str,
        league: str,
        cursor: str | None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        next_change_id = payload.get("next_change_id")
        for stash in payload.get("stashes", []):
            stash_id = stash.get("id") or stash.get("stash_id") or ""
            rows.append(
                {
                    "ingested_at": now,
                    "realm": realm,
                    "league": league,
                    "stash_id": str(stash_id),
                    "checkpoint": cursor or "",
                    "next_change_id": next_change_id or "",
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
