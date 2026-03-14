from __future__ import annotations

import json
from typing import Any

from poe_trade.analytics.reports import daily_report
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.strategy.alerts import list_alerts

from .ml import fetch_predict_one, fetch_status
from .service_control import ServiceSnapshot


class OpsBackendUnavailable(RuntimeError):
    pass


def contract_payload(
    settings: Settings,
    *,
    visible_service_ids: list[str],
    controllable_service_ids: list[str],
) -> dict[str, Any]:
    primary_league = (
        settings.api_league_allowlist[0] if settings.api_league_allowlist else ""
    )
    return {
        "version": "v1",
        "auth_mode": "bearer_operator_token",
        "allowed_leagues": list(settings.api_league_allowlist),
        "primary_league": primary_league,
        "routes": {
            "healthz": "/healthz",
            "ops_contract": "/api/v1/ops/contract",
            "ops_services": "/api/v1/ops/services",
            "ops_dashboard": "/api/v1/ops/dashboard",
            "ops_messages": "/api/v1/ops/messages",
            "ops_analytics": "/api/v1/ops/analytics/{kind}",
            "service_action": "/api/v1/actions/services/{service_id}/{verb}",
            "ml_predict_one": "/api/v1/ml/leagues/{league}/predict-one",
            "stash_tabs": "/api/v1/stash/tabs?league={league}&realm={realm}",
        },
        "tabs": [
            "dashboard",
            "services",
            "analytics",
            "pricecheck",
            "stash",
            "messages",
        ],
        "visible_service_ids": visible_service_ids,
        "controllable_service_ids": controllable_service_ids,
    }


def services_payload(snapshots: list[ServiceSnapshot]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        rows.append(
            {
                "id": snapshot.id,
                "name": snapshot.name,
                "description": snapshot.description,
                "status": snapshot.status,
                "uptime": snapshot.uptime,
                "lastCrawl": snapshot.last_crawl,
                "rowsInDb": snapshot.rows_in_db,
                "containerInfo": snapshot.container_info,
                "type": snapshot.type,
                "allowedActions": list(snapshot.allowed_actions),
            }
        )
    return rows


def dashboard_payload(
    client: ClickHouseClient, snapshots: list[ServiceSnapshot]
) -> dict[str, Any]:
    messages = messages_payload(client)
    critical = [row for row in messages if row["severity"] == "critical"]
    return {
        "services": services_payload(snapshots),
        "summary": {
            "running": sum(1 for s in snapshots if s.status == "running"),
            "total": len(snapshots),
            "errors": sum(1 for s in snapshots if s.status == "error"),
            "criticalAlerts": len(critical),
        },
        "topOpportunities": critical[:3],
    }


def messages_payload(client: ClickHouseClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for alert in list_alerts(client)[:50]:
            rows.append(
                {
                    "id": str(alert.get("alert_id") or ""),
                    "timestamp": str(alert.get("recorded_at") or "").replace(" ", "T")
                    + "Z",
                    "severity": "critical"
                    if str(alert.get("status") or "") != "acked"
                    else "info",
                    "sourceModule": "scanner_alerts",
                    "message": str(
                        alert.get("item_or_market_key") or "alert triggered"
                    ),
                    "suggestedAction": "inspect strategy alert",
                }
            )
    except Exception:
        raise OpsBackendUnavailable("messages backend unavailable") from None

    try:
        ingest_payload = client.execute(
            "SELECT queue_key, status, last_ingest_at FROM poe_trade.poe_ingest_status "
            "ORDER BY last_ingest_at DESC LIMIT 10 FORMAT JSONEachRow"
        ).strip()
    except ClickHouseClientError:
        ingest_payload = ""
    if ingest_payload:
        for raw in ingest_payload.splitlines():
            row = json.loads(raw)
            status = str(row.get("status") or "")
            if "rate_limited" in status or "error" in status:
                rows.append(
                    {
                        "id": f"ingest-{row.get('queue_key')}-{row.get('last_ingest_at')}",
                        "timestamp": str(row.get("last_ingest_at") or "").replace(
                            " ", "T"
                        )
                        + "Z",
                        "severity": "warning",
                        "sourceModule": "ingestion",
                        "message": f"{row.get('queue_key')} status={status}",
                        "suggestedAction": "review runbook and restart harvester if needed",
                    }
                )
    rows.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
    return rows


def analytics_ingestion(client: ClickHouseClient) -> dict[str, Any]:
    return {
        "rows": _safe_json_rows(
            client,
            "SELECT queue_key, feed_kind, status, last_ingest_at "
            "FROM poe_trade.poe_ingest_status ORDER BY last_ingest_at DESC LIMIT 50 FORMAT JSONEachRow",
        )
    }


def analytics_scanner(client: ClickHouseClient) -> dict[str, Any]:
    rows = _safe_json_rows(
        client,
        "SELECT status, count() AS count FROM poe_trade.scanner_recommendations "
        "GROUP BY status ORDER BY status FORMAT JSONEachRow",
    )
    return {"rows": rows}


def analytics_alerts(client: ClickHouseClient) -> dict[str, Any]:
    return {"rows": list_alerts(client)}


def analytics_backtests(client: ClickHouseClient) -> dict[str, Any]:
    rows = _safe_json_rows(
        client,
        "SELECT status, count() AS count FROM poe_trade.research_backtest_summary "
        "GROUP BY status ORDER BY status FORMAT JSONEachRow",
    )
    return {"rows": rows}


def analytics_ml(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    return {"status": fetch_status(client, league=league)}


def analytics_report(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    return {"report": daily_report(client, league=league)}


def price_check_payload(
    client: ClickHouseClient,
    *,
    league: str,
    item_text: str,
) -> dict[str, Any]:
    prediction = fetch_predict_one(
        client,
        league=league,
        request_payload={
            "input_format": "poe-clipboard",
            "payload": item_text,
            "output_mode": "json",
        },
    )
    return {
        "predictedValue": prediction.get("price_p50"),
        "currency": "chaos",
        "confidence": prediction.get("confidence_percent") or 0.0,
        "comparables": [],
        "interval": {
            "p10": prediction.get("price_p10"),
            "p90": prediction.get("price_p90"),
        },
        "saleProbabilityPercent": prediction.get("sale_probability_percent"),
        "priceRecommendationEligible": prediction.get("price_recommendation_eligible"),
        "fallbackReason": prediction.get("fallback_reason"),
    }


def _safe_json_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise OpsBackendUnavailable("analytics backend unavailable") from exc
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]
