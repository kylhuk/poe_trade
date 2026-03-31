from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Any

from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError


class StashScanBackendUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StashPrediction:
    predicted_price: float
    currency: str
    confidence: float
    price_p10: float | None
    price_p90: float | None
    price_recommendation_eligible: bool
    estimate_trust: str
    estimate_warning: str
    fallback_reason: str


def content_signature_for_item(item: dict[str, Any]) -> str:
    stable = {
        "name": str(item.get("name") or "").strip(),
        "typeLine": str(item.get("typeLine") or item.get("baseType") or "").strip(),
        "rarity": item.get("frameType"),
        "itemClass": str(item.get("itemClass") or "").strip(),
        "mods": _normalized_mod_lines(item),
        "icon": str(item.get("icon") or "").strip(),
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def lineage_key_for_item(item: dict[str, Any]) -> str:
    item_id = str(item.get("id") or "").strip()
    if item_id:
        return f"item:{item_id}"
    return f"sig:{content_signature_for_item(item)}"


def lineage_key_from_previous_scan(
    *,
    signature: str,
    prior_signature_matches: dict[str, str],
    prior_position_matches: dict[str, str],
    position_key: str,
) -> str:
    if signature in prior_signature_matches:
        return prior_signature_matches[signature]
    if position_key in prior_position_matches:
        return prior_position_matches[position_key]
    return f"sig:{signature}"


def serialize_stash_item_to_clipboard(item: dict[str, Any]) -> str:
    lines = [
        f"Rarity: {_rarity_label(item.get('frameType'))}",
        str(item.get("name") or "").strip(),
        str(
            item.get("typeLine")
            or item.get("baseType")
            or item.get("name")
            or "Unknown"
        ).strip(),
        "--------",
    ]
    for entry in _normalized_mod_lines(item):
        lines.append(entry)
    return "\n".join(line for line in lines if line)


def normalize_stash_prediction(payload: dict[str, Any]) -> StashPrediction:
    interval = (
        payload.get("interval") if isinstance(payload.get("interval"), dict) else {}
    )
    return StashPrediction(
        predicted_price=float(
            payload.get("predictedValue") or payload.get("price_p50") or 0.0
        ),
        currency=str(payload.get("currency") or "chaos"),
        confidence=float(
            payload.get("confidence") or payload.get("confidence_percent") or 0.0
        ),
        price_p10=_opt_float(interval.get("p10") or payload.get("price_p10")),
        price_p90=_opt_float(interval.get("p90") or payload.get("price_p90")),
        price_recommendation_eligible=bool(
            payload.get("priceRecommendationEligible")
            if "priceRecommendationEligible" in payload
            else payload.get("price_recommendation_eligible", False)
        ),
        estimate_trust=str(
            payload.get("estimateTrust") or payload.get("estimate_trust") or "normal"
        ),
        estimate_warning=str(
            payload.get("estimateWarning") or payload.get("estimate_warning") or ""
        ),
        fallback_reason=str(
            payload.get("fallbackReason") or payload.get("fallback_reason") or ""
        ),
    )


def fetch_published_scan_id(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
) -> str | None:
    query = (
        "SELECT argMax(scan_id, published_at) AS scan_id "
        "FROM poe_trade.account_stash_published_scans "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        "FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashScanBackendUnavailable("published scan backend unavailable") from exc
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    scan_id = str(row.get("scan_id") or "").strip()
    return scan_id or None


def fetch_active_scan(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    stale_timeout_seconds: int | None = None,
) -> dict[str, Any] | None:
    query = (
        "SELECT scan_id, is_active, started_at, updated_at "
        "FROM poe_trade.account_stash_active_scans "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        "ORDER BY updated_at DESC LIMIT 1 FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashScanBackendUnavailable("active scan backend unavailable") from exc
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    active_scan = {
        "scanId": str(row.get("scan_id") or ""),
        "isActive": bool(row.get("is_active") or 0),
        "startedAt": str(row.get("started_at") or ""),
        "updatedAt": str(row.get("updated_at") or ""),
    }
    if not active_scan["isActive"]:
        return active_scan

    timeout_seconds = int(stale_timeout_seconds or 0)
    if timeout_seconds <= 0:
        return active_scan

    latest_run = fetch_latest_scan_run(
        client,
        account_name=account_name,
        league=league,
        realm=realm,
        scan_id=active_scan["scanId"],
    )
    if not _active_scan_is_stale(active_scan, latest_run, timeout_seconds):
        return active_scan

    return _reconcile_stale_active_scan(
        client,
        account_name=account_name,
        league=league,
        realm=realm,
        active_scan=active_scan,
        latest_run=latest_run,
    )


def fetch_latest_scan_run(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    scan_id: str | None = None,
) -> dict[str, Any] | None:
    scan_id_filter = (
        f"AND scan_id = '{_escape_sql_literal(scan_id)}' " if scan_id else ""
    )
    query = (
        "SELECT scan_id, status, started_at, updated_at, published_at, tabs_total, tabs_processed, items_total, items_processed, error_message "
        "FROM poe_trade.account_stash_scan_runs "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        f"{scan_id_filter}"
        "ORDER BY updated_at DESC LIMIT 1 FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashScanBackendUnavailable("scan run backend unavailable") from exc
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    return {
        "scanId": str(row.get("scan_id") or ""),
        "status": str(row.get("status") or "idle"),
        "startedAt": str(row.get("started_at") or "") or None,
        "updatedAt": str(row.get("updated_at") or "") or None,
        "publishedAt": str(row.get("published_at") or "") or None,
        "progress": {
            "tabsTotal": int(row.get("tabs_total") or 0),
            "tabsProcessed": int(row.get("tabs_processed") or 0),
            "itemsTotal": int(row.get("items_total") or 0),
            "itemsProcessed": int(row.get("items_processed") or 0),
        },
        "error": str(row.get("error_message") or "") or None,
    }


def _active_scan_is_stale(
    active_scan: dict[str, Any],
    latest_run: dict[str, Any] | None,
    stale_timeout_seconds: int,
) -> bool:
    if stale_timeout_seconds <= 0:
        return False
    candidate_timestamp = _parse_iso_datetime(
        str((latest_run or {}).get("updatedAt") or active_scan.get("updatedAt") or "")
    )
    if candidate_timestamp is None:
        return False
    if candidate_timestamp.tzinfo is None:
        candidate_timestamp = candidate_timestamp.replace(tzinfo=timezone.utc)
    return _utcnow() - candidate_timestamp > timedelta(seconds=stale_timeout_seconds)


def _reconcile_stale_active_scan(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    active_scan: dict[str, Any],
    latest_run: dict[str, Any] | None,
) -> dict[str, Any]:
    reconciled_at = _utcnow().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    scan_id = str(active_scan.get("scanId") or "")
    started_at = str(
        (latest_run or {}).get("startedAt")
        or active_scan.get("startedAt")
        or reconciled_at
    )

    _write_active_scan_row(
        client,
        account_name=account_name,
        league=league,
        realm=realm,
        scan_id=scan_id,
        is_active=False,
        started_at=started_at,
        updated_at=reconciled_at,
    )

    latest_status = str((latest_run or {}).get("status") or "")
    if latest_run is None or latest_status not in {"failed", "published"}:
        progress = (
            (latest_run or {}).get("progress") if isinstance(latest_run, dict) else {}
        )
        progress = progress if isinstance(progress, dict) else {}
        _write_scan_run_row(
            client,
            scan_id=scan_id,
            status="failed",
            account_name=account_name,
            league=league,
            realm=realm,
            started_at=started_at,
            updated_at=reconciled_at,
            completed_at=None,
            published_at=None,
            failed_at=reconciled_at,
            tabs_total=int(progress.get("tabsTotal") or 0),
            tabs_processed=int(progress.get("tabsProcessed") or 0),
            items_total=int(progress.get("itemsTotal") or 0),
            items_processed=int(progress.get("itemsProcessed") or 0),
            error_message="stale active scan timed out",
        )

    return {
        **active_scan,
        "isActive": False,
        "updatedAt": reconciled_at,
    }


def fetch_published_tabs(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
) -> dict[str, Any]:
    scan_id = fetch_published_scan_id(
        client,
        account_name=account_name,
        league=league,
        realm=realm,
    )
    latest_run = fetch_latest_scan_run(
        client,
        account_name=account_name,
        league=league,
        realm=realm,
    )
    if not scan_id:
        return {
            "scanId": None,
            "publishedAt": None,
            "isStale": False,
            "scanStatus": latest_run
            if latest_run and latest_run.get("status") in {"running", "publishing"}
            else None,
            "stashTabs": [],
        }

    published_at = _fetch_published_at(
        client,
        account_name=account_name,
        league=league,
        realm=realm,
    )
    tabs_query = (
        "SELECT tab_id, tab_index, tab_name, tab_type "
        "FROM poe_trade.account_stash_scan_tabs "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        f"AND scan_id = '{_escape_sql_literal(scan_id)}' "
        "ORDER BY tab_index ASC FORMAT JSONEachRow"
    )
    items_query = (
        "SELECT tab_id, tab_index, lineage_key, item_id, item_name, item_class, rarity, x, y, w, h, listed_price, currency, predicted_price, confidence, price_p10, price_p90, price_recommendation_eligible, estimate_trust, estimate_warning, fallback_reason, icon_url, priced_at "
        "FROM poe_trade.account_stash_item_valuations "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        f"AND scan_id = '{_escape_sql_literal(scan_id)}' "
        "ORDER BY tab_index ASC, y ASC, x ASC FORMAT JSONEachRow"
    )
    try:
        tabs_payload = client.execute(tabs_query).strip()
        items_payload = client.execute(items_query).strip()
    except ClickHouseClientError as exc:
        raise StashScanBackendUnavailable(
            "published stash backend unavailable"
        ) from exc

    tabs: list[dict[str, Any]] = []
    tab_map: dict[str, dict[str, Any]] = {}
    for line in tabs_payload.splitlines() if tabs_payload else []:
        row = json.loads(line)
        tab = {
            "id": str(row.get("tab_id") or ""),
            "name": str(row.get("tab_name") or ""),
            "type": _normalize_tab_type(str(row.get("tab_type") or "normal")),
            "items": [],
        }
        tabs.append(tab)
        tab_map[tab["id"]] = tab

    for line in items_payload.splitlines() if items_payload else []:
        row = json.loads(line)
        tab = tab_map.get(str(row.get("tab_id") or ""))
        if tab is None:
            continue
        tab["items"].append(_to_api_item(row))

    return {
        "scanId": scan_id,
        "publishedAt": published_at,
        "isStale": False,
        "scanStatus": latest_run
        if latest_run and latest_run.get("status") in {"running", "publishing"}
        else None,
        "stashTabs": tabs,
    }


def fetch_item_history(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    lineage_key: str,
    limit: int = 20,
) -> dict[str, Any]:
    query = (
        "SELECT lineage_key, item_name, item_class, rarity, icon_url, scan_id, priced_at, "
        "predicted_price, confidence, price_p10, price_p90, listed_price, currency, "
        "price_recommendation_eligible, estimate_trust, estimate_warning, fallback_reason "
        "FROM poe_trade.account_stash_item_valuations "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        f"AND lineage_key = '{_escape_sql_literal(lineage_key)}' "
        f"ORDER BY priced_at DESC LIMIT {max(limit, 1)} FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashScanBackendUnavailable("item history backend unavailable") from exc
    if not payload:
        return {"fingerprint": lineage_key, "item": {}, "history": []}

    rows = [json.loads(line) for line in payload.splitlines() if line.strip()]
    first = rows[0]
    return {
        "fingerprint": str(first.get("lineage_key") or lineage_key),
        "item": {
            "name": str(first.get("item_name") or "Unknown"),
            "itemClass": str(first.get("item_class") or ""),
            "rarity": str(first.get("rarity") or "normal"),
            "iconUrl": str(first.get("icon_url") or ""),
        },
        "history": [
            {
                "scanId": str(row.get("scan_id") or ""),
                "pricedAt": str(row.get("priced_at") or ""),
                "predictedValue": float(row.get("predicted_price") or 0.0),
                "listedPrice": _opt_float(row.get("listed_price")),
                "currency": str(row.get("currency") or "chaos"),
                "confidence": float(row.get("confidence") or 0.0),
                "interval": {
                    "p10": _opt_float(row.get("price_p10")),
                    "p90": _opt_float(row.get("price_p90")),
                },
                "priceRecommendationEligible": bool(
                    row.get("price_recommendation_eligible") or 0
                ),
                "estimateTrust": str(row.get("estimate_trust") or "normal"),
                "estimateWarning": str(row.get("estimate_warning") or ""),
                "fallbackReason": str(row.get("fallback_reason") or ""),
            }
            for row in rows
        ],
    }


def _fetch_published_at(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
) -> str | None:
    query = (
        "SELECT argMax(published_at, published_at) AS published_at "
        "FROM poe_trade.account_stash_published_scans "
        f"WHERE account_name = '{_escape_sql_literal(account_name)}' "
        f"AND league = '{_escape_sql_literal(league)}' "
        f"AND realm = '{_escape_sql_literal(realm)}' "
        "FORMAT JSONEachRow"
    )
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise StashScanBackendUnavailable("published scan backend unavailable") from exc
    if not payload:
        return None
    row = json.loads(payload.splitlines()[0])
    value = str(row.get("published_at") or "").strip()
    return value or None


def _to_api_item(row: dict[str, Any]) -> dict[str, Any]:
    listed_price = _opt_float(row.get("listed_price"))
    estimated = float(row.get("predicted_price") or 0.0)
    delta = 0.0 if listed_price is None else estimated - listed_price
    delta_percent = 0.0 if listed_price in (None, 0) else (delta / listed_price) * 100.0
    evaluation = "well_priced"
    if delta_percent >= 10:
        evaluation = "mispriced"
    elif delta_percent >= 3:
        evaluation = "could_be_better"
    return {
        "id": str(row.get("item_id") or row.get("lineage_key") or ""),
        "fingerprint": str(row.get("lineage_key") or ""),
        "name": str(row.get("item_name") or "Unknown"),
        "x": int(row.get("x") or 0),
        "y": int(row.get("y") or 0),
        "w": int(row.get("w") or 1),
        "h": int(row.get("h") or 1),
        "itemClass": str(row.get("item_class") or "Unknown"),
        "rarity": str(row.get("rarity") or "normal"),
        "listedPrice": listed_price,
        "estimatedPrice": estimated,
        "estimatedPriceConfidence": float(row.get("confidence") or 0.0),
        "priceDeltaChaos": delta,
        "priceDeltaPercent": delta_percent,
        "priceEvaluation": evaluation,
        "currency": str(row.get("currency") or "chaos"),
        "iconUrl": str(row.get("icon_url") or ""),
        "pricedAt": str(row.get("priced_at") or ""),
        "interval": {
            "p10": _opt_float(row.get("price_p10")),
            "p90": _opt_float(row.get("price_p90")),
        },
        "priceRecommendationEligible": bool(
            row.get("price_recommendation_eligible") or 0
        ),
        "estimateTrust": str(row.get("estimate_trust") or "normal"),
        "estimateWarning": str(row.get("estimate_warning") or ""),
        "fallbackReason": str(row.get("fallback_reason") or ""),
    }


def _normalized_mod_lines(item: dict[str, Any]) -> list[str]:
    sections = (
        "implicitMods",
        "explicitMods",
        "craftedMods",
        "fracturedMods",
        "enchantMods",
    )
    lines: list[str] = []
    for section in sections:
        values = item.get(section)
        if not isinstance(values, list):
            continue
        for value in values:
            text = str(value).strip()
            if text:
                lines.append(text)
    return lines


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rarity_label(frame_type: Any) -> str:
    mapping = {0: "Normal", 1: "Magic", 2: "Rare", 3: "Unique"}
    if isinstance(frame_type, int):
        return mapping.get(frame_type, "Normal")
    return "Normal"


def _escape_sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _write_scan_run_row(
    client: ClickHouseClient,
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
    client.execute(query)


def _write_active_scan_row(
    client: ClickHouseClient,
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
        "is_active": 1 if is_active else 0,
        "started_at": started_at,
        "updated_at": updated_at,
    }
    query = (
        "INSERT INTO poe_trade.account_stash_active_scans "
        "(account_name, league, realm, scan_id, is_active, started_at, updated_at)\n"
        "FORMAT JSONEachRow\n"
        f"{json.dumps(row, ensure_ascii=False)}"
    )
    client.execute(query)


def _normalize_tab_type(raw: str) -> str:
    normalized = raw.lower().strip()
    mapping = {
        "normal": "normal",
        "normalstash": "normal",
        "premiumstash": "normal",
        "quad": "quad",
        "quadstash": "quad",
        "currency": "currency",
        "currencystash": "currency",
        "map": "map",
        "mapstash": "map",
        "fragment": "fragment",
        "fragmentstash": "fragment",
        "essence": "essence",
        "essencestash": "essence",
        "divination": "divination",
        "divinationcardstash": "divination",
        "unique": "unique",
        "uniquestash": "unique",
        "delve": "delve",
        "delvestash": "delve",
        "blight": "blight",
        "blightstash": "blight",
        "ultimatum": "ultimatum",
        "ultimatumstash": "ultimatum",
        "delirium": "delirium",
        "deliriumstash": "delirium",
        "metamorph": "metamorph",
        "metamorphstash": "metamorph",
        "flask": "flask",
        "flaskstash": "flask",
        "gem": "gem",
        "gemstash": "gem",
    }
    return mapping.get(normalized, "normal")
