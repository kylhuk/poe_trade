from __future__ import annotations

import json
import re
from typing import Any

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError

_PRICE_NOTE_PATTERN = re.compile(
    r"^~(?:b/o|price)\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Za-z]+)$",
    re.IGNORECASE,
)


class StashBackendUnavailable(RuntimeError):
    pass


def fetch_stash_tabs(
    client: ClickHouseClient,
    *,
    league: str,
    realm: str,
) -> dict[str, Any]:
    query = (
        "SELECT tab_id, argMax(payload_json, captured_at) AS payload_json "
        "FROM poe_trade.raw_account_stash_snapshot "
        f"WHERE league = '{league}' AND realm = '{realm}' "
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
        row = json.loads(line)
        stash_payload = json.loads(str(row.get("payload_json") or "{}"))
        tab_meta = (
            stash_payload.get("tab")
            if isinstance(stash_payload.get("tab"), dict)
            else {}
        )
        body = (
            stash_payload.get("payload")
            if isinstance(stash_payload.get("payload"), dict)
            else {}
        )
        items_raw = body.get("items") if isinstance(body.get("items"), list) else []
        tab_name = str(
            tab_meta.get("n") or tab_meta.get("name") or row.get("tab_id") or ""
        )
        tab_type = _normalize_tab_type(str(tab_meta.get("type") or "normal"))
        items = [
            _to_api_item(item, tab_name=tab_name)
            for item in items_raw
            if isinstance(item, dict)
        ]
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
