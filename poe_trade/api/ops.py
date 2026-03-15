from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from poe_trade.analytics.reports import daily_report
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.strategy.alerts import ack_alert, list_alerts

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
        "auth_mode": "bearer_operator_token_or_cookie_session",
        "allowed_leagues": list(settings.api_league_allowlist),
        "primary_league": primary_league,
        "routes": {
            "healthz": "/healthz",
            "ops_contract": "/api/v1/ops/contract",
            "ops_services": "/api/v1/ops/services",
            "ops_dashboard": "/api/v1/ops/dashboard",
            "ops_messages": "/api/v1/ops/messages",
            "ops_scanner_summary": "/api/v1/ops/scanner/summary",
            "ops_scanner_recommendations": "/api/v1/ops/scanner/recommendations",
            "ops_alert_ack": "/api/v1/ops/alerts/{alert_id}/ack",
            "ops_analytics": "/api/v1/ops/analytics/{kind}",
            "service_action": "/api/v1/actions/services/{service_id}/{verb}",
            "ml_predict_one": "/api/v1/ml/leagues/{league}/predict-one",
            "stash_tabs": "/api/v1/stash/tabs?league={league}&realm={realm}",
            "stash_status": "/api/v1/stash/status?league={league}&realm={realm}",
            "auth_login": "/api/v1/auth/login",
            "auth_callback": "/api/v1/auth/callback",
            "auth_session": "/api/v1/auth/session",
            "auth_logout": "/api/v1/auth/logout",
            "ml_automation_status": "/api/v1/ml/leagues/{league}/automation/status",
            "ml_automation_history": "/api/v1/ml/leagues/{league}/automation/history",
        },
        "tabs": [
            "dashboard",
            "opportunities",
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
    opportunities = scanner_recommendations_payload(
        client,
        limit=3,
        sort_by="expected_profit_chaos",
    )["recommendations"]
    summary_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.id
        in {"clickhouse", "market_harvester", "scanner_worker", "ml_trainer", "api"}
    ]
    return {
        "services": services_payload(snapshots),
        "summary": {
            "running": sum(1 for s in summary_snapshots if s.status == "running"),
            "total": len(summary_snapshots),
            "errors": sum(1 for s in summary_snapshots if s.status == "error"),
            "criticalAlerts": len(critical),
        },
        "topOpportunities": opportunities,
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
        "SELECT strategy_id, count() AS recommendation_count "
        "FROM poe_trade.scanner_recommendations "
        "GROUP BY strategy_id ORDER BY strategy_id FORMAT JSONEachRow",
    )
    return {"rows": rows}


def scanner_summary_payload(client: ClickHouseClient) -> dict[str, Any]:
    rows = _safe_json_rows(
        client,
        "SELECT max(recorded_at) AS last_run_at, count() AS recommendation_count "
        "FROM poe_trade.scanner_recommendations FORMAT JSONEachRow",
    )
    if not rows:
        return {
            "status": "empty",
            "lastRunAt": None,
            "recommendationCount": 0,
            "freshnessMinutes": None,
        }
    row = rows[0]
    recommendation_count = int(row.get("recommendation_count") or 0)
    last_run_at = _as_iso_utc(row.get("last_run_at"))
    freshness_minutes = _freshness_minutes(last_run_at)
    if not last_run_at:
        status = "empty" if recommendation_count == 0 else "stale"
    elif freshness_minutes is None:
        status = "stale"
    elif freshness_minutes <= 15:
        status = "ok"
    else:
        status = "stale"
    return {
        "status": status,
        "lastRunAt": last_run_at,
        "recommendationCount": recommendation_count,
        "freshnessMinutes": freshness_minutes,
    }


