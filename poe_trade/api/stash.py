from __future__ import annotations

import json
import re
from typing import Any, cast

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError

_PRICE_NOTE_PATTERN = re.compile(
    r"^~(?:b/o|price)\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Za-z]+)$",
    re.IGNORECASE,
)


class StashBackendUnavailable(RuntimeError):
    pass


def stash_status_payload(
    client: ClickHouseClient,
    *,
    league: str,
    realm: str,
    enable_account_stash: bool,
    session: dict[str, Any] | None,
) -> dict[str, Any]:
    if not enable_account_stash:
        return {
            "status": "feature_unavailable",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "reason": "set POE_ENABLE_ACCOUNT_STASH=true to enable stash APIs",
            "featureFlag": "POE_ENABLE_ACCOUNT_STASH",
            "session": None,
        }
    if session is None:
        return {
            "status": "disconnected",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": None,
        }
    session_status = str(session.get("status") or "")
    if session_status == "session_expired":
        return {
            "status": "session_expired",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": {
                "accountName": str(session.get("account_name") or ""),
                "expiresAt": str(session.get("expires_at") or ""),
            },
        }
    if session_status != "connected":
        return {
            "status": "disconnected",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": None,
        }

    raw_account_name = str(session.get("account_name") or "")
    if not raw_account_name:
        return {
            "status": "disconnected",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": None,
        }
    account_name = _escape_sql_literal(raw_account_name)
    query = (
        "SELECT countDistinct(tab_id) AS tabs, count() AS snapshots "
        "FROM poe_trade.raw_account_stash_snapshot "
        f"WHERE league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        f"AND account_name = '{account_name}' "
        "FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashBackendUnavailable("stash status backend unavailable") from exc
    tabs = 0
    snapshots = 0
    if payload:
        row = json.loads(payload.splitlines()[0])
        tabs = int(row.get("tabs") or 0)
        snapshots = int(row.get("snapshots") or 0)
    return {
        "status": "connected_populated" if snapshots > 0 else "connected_empty",
        "connected": True,
        "tabCount": tabs,
        "itemCount": snapshots,
        "session": {
            "accountName": raw_account_name,
            "expiresAt": str(session.get("expires_at") or ""),
        },
    }


def fetch_stash_tabs(
    client: ClickHouseClient,
    *,
    league: str,
    realm: str,
    account_name: str = "",
) -> dict[str, Any]:
    escaped_account = _escape_sql_literal(account_name)
    query = (
        "SELECT tab_id, argMax(payload_json, captured_at) AS payload_json "
        "FROM poe_trade.raw_account_stash_snapshot "
        f"WHERE league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        f"AND account_name = '{escaped_account}' "
        "GROUP BY tab_id ORDER BY tab_id FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashBackendUnavailable("stash backend unavailable") from exc
    if not payload:
        return {"stashTabs": []}

    tabs: list[dict[str, Any]] = []
    for line in payload.splitlines():
        row_obj = json.loads(line)
        row = cast(dict[str, object], row_obj if isinstance(row_obj, dict) else {})
        stash_obj = json.loads(str(row.get("payload_json") or "{}"))
        stash_payload = cast(
            dict[str, object], stash_obj if isinstance(stash_obj, dict) else {}
        )
        tab_node = stash_payload.get("tab")
        tab_meta = cast(
            dict[str, object], tab_node if isinstance(tab_node, dict) else {}
        )
        payload_node = stash_payload.get("payload")
        body = cast(
            dict[str, object], payload_node if isinstance(payload_node, dict) else {}
        )
        raw_items = body.get("items")
        items_raw: list[dict[str, object]]
        if isinstance(raw_items, list):
            items_raw = [item for item in raw_items if isinstance(item, dict)]
        else:
            items_raw = []
        tab_name = str(
            tab_meta.get("n") or tab_meta.get("name") or row.get("tab_id") or ""
        )
        tab_type = _normalize_tab_type(str(tab_meta.get("type") or "normal"))
        items = [_to_api_item(item, tab_name=tab_name) for item in items_raw]
        tabs.append(
            {
                "id": str(row.get("tab_id") or ""),
                "name": tab_name,
                "type": tab_type,
                "items": items,
            }
        )
    return {"stashTabs": tabs}


def _to_api_item(item: dict[str, Any], *, tab_name: str) -> dict[str, Any]:
    listed_price = _parse_listed_price(str(item.get("note") or tab_name))
    listed_value = listed_price[0] if listed_price else None
    currency = listed_price[1] if listed_price else "chaos"
    estimated = float(item.get("chaosValue") or listed_value or 0.0)
    confidence = (
        85
        if item.get("chaosValue") is not None
        else (70 if listed_value is not None else 0)
    )
    delta = 0.0 if listed_value is None else estimated - listed_value
    delta_percent = 0.0 if listed_value in (None, 0) else (delta / listed_value) * 100.0
    evaluation = "well_priced"
    if delta_percent >= 10:
        evaluation = "mispriced"
    elif delta_percent >= 3:
        evaluation = "could_be_better"
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or item.get("typeLine") or "Unknown"),
        "x": int(item.get("x") or 0),
        "y": int(item.get("y") or 0),
        "w": int(item.get("w") or 1),
        "h": int(item.get("h") or 1),
        "itemClass": str(item.get("itemClass") or "Unknown"),
        "rarity": _rarity_from_frame_type(item.get("frameType")),
        "listedPrice": listed_value,
        "estimatedPrice": estimated,
        "estimatedPriceConfidence": confidence,
        "priceDeltaChaos": delta,
        "priceDeltaPercent": delta_percent,
        "priceEvaluation": evaluation,
        "currency": currency,
        "iconUrl": str(item.get("icon") or ""),
    }


def _parse_listed_price(raw: str) -> tuple[float, str] | None:
    match = _PRICE_NOTE_PATTERN.match(raw.strip())
    if not match:
        return None
    return float(match.group(1)), match.group(2).lower()


def _normalize_tab_type(raw: str) -> str:
    normalized = raw.lower().strip()
    if normalized in {"normal", "quad", "currency", "map"}:
        return normalized
    return "normal"


def _rarity_from_frame_type(frame_type: Any) -> str:
    mapping = {0: "normal", 1: "magic", 2: "rare", 3: "unique"}
    if isinstance(frame_type, int):
        return mapping.get(frame_type, "normal")
    return "normal"


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")
