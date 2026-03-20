from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from poe_trade.config import constants
from poe_trade.db import ClickHouseClient

from .poe_client import PoeClient
from .status import StatusReporter
from .sync_contract import queue_key

logger = logging.getLogger(__name__)

_PRICE_NOTE_PATTERN = re.compile(
    r"^~(?:b/o|price)\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Za-z]+)$",
    re.IGNORECASE,
)


def stash_endpoint(realm: str, league: str, tab_id: str | None = None) -> str:
    normalized_realm = realm.strip().lower()
    prefix = "stash"
    if normalized_realm and normalized_realm != "pc":
        prefix = f"stash/{normalized_realm}"
    base = f"{prefix}/{league}"
    if tab_id:
        return f"{base}/{tab_id}"
    return base


class AccountStashHarvester:
    def __init__(
        self,
        client: PoeClient,
        clickhouse: ClickHouseClient,
        status: StatusReporter,
        *,
        service_name: str = "account_stash_harvester",
        account_name: str = "",
        request_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._client = client
        self._clickhouse = clickhouse
        self._status = status
        self._service_name = service_name
        self._account_name = account_name
        self._request_headers = dict(request_headers or {})

    def run(
        self,
        *,
        realm: str,
        league: str,
        interval: float,
        dry_run: bool,
        once: bool,
    ) -> None:
        while True:
            self._harvest(realm=realm, league=league, dry_run=dry_run)
            if once:
                return
            time.sleep(max(interval, 0.0))

    def _harvest(self, *, realm: str, league: str, dry_run: bool) -> None:
        key = queue_key(constants.FEED_KIND_ACCOUNT_STASH, realm)
        started = time.monotonic()
        captured = datetime.now(timezone.utc)
        status_text = "success"
        error_msg: str | None = None
        try:
            tabs_payload = self._client.request(
                "GET",
                stash_endpoint(realm, league),
                headers=self._request_headers,
            )
            tabs = _tab_rows_from_payload(tabs_payload)
            snapshots = self._fetch_tab_snapshots(realm=realm, league=league, tabs=tabs)
            if not dry_run:
                self._write_raw_snapshots(snapshots)
                self._write_flat_items(snapshots)
        except Exception as exc:
            status_text = "error"
            error_msg = str(exc)
            logger.exception(
                "Account stash harvest failed realm=%s league=%s", realm, league
            )
        finally:
            elapsed = time.monotonic() - started
            self._status.report(
                queue_key=key,
                feed_kind=constants.FEED_KIND_ACCOUNT_STASH,
                contract_version=constants.INGEST_CONTRACT_VERSION,
                league=league,
                realm=realm,
                cursor=None,
                next_change_id=None,
                last_ingest_at=captured,
                request_rate=0.0 if elapsed <= 0 else 1.0 / elapsed,
                status=status_text,
                error=error_msg,
                error_count=1 if error_msg else 0,
                stalled_since=captured if error_msg else None,
            )

    def _fetch_tab_snapshots(
        self,
        *,
        realm: str,
        league: str,
        tabs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        captured_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        for tab in tabs:
            tab_id = str(tab.get("id") or tab.get("tab_id") or "")
            if not tab_id:
                continue
            payload = self._client.request(
                "GET",
                stash_endpoint(realm, league, tab_id=tab_id),
                headers=self._request_headers,
            )
            snapshot_payload = {
                "tab": tab,
                "payload": payload,
            }
            rows.append(
                {
                    "snapshot_id": f"{self._service_name}:{realm}:{league}:{tab_id}:{captured_at}",
                    "captured_at": captured_at,
                    "realm": realm,
                    "league": league,
                    "account_name": self._account_name,
                    "tab_id": tab_id,
                    "next_change_id": str(payload.get("next_change_id") or ""),
                    "payload_json": json.dumps(snapshot_payload, ensure_ascii=False),
                }
            )
        return rows

    def _write_raw_snapshots(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        query = (
            "INSERT INTO poe_trade.raw_account_stash_snapshot "
            "(snapshot_id, captured_at, realm, league, account_name, tab_id, next_change_id, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)

    def _write_flat_items(self, rows: list[dict[str, Any]]) -> None:
        flat_rows: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row.get("payload_json") or "{}"))
            tab = payload.get("tab") if isinstance(payload.get("tab"), dict) else {}
            body = (
                payload.get("payload")
                if isinstance(payload.get("payload"), dict)
                else {}
            )
            raw_items = body.get("items")
            items = raw_items if isinstance(raw_items, list) else []
            tab_name = str(tab.get("n") or tab.get("name") or "")
            tab_type = str(tab.get("type") or "normal")
            for item in items:
                if not isinstance(item, dict):
                    continue
                listed = parse_listed_price(str(item.get("note") or ""))
                estimated = listed[0] if listed else 0.0
                currency = listed[1] if listed else "chaos"
                confidence = 80 if listed else 0
                flat_rows.append(
                    {
                        "observed_at": row.get("captured_at"),
                        "realm": row.get("realm"),
                        "league": row.get("league"),
                        "account_name": row.get("account_name"),
                        "tab_id": row.get("tab_id"),
                        "tab_name": tab_name,
                        "tab_type": tab_type,
                        "item_id": str(item.get("id") or ""),
                        "item_name": str(
                            item.get("name") or item.get("typeLine") or "Unknown"
                        ),
                        "item_class": str(item.get("itemClass") or "Unknown"),
                        "rarity": _rarity_from_frame_type(item.get("frameType")),
                        "x": int(item.get("x") or 0),
                        "y": int(item.get("y") or 0),
                        "w": int(item.get("w") or 1),
                        "h": int(item.get("h") or 1),
                        "listed_price": listed[0] if listed else None,
                        "estimated_price": estimated,
                        "estimated_price_confidence": confidence,
                        "currency": currency,
                        "icon_url": str(item.get("icon") or ""),
                        "payload_json": json.dumps(item, ensure_ascii=False),
                    }
                )
        if not flat_rows:
            return
        payload = "\n".join(json.dumps(row, ensure_ascii=False) for row in flat_rows)
        query = (
            "INSERT INTO poe_trade.silver_account_stash_items "
            "(observed_at, realm, league, account_name, tab_id, tab_name, tab_type, item_id, item_name, item_class, rarity, x, y, w, h, listed_price, estimated_price, estimated_price_confidence, currency, icon_url, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{payload}"
        )
        self._clickhouse.execute(query)


def _tab_rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        tabs = payload.get("tabs")
        if isinstance(tabs, list):
            return [row for row in tabs if isinstance(row, dict)]
    return []


def parse_listed_price(note: str) -> tuple[float, str] | None:
    match = _PRICE_NOTE_PATTERN.match(note.strip())
    if not match:
        return None
    return float(match.group(1)), match.group(2).lower()


def _rarity_from_frame_type(frame_type: Any) -> str:
    mapping = {
        0: "normal",
        1: "magic",
        2: "rare",
        3: "unique",
    }
    if isinstance(frame_type, int):
        return mapping.get(frame_type, "normal")
    return "normal"