def scanner_recommendations_payload(
    client: ClickHouseClient,
    *,
    limit: int = 50,
    sort_by: str = "recorded_at",
    min_confidence: float | None = None,
    league: str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    sort_key = _validate_scanner_sort(sort_by)
    if min_confidence is not None and not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    page_limit = max(1, min(limit, 200))
    fetch_limit = max(50, page_limit * 5)
    rows = _safe_json_rows(
        client,
        "SELECT scanner_run_id, strategy_id, league, item_or_market_key, why_it_fired, buy_plan, "
        "max_buy, transform_plan, exit_plan, execution_venue, expected_profit_chaos, expected_roi, expected_hold_time, confidence, evidence_snapshot, recorded_at "
        "FROM poe_trade.scanner_recommendations "
        "ORDER BY recorded_at DESC "
        f"LIMIT {fetch_limit} FORMAT JSONEachRow",
    )
    mapped: list[dict[str, Any]] = []
    for row in rows:
        row_league = str(row.get("league") or "")
        row_strategy = str(row.get("strategy_id") or "")
        row_confidence = _coerce_float(row.get("confidence"))
        if league and row_league != league:
            continue
        if strategy_id and row_strategy != strategy_id:
            continue
        if min_confidence is not None and (
            row_confidence is None or row_confidence < min_confidence
        ):
            continue

        recorded_at_iso = _as_iso_utc(row.get("recorded_at"))
        evidence_snapshot = _parse_evidence_snapshot(row.get("evidence_snapshot"))
        search_hint = _string_or_fallback(
            evidence_snapshot,
            "search_hint",
            str(row.get("item_or_market_key") or ""),
        )
        item_name = _string_or_fallback(evidence_snapshot, "item_name", search_hint)
        buy_plan = str(row.get("buy_plan") or "")
        transform_plan = str(row.get("transform_plan") or "")
        exit_plan = str(row.get("exit_plan") or "")
        execution_venue = str(row.get("execution_venue") or "")
        max_buy = row.get("max_buy")
        semantic_key = _semantic_key(
            league=row_league,
            strategy_id=row_strategy,
            execution_venue=execution_venue,
            search_hint=search_hint,
            item_name=item_name,
            buy_plan=buy_plan,
            max_buy=max_buy,
            transform_plan=transform_plan,
            exit_plan=exit_plan,
        )
        expected_hold_time = str(row.get("expected_hold_time") or "")
        expected_hold_minutes = _first_number(
            evidence_snapshot, "expected_hold_minutes"
        )
        if expected_hold_minutes is None:
            expected_hold_minutes = _parse_hold_minutes(expected_hold_time)
        freshness_minutes = _first_number(evidence_snapshot, "freshness_minutes")
        if freshness_minutes is None:
            freshness_minutes = _freshness_minutes(recorded_at_iso)

        mapped.append(
            {
                "scannerRunId": str(row.get("scanner_run_id") or ""),
                "strategyId": row_strategy,
                "league": row_league,
                "itemOrMarketKey": str(row.get("item_or_market_key") or ""),
                "semanticKey": semantic_key,
                "searchHint": search_hint,
                "itemName": item_name,
                "whyItFired": str(row.get("why_it_fired") or ""),
                "buyPlan": buy_plan,
                "maxBuy": max_buy,
                "transformPlan": transform_plan,
                "exitPlan": exit_plan,
                "executionVenue": execution_venue,
                "expectedProfitChaos": row.get("expected_profit_chaos"),
                "expectedRoi": row.get("expected_roi"),
                "expectedHoldTime": expected_hold_time,
                "expectedHoldMinutes": expected_hold_minutes,
                "confidence": row_confidence,
                "liquidityScore": _first_number(evidence_snapshot, "liquidity_score"),
                "freshnessMinutes": freshness_minutes,
                "goldCost": _first_number(evidence_snapshot, "gold_cost"),
                "evidenceSnapshot": evidence_snapshot,
                "recordedAt": recorded_at_iso,
            }
        )

    mapped.sort(
        key=lambda row: _sort_value(row, sort_key), reverse=_sort_desc(sort_key)
    )
    recommendations = mapped[:page_limit]
    primary_league = league or (
        str(recommendations[0].get("league") or "") if recommendations else ""
    )
    return {
        "recommendations": recommendations,
        "meta": {
            "source": "scanner_recommendations",
            "primaryLeague": primary_league,
            "generatedAt": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        },
    }


def ack_alert_payload(client: ClickHouseClient, *, alert_id: str) -> dict[str, Any]:
    if not alert_id:
        raise ValueError("alert_id is required")
    acked = ack_alert(client, alert_id=alert_id)
    return {"alertId": acked, "status": "acked"}


def analytics_alerts(client: ClickHouseClient) -> dict[str, Any]:
    return {"rows": list_alerts(client)}


def analytics_backtests(client: ClickHouseClient) -> dict[str, Any]:
    summary_rows = _safe_json_rows(
        client,
        "SELECT status, count() AS count FROM poe_trade.research_backtest_summary "
        "GROUP BY status ORDER BY status FORMAT JSONEachRow",
    )
    detail_rows = _safe_json_rows(
        client,
        "SELECT status, count() AS count FROM poe_trade.research_backtest_detail "
        "GROUP BY status ORDER BY status FORMAT JSONEachRow",
    )
    summary_total = sum(int(row.get("count") or 0) for row in summary_rows)
    detail_total = sum(int(row.get("count") or 0) for row in detail_rows)
    return {
        "rows": summary_rows,
        "summaryRows": summary_rows,
        "detailRows": detail_rows,
        "totals": {
            "summary": summary_total,
            "detail": detail_total,
        },
    }


def analytics_ml(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    return {"status": fetch_status(client, league=league)}


def analytics_report(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    report = daily_report(client, league=league)
    observed_rows = [
        _as_int(report.get("recommendations")),
        _as_int(report.get("alerts")),
        _as_int(report.get("journal_events")),
        _as_int(report.get("journal_positions")),
        _as_int(report.get("backtest_summary_rows")),
        _as_int(report.get("backtest_detail_rows")),
        _as_int(report.get("gold_currency_ref_hour_rows")),
        _as_int(report.get("gold_listing_ref_hour_rows")),
        _as_int(report.get("gold_liquidity_ref_hour_rows")),
        _as_int(report.get("gold_bulk_premium_hour_rows")),
        _as_int(report.get("gold_set_ref_hour_rows")),
    ]
    return {
        "status": "ok" if any(observed_rows) else "empty",
        "report": report,
    }


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


def _as_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _validate_scanner_sort(sort_by: str) -> str:
    allowed = {
        "recorded_at": "recordedAt",
        "expected_profit_chaos": "expectedProfitChaos",
        "expected_roi": "expectedRoi",
        "confidence": "confidence",
        "freshness_minutes": "freshnessMinutes",
    }
    key = allowed.get(sort_by)
    if key is None:
        raise ValueError(f"invalid sort field: {sort_by}")
    return key


def _sort_desc(sort_key: str) -> bool:
    return sort_key != "freshnessMinutes"


def _sort_value(row: dict[str, Any], sort_key: str) -> float:
    value = row.get(sort_key)
    if value is None:
        return float("-inf")
    if sort_key == "recordedAt":
        parsed = _parse_iso_utc(str(value))
        if parsed is None:
            return float("-inf")
        return parsed.timestamp()
    if isinstance(value, (int, float)):
        return float(value)
    parsed = _coerce_float(value)
    return parsed if parsed is not None else float("-inf")


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _parse_evidence_snapshot(value: object) -> dict[str, Any] | str:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return ""
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return value
        return parsed if isinstance(parsed, dict) else value
    return ""


def _string_or_fallback(
    evidence_snapshot: dict[str, Any] | str,
    key: str,
    fallback: str,
) -> str:
    if isinstance(evidence_snapshot, dict):
        value = evidence_snapshot.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return fallback


def _semantic_key(
    *,
    league: str,
    strategy_id: str,
    execution_venue: str,
    search_hint: str,
    item_name: str,
    buy_plan: str,
    max_buy: object,
    transform_plan: str,
    exit_plan: str,
) -> str:
    max_buy_value = _coerce_float(max_buy)
    max_buy_text = "null" if max_buy_value is None else f"{max_buy_value:.1f}"
    parts = [
        league,
        strategy_id,
        execution_venue,
        search_hint,
        item_name,
        buy_plan,
        max_buy_text,
        transform_plan,
        exit_plan,
    ]
    return "|".join(_normalize_semantic_text(value) for value in parts)


def _normalize_semantic_text(value: str) -> str:
    return " ".join(value.split()).strip().lower()


def _first_number(evidence_snapshot: dict[str, Any] | str, key: str) -> float | None:
    if not isinstance(evidence_snapshot, dict):
        return None
    return _coerce_float(evidence_snapshot.get(key))


def _parse_hold_minutes(value: str) -> float | None:
    if not value:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", value)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _as_iso_utc(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
    text = str(value).strip()
    if not text:
        return None
    parsed = _parse_iso_utc(text)
    if parsed is None:
        return text
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness_minutes(recorded_at_iso: str | None) -> float | None:
    if not recorded_at_iso:
        return None
    parsed = _parse_iso_utc(recorded_at_iso)
    if parsed is None:
        return None
    delta = datetime.now(timezone.utc) - parsed
    return round(max(0.0, delta.total_seconds() / 60.0), 2)
