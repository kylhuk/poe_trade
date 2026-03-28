from __future__ import annotations

from typing import Any

from poe_trade.db import ClickHouseClient
from poe_trade.stash_scan import (
    StashScanBackendUnavailable,
    fetch_active_scan,
    fetch_item_history,
    fetch_latest_scan_run,
    fetch_published_scan_id,
    fetch_published_tabs,
)

from .valuation import (
    ValuationBackendUnavailable,
    build_stash_scan_valuations_payload,
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
            "publishedScanId": None,
            "publishedAt": None,
            "scanStatus": None,
        }
    if session is None:
        return {
            "status": "disconnected",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": None,
            "publishedScanId": None,
            "publishedAt": None,
            "scanStatus": None,
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
            "publishedScanId": None,
            "publishedAt": None,
            "scanStatus": None,
        }
    if session_status != "connected":
        return {
            "status": "disconnected",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": None,
            "publishedScanId": None,
            "publishedAt": None,
            "scanStatus": None,
        }

    account_name = str(session.get("account_name") or "")
    if not account_name:
        return {
            "status": "disconnected",
            "connected": False,
            "tabCount": 0,
            "itemCount": 0,
            "session": None,
            "publishedScanId": None,
            "publishedAt": None,
            "scanStatus": None,
        }

    try:
        published = fetch_stash_tabs(
            client,
            league=league,
            realm=realm,
            account_name=account_name,
        )
    except StashScanBackendUnavailable as exc:
        raise StashBackendUnavailable("stash status backend unavailable") from exc

    stash_tabs = published.get("stashTabs") if isinstance(published, dict) else []
    tabs = stash_tabs if isinstance(stash_tabs, list) else []
    item_count = sum(
        len(tab.get("items") or [])
        for tab in tabs
        if isinstance(tab, dict) and isinstance(tab.get("items"), list)
    )
    published_scan_id = published.get("scanId") if isinstance(published, dict) else None
    published_at = published.get("publishedAt") if isinstance(published, dict) else None
    scan_status = published.get("scanStatus") if isinstance(published, dict) else None
    return {
        "status": "connected_populated" if tabs else "connected_empty",
        "connected": True,
        "tabCount": len(tabs),
        "itemCount": item_count,
        "session": {
            "accountName": account_name,
            "expiresAt": str(session.get("expires_at") or ""),
        },
        "publishedScanId": published_scan_id,
        "publishedAt": published_at,
        "scanStatus": scan_status,
    }


def fetch_stash_tabs(
    client: ClickHouseClient,
    *,
    league: str,
    realm: str,
    account_name: str = "",
) -> dict[str, Any]:
    try:
        return fetch_published_tabs(
            client,
            account_name=account_name,
            league=league,
            realm=realm,
        )
    except StashScanBackendUnavailable as exc:
        raise StashBackendUnavailable("stash backend unavailable") from exc


def stash_scan_status_payload(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    stale_timeout_seconds: int = 0,
) -> dict[str, Any]:
    try:
        active = fetch_active_scan(
            client,
            account_name=account_name,
            league=league,
            realm=realm,
            stale_timeout_seconds=stale_timeout_seconds,
        )
        latest = fetch_latest_scan_run(
            client,
            account_name=account_name,
            league=league,
            realm=realm,
        )
        published_scan_id = fetch_published_scan_id(
            client,
            account_name=account_name,
            league=league,
            realm=realm,
        )
    except StashScanBackendUnavailable as exc:
        raise StashBackendUnavailable("stash scan status backend unavailable") from exc

    if latest is None:
        if active is None:
            return {
                "status": "idle",
                "activeScanId": None,
                "publishedScanId": published_scan_id,
                "startedAt": None,
                "updatedAt": None,
                "publishedAt": None,
                "progress": {
                    "tabsTotal": 0,
                    "tabsProcessed": 0,
                    "itemsTotal": 0,
                    "itemsProcessed": 0,
                },
                "error": None,
            }
        status = "running" if active.get("isActive") else "idle"
        return {
            "status": status,
            "activeScanId": active.get("scanId") if active.get("isActive") else None,
            "publishedScanId": published_scan_id,
            "startedAt": active.get("startedAt"),
            "updatedAt": active.get("updatedAt"),
            "publishedAt": None,
            "progress": {
                "tabsTotal": 0,
                "tabsProcessed": 0,
                "itemsTotal": 0,
                "itemsProcessed": 0,
            },
            "error": None,
        }

    is_active = bool(active and active.get("isActive"))
    status = str(latest.get("status") or "idle")
    active_scan_id = (
        latest.get("scanId")
        if (is_active or status in {"running", "publishing"})
        else None
    )
    if status == "published":
        active_scan_id = None
    return {
        "status": status,
        "activeScanId": active_scan_id,
        "publishedScanId": published_scan_id,
        "startedAt": latest.get("startedAt"),
        "updatedAt": latest.get("updatedAt"),
        "publishedAt": latest.get("publishedAt"),
        "progress": latest.get("progress")
        or {
            "tabsTotal": 0,
            "tabsProcessed": 0,
            "itemsTotal": 0,
            "itemsProcessed": 0,
        },
        "error": latest.get("error"),
    }


def fetch_stash_item_history(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    fingerprint: str,
    limit: int = 20,
) -> dict[str, Any]:
    try:
        return fetch_item_history(
            client,
            account_name=account_name,
            league=league,
            realm=realm,
            lineage_key=fingerprint,
            limit=limit,
        )
    except StashScanBackendUnavailable as exc:
        raise StashBackendUnavailable("stash history backend unavailable") from exc


def stash_scan_valuations_payload(
    client: ClickHouseClient,
    *,
    account_name: str,
    league: str,
    realm: str,
    scan_id: str,
    item_id: str | None,
    structured_mode: bool,
    min_threshold: float,
    max_threshold: float,
    max_age_days: int,
) -> dict[str, Any]:
    try:
        return build_stash_scan_valuations_payload(
            client,
            account_name=account_name,
            league=league,
            realm=realm,
            scan_id=scan_id,
            item_id=item_id,
            structured_mode=structured_mode,
            min_threshold=min_threshold,
            max_threshold=max_threshold,
            max_age_days=max_age_days,
        )
    except ValuationBackendUnavailable as exc:
        raise StashBackendUnavailable("stash valuations backend unavailable") from exc
