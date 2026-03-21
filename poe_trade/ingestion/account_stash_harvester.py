from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from poe_trade.config import constants
from poe_trade.db import ClickHouseClient
from poe_trade.stash_scan import (
    content_signature_for_item,
    lineage_key_for_item,
    normalize_stash_prediction,
)

from .poe_client import PoeClient
from .status import StatusReporter
from .sync_contract import queue_key

logger = logging.getLogger(__name__)

_PRICE_NOTE_PATTERN = re.compile(
    r"^~(?:b/o|price)\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Za-z]+)$",
    re.IGNORECASE,
)

_PRIVATE_STASH_ITEMS_URL = "https://www.pathofexile.com/character-window/get-stash-items"


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

    def run_private_scan(
        self,
        *,
        realm: str,
        league: str,
        price_item: Callable[[dict[str, Any]], dict[str, Any]],
        scan_id: str | None = None,
        started_at: str | None = None,
    ) -> dict[str, Any]:
        account_name = self._account_name.strip()
        if not account_name:
            raise ValueError("account_name is required for private stash scans")

        effective_scan_id = scan_id or uuid.uuid4().hex
        effective_started_at = started_at or _timestamp_utc()
        self._write_scan_run(
            scan_id=effective_scan_id,
            status="running",
            account_name=account_name,
            league=league,
            realm=realm,
            started_at=effective_started_at,
            updated_at=effective_started_at,
            completed_at=None,
            published_at=None,
            failed_at=None,
            tabs_total=0,
            tabs_processed=0,
            items_total=0,
            items_processed=0,
            error_message="",
        )
        self._write_active_scan(
            account_name=account_name,
            league=league,
            realm=realm,
            scan_id=effective_scan_id,
            is_active=True,
            started_at=effective_started_at,
            updated_at=effective_started_at,
        )

        tabs_total = 0
        tabs_processed = 0
        items_processed = 0
        items_total = 0

        try:
            tabs_payload = self._client.request(
                "GET",
                _PRIVATE_STASH_ITEMS_URL,
                params=_private_stash_params(
                    account_name=account_name,
                    realm=realm,
                    league=league,
                    tabs="1",
                    tab_index="0",
                ),
                headers=self._request_headers,
            )
            tabs = _ordered_private_tabs_from_payload(tabs_payload)
            tabs_total = len(tabs)

            for tab_number, tab in enumerate(tabs, start=1):
                tab_index = int(tab.get("tab_index") or 0)
                payload = self._client.request(
                    "GET",
                    _PRIVATE_STASH_ITEMS_URL,
                    params=_private_stash_params(
                        account_name=account_name,
                        realm=realm,
                        league=league,
                        tabs="0",
                        tab_index=str(tab_index),
                    ),
                    headers=self._request_headers,
                )
                current_tab_row = {
                    "scan_id": effective_scan_id,
                    "account_name": account_name,
                    "league": league,
                    "realm": realm,
                    "tab_id": str(tab.get("id") or ""),
                    "tab_index": tab_index,
                    "tab_name": str(tab.get("name") or ""),
                    "tab_type": str(tab.get("type") or "normal"),
                    "captured_at": _timestamp_utc(),
                    "tab_meta_json": json.dumps(tab, ensure_ascii=False),
                    "payload_json": json.dumps(payload, ensure_ascii=False),
                }

                raw_items = payload.get("items") if isinstance(payload, dict) else []
                items = raw_items if isinstance(raw_items, list) else []
                items_total += len(items)
                current_item_rows: list[dict[str, Any]] = []
                for raw_item in items:
                    if not isinstance(raw_item, dict):
                        continue
                    price_payload = price_item(raw_item)
                    if not _has_concrete_prediction(price_payload):
                        raise ValueError("missing concrete valuation for stash item")
                    prediction = normalize_stash_prediction(price_payload)
                    listed = parse_listed_price(str(raw_item.get("note") or ""))
                    listed_price = listed[0] if listed else None
                    currency = str(prediction.currency or (listed[1] if listed else "chaos"))
                    current_item_rows.append(
                        {
                            "scan_id": effective_scan_id,
                            "account_name": account_name,
                            "league": league,
                            "realm": realm,
                            "tab_id": str(tab.get("id") or ""),
                            "tab_index": tab_index,
                            "tab_name": str(tab.get("name") or ""),
                            "tab_type": str(tab.get("type") or "normal"),
                            "lineage_key": lineage_key_for_item(raw_item),
                            "content_signature": content_signature_for_item(raw_item),
                            "item_position_key": _item_position_key(
                                str(tab.get("id") or ""), raw_item
                            ),
                            "item_id": str(raw_item.get("id") or ""),
                            "item_name": str(
                                raw_item.get("name")
                                or raw_item.get("typeLine")
                                or "Unknown"
                            ),
                            "item_class": str(raw_item.get("itemClass") or "Unknown"),
                            "rarity": _rarity_from_frame_type(raw_item.get("frameType")),
                            "x": int(raw_item.get("x") or 0),
                            "y": int(raw_item.get("y") or 0),
                            "w": int(raw_item.get("w") or 1),
                            "h": int(raw_item.get("h") or 1),
                            "listed_price": listed_price,
                            "currency": currency,
                            "predicted_price": prediction.predicted_price,
                            "confidence": prediction.confidence,
                            "price_p10": prediction.price_p10,
                            "price_p90": prediction.price_p90,
                            "price_recommendation_eligible": prediction.price_recommendation_eligible,
                            "estimate_trust": prediction.estimate_trust,
                            "estimate_warning": prediction.estimate_warning,
                            "fallback_reason": prediction.fallback_reason,
                            "icon_url": str(raw_item.get("icon") or ""),
                            "priced_at": _timestamp_utc(),
                            "payload_json": json.dumps(raw_item, ensure_ascii=False),
                        }
                    )
                self._write_scan_tabs([current_tab_row])
                self._write_scan_item_valuations(current_item_rows)
                items_processed += len(current_item_rows)
                self._write_scan_run(
                    scan_id=effective_scan_id,
                    status="running",
                    account_name=account_name,
                    league=league,
                    realm=realm,
                    started_at=effective_started_at,
                    updated_at=_timestamp_utc(),
                    completed_at=None,
                    published_at=None,
                    failed_at=None,
                    tabs_total=tabs_total,
                    tabs_processed=tab_number,
                    items_total=items_total,
                    items_processed=items_processed,
                    error_message="",
                )
                tabs_processed = tab_number

            published_at = _timestamp_utc()
            self._write_scan_run(
                scan_id=effective_scan_id,
                status="published",
                account_name=account_name,
                league=league,
                realm=realm,
                started_at=effective_started_at,
                updated_at=published_at,
                completed_at=published_at,
                published_at=published_at,
                failed_at=None,
                tabs_total=tabs_total,
                tabs_processed=tabs_processed,
                items_total=items_total,
                items_processed=items_processed,
                error_message="",
            )
            self._write_active_scan(
                account_name=account_name,
                league=league,
                realm=realm,
                scan_id=effective_scan_id,
                is_active=False,
                started_at=effective_started_at,
                updated_at=published_at,
            )
            self._write_published_scan(
                account_name=account_name,
                league=league,
                realm=realm,
                scan_id=effective_scan_id,
                published_at=published_at,
            )
            return {
                "scanId": effective_scan_id,
                "status": "published",
                "startedAt": effective_started_at,
                "publishedAt": published_at,
                "accountName": account_name,
                "league": league,
                "realm": realm,
            }
        except Exception as exc:
            failed_at = _timestamp_utc()
            error_message = _friendly_scan_error_message(exc)
            self._write_scan_run(
                scan_id=effective_scan_id,
                status="failed",
                account_name=account_name,
                league=league,
                realm=realm,
                started_at=effective_started_at,
                updated_at=failed_at,
                completed_at=None,
                published_at=None,
                failed_at=failed_at,
                tabs_total=tabs_total,
                tabs_processed=tabs_processed,
                items_total=items_total,
                items_processed=items_processed,
                error_message=error_message,
            )
            self._write_active_scan(
                account_name=account_name,
                league=league,
                realm=realm,
                scan_id=effective_scan_id,
                is_active=False,
                started_at=effective_started_at,
                updated_at=failed_at,
            )
            logger.exception(
                "Private stash scan failed account=%s realm=%s league=%s",
                account_name,
                realm,
                league,
            )
            return {
                "scanId": effective_scan_id,
                "status": "failed",
                "startedAt": effective_started_at,
                "accountName": account_name,
                "league": league,
                "realm": realm,
                "error": error_message,
            }

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

    def _write_scan_run(
        self,
        *,
        scan_id: str,
        status: str,
        account_name: str,
        league: str,
        realm: str,
        started_at: str,
        updated_at: str,
        completed_at: str | None,
        published_at: str | None,
        failed_at: str | None,
        tabs_total: int,
        tabs_processed: int,
        items_total: int,
        items_processed: int,
        error_message: str,
    ) -> None:
        row = {
            "scan_id": scan_id,
            "account_name": account_name,
            "league": league,
            "realm": realm,
            "status": status,
            "started_at": started_at,
            "updated_at": updated_at,
            "completed_at": completed_at,
            "published_at": published_at,
            "failed_at": failed_at,
            "tabs_total": tabs_total,
            "tabs_processed": tabs_processed,
            "items_total": items_total,
            "items_processed": items_processed,
            "error_message": error_message,
        }
        query = (
            "INSERT INTO poe_trade.account_stash_scan_runs "
            "(scan_id, account_name, league, realm, status, started_at, updated_at, completed_at, published_at, failed_at, tabs_total, tabs_processed, items_total, items_processed, error_message)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row, ensure_ascii=False)}"
        )
        self._clickhouse.execute(query)

    def _write_active_scan(
        self,
        *,
        account_name: str,
        league: str,
        realm: str,
        scan_id: str,
        is_active: bool,
        started_at: str,
        updated_at: str,
    ) -> None:
        row = {
            "account_name": account_name,
            "league": league,
            "realm": realm,
            "scan_id": scan_id,
            "is_active": _bool_to_uint8(is_active),
            "started_at": started_at,
            "updated_at": updated_at,
        }
        query = (
            "INSERT INTO poe_trade.account_stash_active_scans "
            "(account_name, league, realm, scan_id, is_active, started_at, updated_at)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row, ensure_ascii=False)}"
        )
        self._clickhouse.execute(query)

    def _write_scan_tabs(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        query = (
            "INSERT INTO poe_trade.account_stash_scan_tabs "
            "(scan_id, account_name, league, realm, tab_id, tab_index, tab_name, tab_type, captured_at, tab_meta_json, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{_json_each_row_payload(rows)}"
        )
        self._clickhouse.execute(query)

    def _write_scan_item_valuations(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        query = (
            "INSERT INTO poe_trade.account_stash_item_valuations "
            "(scan_id, account_name, league, realm, tab_id, tab_index, tab_name, tab_type, lineage_key, content_signature, item_position_key, item_id, item_name, item_class, rarity, x, y, w, h, listed_price, currency, predicted_price, confidence, price_p10, price_p90, price_recommendation_eligible, estimate_trust, estimate_warning, fallback_reason, icon_url, priced_at, payload_json)\n"
            "FORMAT JSONEachRow\n"
            f"{_json_each_row_payload(rows)}"
        )
        self._clickhouse.execute(query)

    def _write_published_scan(
        self,
        *,
        account_name: str,
        league: str,
        realm: str,
        scan_id: str,
        published_at: str,
    ) -> None:
        row = {
            "account_name": account_name,
            "league": league,
            "realm": realm,
            "scan_id": scan_id,
            "published_at": published_at,
        }
        query = (
            "INSERT INTO poe_trade.account_stash_published_scans "
            "(account_name, league, realm, scan_id, published_at)\n"
            "FORMAT JSONEachRow\n"
            f"{json.dumps(row, ensure_ascii=False)}"
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


def _ordered_private_tabs_from_payload(payload: Any) -> list[dict[str, Any]]:
    raw_tabs = _tab_rows_from_payload(payload)
    rows: list[dict[str, Any]] = []
    for index, tab in enumerate(raw_tabs):
        raw_index = tab.get("i")
        tab_index = int(raw_index) if isinstance(raw_index, (int, str)) else index
        rows.append(
            {
                "id": str(tab.get("id") or tab.get("tab_id") or ""),
                "tab_index": tab_index,
                "name": str(tab.get("n") or tab.get("name") or ""),
                "type": str(tab.get("type") or "normal"),
            }
        )
    return rows


def _private_stash_params(
    *,
    account_name: str,
    realm: str,
    league: str,
    tabs: str,
    tab_index: str,
) -> dict[str, str]:
    return {
        "accountName": account_name,
        "realm": realm,
        "league": league,
        "tabs": tabs,
        "tabIndex": tab_index,
    }


def _item_position_key(tab_id: str, item: Mapping[str, Any]) -> str:
    return (
        f"{tab_id}:{int(item.get('x') or 0)}:{int(item.get('y') or 0)}:"
        f"{int(item.get('w') or 1)}:{int(item.get('h') or 1)}"
    )


def _timestamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _has_concrete_prediction(payload: Mapping[str, Any]) -> bool:
    predicted_value = payload.get("predictedValue")
    if isinstance(predicted_value, (int, float)):
        return True
    price_p50 = payload.get("price_p50")
    return isinstance(price_p50, (int, float))


def _json_each_row_payload(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)


def _bool_to_uint8(value: bool) -> int:
    return 1 if value else 0


def _friendly_scan_error_message(exc: Exception) -> str:
    message = str(exc)
    if "PoE client error 401" in message or "PoE client error 403" in message:
        return "invalid POESESSID or stash access denied"
    return message


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
