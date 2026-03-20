from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from poe_trade import __version__
from poe_trade.analytics.reports import daily_report
from poe_trade.config import constants
from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.ml import workflows as ml_workflows
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
        "deployment": deployment_payload(),
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
            "ops_search_suggestions": "/api/v1/ops/analytics/search-suggestions",
            "ops_search_history": "/api/v1/ops/analytics/search-history",
            "ops_pricing_outliers": "/api/v1/ops/analytics/pricing-outliers",
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
        sort_by="expected_profit_per_minute_chaos",
    )["recommendations"]
    summary_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.id
        in {"clickhouse", "market_harvester", "scanner_worker", "ml_trainer", "api"}
    ]
    return {
        "services": services_payload(snapshots),
        "deployment": deployment_payload(),
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


def deployment_payload() -> dict[str, Any]:
    return {
        "backendVersion": __version__,
        "backendSha": None,
        "frontendBuildSha": None,
        "recommendationContractVersion": constants.RECOMMENDATION_CONTRACT_VERSION,
        "contractMatchState": "unknown",
    }


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
    cursor: str | None = None,
) -> dict[str, Any]:
    sort_spec = _validate_scanner_sort(sort_by)
    if min_confidence is not None and min_confidence > 1:
        if min_confidence <= 100:
            min_confidence = min_confidence / 100.0
        else:
            raise ValueError("min_confidence must be between 0 and 1")
    if min_confidence is not None and not 0 <= min_confidence <= 1:
        raise ValueError("min_confidence must be between 0 and 1")
    page_limit = max(1, min(limit, 200))
    signature = _scanner_cursor_signature(
        sort_by=sort_spec["name"],
        league=league,
        strategy_id=strategy_id,
        min_confidence=min_confidence,
        limit=page_limit,
    )

    filters: list[str] = []
    if league:
        filters.append(f"league = {_quote_sql_string(league)}")
    if strategy_id:
        filters.append(f"strategy_id = {_quote_sql_string(strategy_id)}")
    if min_confidence is not None:
        filters.append(f"isNotNull(confidence) AND confidence >= {min_confidence!r}")
    if cursor:
        cursor_payload = _decode_scanner_cursor(cursor)
        _validate_scanner_cursor_signature(cursor_payload.get("signature"), signature)
        filters.append(_scanner_seek_predicate(sort_spec, cursor_payload.get("tuple")))

    where_clause = ""
    if filters:
        where_clause = " WHERE " + " AND ".join(f"({part})" for part in filters)

    order_clause = ", ".join(sort_spec["order_by"])
    query_limit = page_limit + 1
    expected_hold_minutes_sql = _scanner_expected_hold_minutes_sql(
        evidence_snapshot_expr="evidence_snapshot",
        expected_hold_time_expr="expected_hold_time",
    )
    expected_profit_per_minute_sql = _scanner_expected_profit_per_minute_sql(
        expected_profit_expr="expected_profit_chaos",
        expected_hold_minutes_expr=expected_hold_minutes_sql,
    )
    rows = _safe_json_rows_with_legacy_fallback(
        client,
        _scanner_recommendations_query(
            include_metadata=True,
            expected_hold_minutes_sql=expected_hold_minutes_sql,
            expected_profit_per_minute_sql=expected_profit_per_minute_sql,
            where_clause=where_clause,
            order_clause=order_clause,
            query_limit=query_limit,
        ),
        _scanner_recommendations_query(
            include_metadata=False,
            expected_hold_minutes_sql=expected_hold_minutes_sql,
            expected_profit_per_minute_sql=expected_profit_per_minute_sql,
            where_clause=where_clause,
            order_clause=order_clause,
            query_limit=query_limit,
        ),
    )
    has_more = len(rows) > page_limit
    visible_rows = rows[:page_limit]
    mapped: list[dict[str, Any]] = []
    for row in visible_rows:
        row_league = str(row.get("league") or "")
        row_strategy = str(row.get("strategy_id") or "")
        row_confidence = _coerce_float(row.get("confidence"))

        recorded_at_iso = _as_iso_utc(row.get("recorded_at"))
        evidence_snapshot = _parse_evidence_snapshot(row.get("evidence_snapshot"))
        ml_influence_score, ml_influence_reason = _ml_influence_from_snapshot(
            evidence_snapshot
        )
        effective_confidence = _effective_confidence(
            base_confidence=row_confidence,
            ml_influence_score=ml_influence_score,
        )
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
        expected_hold_minutes = _coerce_float(row.get("expected_hold_minutes"))
        expected_profit_per_minute_chaos = _coerce_float(
            row.get("expected_profit_per_minute_chaos")
        )
        freshness_minutes = _first_number(evidence_snapshot, "freshness_minutes")
        if freshness_minutes is None:
            freshness_minutes = _freshness_minutes(recorded_at_iso)

        mapped.append(
            {
                "scannerRunId": str(row.get("scanner_run_id") or ""),
                "strategyId": row_strategy,
                "league": row_league,
                "recommendationSource": _scanner_recommendation_source(row),
                "contractVersion": _scanner_contract_version(row),
                "producerVersion": _optional_string(row.get("producer_version")),
                "producerRunId": _scanner_producer_run_id(row),
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
                "expectedProfitPerMinuteChaos": expected_profit_per_minute_chaos,
                "expectedRoi": row.get("expected_roi"),
                "expectedHoldTime": expected_hold_time,
                "expectedHoldMinutes": expected_hold_minutes,
                "confidence": row_confidence,
                "effectiveConfidence": effective_confidence,
                "mlInfluenceScore": ml_influence_score,
                "mlInfluenceReason": ml_influence_reason,
                "liquidityScore": _first_number(evidence_snapshot, "liquidity_score"),
                "freshnessMinutes": freshness_minutes,
                "goldCost": _first_number(evidence_snapshot, "gold_cost"),
                "evidenceSnapshot": evidence_snapshot,
                "recordedAt": recorded_at_iso,
            }
        )

    recommendations = mapped
    next_cursor: str | None = None
    if has_more and recommendations:
        last_recommendation = recommendations[-1]
        cursor_tuple = _scanner_cursor_tuple(sort_spec, last_recommendation)
        next_cursor = _encode_scanner_cursor(
            {
                "signature": signature,
                "tuple": cursor_tuple,
            }
        )
    primary_league = league or (
        str(recommendations[0].get("league") or "") if recommendations else ""
    )
    return {
        "recommendations": recommendations,
        "meta": {
            "source": "scanner_recommendations",
            "primaryLeague": primary_league,
            "hasMore": has_more,
            "nextCursor": next_cursor,
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


def analytics_gold_diagnostics(
    client: ClickHouseClient, *, league: str
) -> dict[str, Any]:
    try:
        diagnostics_rows = _safe_json_rows(
            client,
            "SELECT mart_name, source_name, source_row_count, source_latest_at, "
            "source_distinct_league_count, source_blank_or_null_league_rows, gold_row_count, "
            "gold_latest_at, gold_distinct_league_count, gold_blank_or_null_league_rows, "
            "gold_freshness_minutes, source_to_gold_lag_minutes, diagnostic_state "
            "FROM poe_trade.v_gold_mart_diagnostics ORDER BY mart_name FORMAT JSONEachRow",
        )
    except OpsBackendUnavailable:
        return {
            "league": league,
            "summary": {
                "status": "unavailable",
                "martCount": 0,
                "problemMarts": 0,
                "goldEmptyMarts": 0,
                "staleMarts": 0,
                "missingLeagueMarts": 0,
            },
            "marts": [],
        }

    league_sql = _quote_sql_string(league)
    league_rows = _safe_json_rows(
        client,
        "SELECT mart_name, source_league_rows, gold_league_rows "
        "FROM ("
        "SELECT 'gold_currency_ref_hour' AS mart_name, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.v_cx_markets_enriched) AS source_league_rows, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.gold_currency_ref_hour) AS gold_league_rows "
        "UNION ALL "
        "SELECT 'gold_listing_ref_hour' AS mart_name, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.v_ps_items_enriched) AS source_league_rows, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.gold_listing_ref_hour) AS gold_league_rows "
        "UNION ALL "
        "SELECT 'gold_liquidity_ref_hour' AS mart_name, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.v_ps_items_enriched) AS source_league_rows, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.gold_liquidity_ref_hour) AS gold_league_rows "
        "UNION ALL "
        "SELECT 'gold_bulk_premium_hour' AS mart_name, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.v_ps_items_enriched) AS source_league_rows, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.gold_bulk_premium_hour) AS gold_league_rows "
        "UNION ALL "
        "SELECT 'gold_set_ref_hour' AS mart_name, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.v_ps_items_enriched) AS source_league_rows, "
        f"(SELECT countIf(ifNull(league, '') = {league_sql}) FROM poe_trade.gold_set_ref_hour) AS gold_league_rows"
        ") ORDER BY mart_name FORMAT JSONEachRow",
    )

    league_by_mart = {
        str(row.get("mart_name") or ""): {
            "source": _as_int(row.get("source_league_rows")),
            "gold": _as_int(row.get("gold_league_rows")),
        }
        for row in league_rows
    }

    marts: list[dict[str, Any]] = []
    problem_marts = 0
    stale_marts = 0
    gold_empty_marts = 0
    missing_league_marts = 0

    for row in diagnostics_rows:
        mart_name = str(row.get("mart_name") or "")
        diagnostic_state = str(row.get("diagnostic_state") or "")
        league_counts = league_by_mart.get(mart_name, {"source": 0, "gold": 0})
        source_league_rows = int(league_counts["source"])
        gold_league_rows = int(league_counts["gold"])

        if source_league_rows == 0 and gold_league_rows == 0:
            league_visibility = "absent_upstream"
        elif source_league_rows > 0 and gold_league_rows == 0:
            league_visibility = "missing_in_gold"
        else:
            league_visibility = "visible"

        if diagnostic_state != "ok":
            problem_marts += 1
        if diagnostic_state == "gold_stale_vs_source":
            stale_marts += 1
        if diagnostic_state == "gold_empty":
            gold_empty_marts += 1
        if league_visibility == "missing_in_gold":
            missing_league_marts += 1

        marts.append(
            {
                "martName": mart_name,
                "sourceName": str(row.get("source_name") or ""),
                "diagnosticState": diagnostic_state,
                "sourceRowCount": _as_int(row.get("source_row_count")),
                "goldRowCount": _as_int(row.get("gold_row_count")),
                "sourceLatestAt": _as_iso_utc(row.get("source_latest_at")),
                "goldLatestAt": _as_iso_utc(row.get("gold_latest_at")),
                "goldFreshnessMinutes": _coerce_float(
                    row.get("gold_freshness_minutes")
                ),
                "sourceToGoldLagMinutes": _coerce_float(
                    row.get("source_to_gold_lag_minutes")
                ),
                "sourceDistinctLeagueCount": _as_int(
                    row.get("source_distinct_league_count")
                ),
                "goldDistinctLeagueCount": _as_int(
                    row.get("gold_distinct_league_count")
                ),
                "sourceBlankLeagueRows": _as_int(
                    row.get("source_blank_or_null_league_rows")
                ),
                "goldBlankLeagueRows": _as_int(
                    row.get("gold_blank_or_null_league_rows")
                ),
                "leagueVisibility": league_visibility,
                "sourceLeagueRows": source_league_rows,
                "goldLeagueRows": gold_league_rows,
            }
        )

    if not marts:
        status = "empty"
    elif all(_as_int(row.get("sourceRowCount")) == 0 for row in marts):
        status = "source_empty"
    elif missing_league_marts > 0:
        status = "league_gap"
    elif stale_marts > 0:
        status = "stale"
    elif gold_empty_marts > 0:
        status = "gold_empty"
    elif problem_marts > 0:
        status = "degraded"
    else:
        status = "ok"

    return {
        "league": league,
        "summary": {
            "status": status,
            "martCount": len(marts),
            "problemMarts": problem_marts,
            "goldEmptyMarts": gold_empty_marts,
            "staleMarts": stale_marts,
            "missingLeagueMarts": missing_league_marts,
        },
        "marts": marts,
    }


def analytics_report(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    report = daily_report(client, league=league)
    gold_diagnostics = analytics_gold_diagnostics(client, league=league)
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
        "goldDiagnostics": gold_diagnostics,
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
    interval = prediction.get("interval")
    if not isinstance(interval, dict):
        interval = {
            "p10": prediction.get("price_p10"),
            "p90": prediction.get("price_p90"),
        }
    return {
        "predictedValue": prediction.get("predictedValue")
        or prediction.get("price_p50"),
        "fairValueP50": prediction.get("fairValueP50")
        or prediction.get("fair_value_p50")
        or prediction.get("price_p50"),
        "fastSale24hPrice": prediction.get("fastSale24hPrice")
        or prediction.get("fast_sale_24h_price"),
        "currency": prediction.get("currency") or "chaos",
        "confidence": prediction.get("confidence")
        or prediction.get("confidence_percent")
        or 0.0,
        "comparables": _price_check_comparables(
            client,
            league=league,
            item_text=item_text,
        ),
        "interval": interval,
        "saleProbabilityPercent": prediction.get("saleProbabilityPercent")
        or prediction.get("sale_probability_percent"),
        "priceRecommendationEligible": prediction.get("priceRecommendationEligible")
        if prediction.get("priceRecommendationEligible") is not None
        else prediction.get("price_recommendation_eligible"),
        "fallbackReason": prediction.get("fallbackReason")
        or prediction.get("fallback_reason"),
        "mlPredicted": prediction.get("mlPredicted")
        if prediction.get("mlPredicted") is not None
        else prediction.get("ml_predicted"),
        "predictionSource": prediction.get("predictionSource")
        or prediction.get("prediction_source"),
        "estimateTrust": prediction.get("estimateTrust")
        or prediction.get("estimate_trust"),
        "estimateWarning": prediction.get("estimateWarning")
        if prediction.get("estimateWarning") is not None
        else prediction.get("estimate_warning"),
    }


def analytics_search_suggestions(
    client: ClickHouseClient,
    *,
    query: str,
    limit: int = 8,
) -> dict[str, Any]:
    compact_query = query.strip()
    if not compact_query:
        return {"query": "", "suggestions": []}
    query_limit = max(1, min(limit, 20))
    label_expr = _search_item_label_sql()
    kind_expr = _search_item_kind_sql()
    rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT",
                f"{label_expr} AS item_name,",
                f"{kind_expr} AS item_kind,",
                "count() AS match_count",
                "FROM poe_trade.ml_price_dataset_v1",
                "WHERE normalized_price_chaos IS NOT NULL",
                "AND normalized_price_chaos > 0",
                f"AND positionCaseInsensitiveUTF8({label_expr}, {_quote_sql_string(compact_query)}) > 0",
                "GROUP BY item_name, item_kind",
                "ORDER BY match_count DESC, item_name ASC",
                f"LIMIT {query_limit} FORMAT JSONEachRow",
            ]
        ),
    )
    return {
        "query": compact_query,
        "suggestions": [
            {
                "itemName": str(row.get("item_name") or ""),
                "itemKind": str(row.get("item_kind") or "base_type"),
                "matchCount": _as_int(row.get("match_count")),
            }
            for row in rows
            if str(row.get("item_name") or "").strip()
        ],
    }


def analytics_search_history(
    client: ClickHouseClient,
    *,
    query_params: Mapping[str, list[str]],
    default_league: str | None = None,
) -> dict[str, Any]:
    compact_query = _first_query_param(query_params, "query")
    league = _first_query_param(query_params, "league") or (default_league or "")
    sort = _normalize_history_sort(_first_query_param(query_params, "sort"))
    order = _normalize_sort_order(_first_query_param(query_params, "order"))
    price_min = _query_param_float(query_params, "price_min")
    price_max = _query_param_float(query_params, "price_max")
    time_from = _query_param_datetime(query_params, "time_from")
    time_to = _query_param_datetime(query_params, "time_to")
    query_limit = _query_param_int(
        query_params, "limit", default=200, minimum=1, maximum=500
    )

    league_where = _history_where_clause(
        query=compact_query,
        league=None,
        price_min=None,
        price_max=None,
        time_from=None,
        time_to=None,
    )
    ranges_where = _history_where_clause(
        query=compact_query,
        league=league,
        price_min=None,
        price_max=None,
        time_from=None,
        time_to=None,
    )
    price_hist_where = _history_where_clause(
        query=compact_query,
        league=league,
        price_min=None,
        price_max=None,
        time_from=time_from,
        time_to=time_to,
    )
    time_hist_where = _history_where_clause(
        query=compact_query,
        league=league,
        price_min=price_min,
        price_max=price_max,
        time_from=None,
        time_to=None,
    )
    rows_where = _history_where_clause(
        query=compact_query,
        league=league,
        price_min=price_min,
        price_max=price_max,
        time_from=time_from,
        time_to=time_to,
    )

    league_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT league",
                "FROM poe_trade.ml_price_dataset_v1",
                league_where,
                "GROUP BY league",
                "ORDER BY league ASC FORMAT JSONEachRow",
            ]
        ),
    )
    range_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT",
                "min(normalized_price_chaos) AS min_price,",
                "max(normalized_price_chaos) AS max_price,",
                "min(as_of_ts) AS min_added_on,",
                "max(as_of_ts) AS max_added_on",
                "FROM poe_trade.ml_price_dataset_v1",
                ranges_where,
                "FORMAT JSONEachRow",
            ]
        ),
    )
    ranges = range_rows[0] if range_rows else {}
    min_price = _coerce_float(ranges.get("min_price"))
    max_price = _coerce_float(ranges.get("max_price"))
    min_added_on = _as_iso_utc(ranges.get("min_added_on"))
    max_added_on = _as_iso_utc(ranges.get("max_added_on"))

    price_bucket = _history_price_bucket_size(min_price, max_price)
    price_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT",
                f"floor(normalized_price_chaos / {price_bucket}) * {price_bucket} AS bucket_start,",
                f"floor(normalized_price_chaos / {price_bucket}) * {price_bucket} + {price_bucket} AS bucket_end,",
                "count() AS count",
                "FROM poe_trade.ml_price_dataset_v1",
                price_hist_where,
                "GROUP BY bucket_start, bucket_end",
                "ORDER BY bucket_start ASC FORMAT JSONEachRow",
            ]
        ),
    )

    time_bucket_seconds = _history_time_bucket_seconds(min_added_on, max_added_on)
    time_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT",
                f"toDateTime(intDiv(toUInt32(toUnixTimestamp(as_of_ts)), {time_bucket_seconds}) * {time_bucket_seconds}, 'UTC') AS bucket_start,",
                f"toDateTime(intDiv(toUInt32(toUnixTimestamp(as_of_ts)), {time_bucket_seconds}) * {time_bucket_seconds} + {time_bucket_seconds}, 'UTC') AS bucket_end,",
                "count() AS count",
                "FROM poe_trade.ml_price_dataset_v1",
                time_hist_where,
                "GROUP BY bucket_start, bucket_end",
                "ORDER BY bucket_start ASC FORMAT JSONEachRow",
            ]
        ),
    )

    label_expr = _search_item_label_sql()
    row_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT",
                f"{label_expr} AS item_name,",
                "league,",
                "normalized_price_chaos AS listed_price,",
                "as_of_ts AS added_on",
                "FROM poe_trade.ml_price_dataset_v1",
                rows_where,
                f"ORDER BY {_history_order_sql(sort, order)}",
                f"LIMIT {query_limit} FORMAT JSONEachRow",
            ]
        ),
    )
    return {
        "query": {
            "text": compact_query,
            "league": league,
            "sort": sort,
            "order": order,
        },
        "filters": {
            "leagueOptions": [
                str(row.get("league") or "")
                for row in league_rows
                if str(row.get("league") or "").strip()
            ],
            "price": {
                "min": min_price if min_price is not None else 0.0,
                "max": max_price if max_price is not None else 0.0,
            },
            "datetime": {
                "min": min_added_on,
                "max": max_added_on,
            },
        },
        "histograms": {
            "price": [
                {
                    "bucketStart": _coerce_float(row.get("bucket_start")) or 0.0,
                    "bucketEnd": _coerce_float(row.get("bucket_end")) or 0.0,
                    "count": _as_int(row.get("count")),
                }
                for row in price_rows
            ],
            "datetime": [
                {
                    "bucketStart": _as_iso_utc(row.get("bucket_start")),
                    "bucketEnd": _as_iso_utc(row.get("bucket_end")),
                    "count": _as_int(row.get("count")),
                }
                for row in time_rows
            ],
        },
        "rows": [
            {
                "itemName": str(row.get("item_name") or ""),
                "league": str(row.get("league") or ""),
                "listedPrice": _coerce_float(row.get("listed_price")) or 0.0,
                "currency": "chaos",
                "addedOn": _as_iso_utc(row.get("added_on")),
            }
            for row in row_rows
        ],
    }


def analytics_pricing_outliers(
    client: ClickHouseClient,
    *,
    query_params: Mapping[str, list[str]],
    default_league: str | None = None,
) -> dict[str, Any]:
    league = _first_query_param(query_params, "league") or (default_league or "")
    limit = _query_param_int(query_params, "limit", default=100, minimum=1, maximum=500)
    minimum_support = _query_param_int(
        query_params, "min_total", default=20, minimum=1, maximum=5000
    )
    sort = _normalize_outlier_sort(_first_query_param(query_params, "sort"))
    order = _normalize_sort_order(
        _first_query_param(query_params, "order"), default="desc"
    )
    query_text = _first_query_param(query_params, "query")
    league_clause = _outlier_league_clause(league)
    item_label_expr = _search_item_label_sql("d")
    summary_filter = ""
    if query_text:
        quoted_query = _quote_sql_string(query_text)
        summary_filter = (
            "WHERE positionCaseInsensitiveUTF8(item_name, "
            + quoted_query
            + ") > 0 OR positionCaseInsensitiveUTF8(affix_analyzed, "
            + quoted_query
            + ") > 0"
        )
    summary_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "WITH base AS (",
                "SELECT",
                f"{item_label_expr} AS item_name,",
                "d.base_type AS base_type,",
                "ifNull(d.rarity, '') AS rarity,",
                "d.item_id AS item_id,",
                "d.as_of_ts AS as_of_ts,",
                "toFloat64(d.normalized_price_chaos) AS listed_price",
                "FROM poe_trade.ml_price_dataset_v1 AS d",
                f"WHERE {league_clause}",
                "AND d.normalized_price_chaos IS NOT NULL",
                "AND d.normalized_price_chaos > 0",
                "),",
                "item_thresholds AS (",
                "SELECT item_name, base_type, rarity,",
                "quantileTDigest(0.1)(listed_price) AS p10,",
                "quantileTDigest(0.5)(listed_price) AS median,",
                "quantileTDigest(0.9)(listed_price) AS p90,",
                "count() AS items_total",
                "FROM base",
                "GROUP BY item_name, base_type, rarity",
                f"HAVING items_total >= {minimum_support}",
                "),",
                "item_weekly AS (",
                "SELECT t.item_name, t.base_type, t.rarity, toStartOfWeek(b.as_of_ts) AS week_start,",
                "countIf(b.listed_price <= t.p10) AS too_cheap_count",
                "FROM base AS b",
                "INNER JOIN item_thresholds AS t ON b.item_name = t.item_name AND b.base_type = t.base_type AND b.rarity = t.rarity",
                "GROUP BY t.item_name, t.base_type, t.rarity, week_start",
                "),",
                "item_rows AS (",
                "SELECT t.item_name AS item_name, '' AS affix_analyzed, t.p10 AS p10, t.median AS median, t.p90 AS p90,",
                "round(avg(w.too_cheap_count), 4) AS items_per_week, t.items_total AS items_total, 'item' AS analysis_level",
                "FROM item_thresholds AS t",
                "LEFT JOIN item_weekly AS w ON t.item_name = w.item_name AND t.base_type = w.base_type AND t.rarity = w.rarity",
                "GROUP BY t.item_name, t.base_type, t.rarity, t.p10, t.median, t.p90, t.items_total",
                "),",
                "affix_base AS (",
                "SELECT b.item_name, b.base_type, b.rarity, b.as_of_ts, b.listed_price,",
                "coalesce(nullIf(c.mod_text, ''), nullIf(t.mod_token, '')) AS affix_analyzed",
                "FROM base AS b",
                f"INNER JOIN poe_trade.ml_item_mod_tokens_v1 AS t ON assumeNotNull(b.item_id) = t.item_id AND t.league = {_quote_sql_string(league)}",
                "LEFT JOIN poe_trade.ml_mod_catalog_v1 AS c ON c.mod_token = t.mod_token",
                "WHERE b.item_id IS NOT NULL",
                "),",
                "affix_thresholds AS (",
                "SELECT item_name, base_type, rarity, affix_analyzed,",
                "quantileTDigest(0.1)(listed_price) AS p10,",
                "quantileTDigest(0.5)(listed_price) AS median,",
                "quantileTDigest(0.9)(listed_price) AS p90,",
                "count() AS items_total",
                "FROM affix_base",
                "WHERE affix_analyzed IS NOT NULL",
                "GROUP BY item_name, base_type, rarity, affix_analyzed",
                f"HAVING items_total >= {minimum_support}",
                "),",
                "affix_weekly AS (",
                "SELECT t.item_name, t.base_type, t.rarity, t.affix_analyzed, toStartOfWeek(a.as_of_ts) AS week_start,",
                "countIf(a.listed_price <= t.p10) AS too_cheap_count",
                "FROM affix_base AS a",
                "INNER JOIN affix_thresholds AS t ON a.item_name = t.item_name AND a.base_type = t.base_type AND a.rarity = t.rarity AND a.affix_analyzed = t.affix_analyzed",
                "GROUP BY t.item_name, t.base_type, t.rarity, t.affix_analyzed, week_start",
                "),",
                "affix_rows AS (",
                "SELECT t.item_name AS item_name, t.affix_analyzed AS affix_analyzed, t.p10 AS p10, t.median AS median, t.p90 AS p90,",
                "round(avg(w.too_cheap_count), 4) AS items_per_week, t.items_total AS items_total, 'affix' AS analysis_level",
                "FROM affix_thresholds AS t",
                "LEFT JOIN affix_weekly AS w ON t.item_name = w.item_name AND t.base_type = w.base_type AND t.rarity = w.rarity AND t.affix_analyzed = w.affix_analyzed",
                "GROUP BY t.item_name, t.base_type, t.rarity, t.affix_analyzed, t.p10, t.median, t.p90, t.items_total",
                ")",
                "SELECT * FROM (SELECT * FROM item_rows UNION ALL SELECT * FROM affix_rows)",
                summary_filter,
                f"ORDER BY {_outlier_order_sql(sort, order)}",
                f"LIMIT {limit} FORMAT JSONEachRow",
            ]
        ),
    )
    weekly_rows = _safe_json_rows(
        client,
        " ".join(
            [
                "WITH base AS (",
                "SELECT",
                f"{item_label_expr} AS item_name,",
                "d.base_type AS base_type,",
                "ifNull(d.rarity, '') AS rarity,",
                "d.as_of_ts AS as_of_ts,",
                "toFloat64(d.normalized_price_chaos) AS listed_price",
                "FROM poe_trade.ml_price_dataset_v1 AS d",
                f"WHERE {league_clause}",
                "AND d.normalized_price_chaos IS NOT NULL",
                "AND d.normalized_price_chaos > 0",
                "),",
                "item_thresholds AS (",
                "SELECT item_name, base_type, rarity,",
                "quantileTDigest(0.1)(listed_price) AS p10,",
                "count() AS items_total",
                "FROM base",
                "GROUP BY item_name, base_type, rarity",
                f"HAVING items_total >= {minimum_support}",
                ")",
                "SELECT toStartOfWeek(b.as_of_ts) AS week_start, countIf(b.listed_price <= t.p10) AS too_cheap_count",
                "FROM base AS b",
                "INNER JOIN item_thresholds AS t ON b.item_name = t.item_name AND b.base_type = t.base_type AND b.rarity = t.rarity",
                "GROUP BY week_start",
                "ORDER BY week_start ASC FORMAT JSONEachRow",
            ]
        ),
    )
    return {
        "query": {
            "league": league,
            "sort": sort,
            "order": order,
            "minTotal": minimum_support,
        },
        "rows": [
            {
                "itemName": str(row.get("item_name") or ""),
                "affixAnalyzed": str(row.get("affix_analyzed") or ""),
                "p10": _coerce_float(row.get("p10")) or 0.0,
                "median": _coerce_float(row.get("median")) or 0.0,
                "p90": _coerce_float(row.get("p90")) or 0.0,
                "itemsPerWeek": _coerce_float(row.get("items_per_week")) or 0.0,
                "itemsTotal": _as_int(row.get("items_total")),
                "analysisLevel": str(row.get("analysis_level") or "item"),
            }
            for row in summary_rows
        ],
        "weekly": [
            {
                "weekStart": _as_iso_utc(row.get("week_start")),
                "tooCheapCount": _as_int(row.get("too_cheap_count")),
            }
            for row in weekly_rows
        ],
    }


def _price_check_comparables(
    client: ClickHouseClient,
    *,
    league: str,
    item_text: str,
) -> list[dict[str, Any]]:
    try:
        parsed = ml_workflows._parse_clipboard_item(item_text)
    except ValueError:
        return []
    base_type = str(parsed.get("base_type") or "").strip()
    if not base_type:
        return []
    clauses = [
        f"league = {_quote_sql_string(league)}",
        "normalized_price_chaos IS NOT NULL",
        "normalized_price_chaos > 0",
        f"base_type = {_quote_sql_string(base_type)}",
    ]
    rarity = str(parsed.get("rarity") or "").strip()
    if rarity:
        clauses.append(f"ifNull(rarity, '') = {_quote_sql_string(rarity)}")
    item_name = str(parsed.get("item_name") or "").strip()
    if rarity == "Unique" and item_name:
        clauses.append(f"nullIf(item_name, '') = {_quote_sql_string(item_name)}")
    label_expr = _search_item_label_sql()
    rows = _safe_json_rows(
        client,
        " ".join(
            [
                "SELECT",
                f"{label_expr} AS item_name,",
                "league,",
                "normalized_price_chaos AS listed_price,",
                "as_of_ts AS added_on",
                "FROM poe_trade.ml_price_dataset_v1",
                "WHERE " + " AND ".join(clauses),
                "ORDER BY as_of_ts DESC",
                "LIMIT 8 FORMAT JSONEachRow",
            ]
        ),
    )
    return [
        {
            "name": str(row.get("item_name") or base_type),
            "price": _coerce_float(row.get("listed_price")) or 0.0,
            "currency": "chaos",
            "league": str(row.get("league") or league),
            "addedOn": _as_iso_utc(row.get("added_on")),
        }
        for row in rows
    ]


def _safe_json_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise OpsBackendUnavailable("analytics backend unavailable") from exc
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _safe_json_rows_with_legacy_fallback(
    client: ClickHouseClient,
    query: str,
    legacy_query: str,
) -> list[dict[str, Any]]:
    try:
        return _safe_json_rows(client, query)
    except OpsBackendUnavailable as exc:
        cause = exc.__cause__
        if not isinstance(
            cause, ClickHouseClientError
        ) or not _is_missing_metadata_column_error(cause):
            raise
        return _safe_json_rows(client, legacy_query)


def _scanner_recommendations_query(
    *,
    include_metadata: bool,
    expected_hold_minutes_sql: str,
    expected_profit_per_minute_sql: str,
    where_clause: str,
    order_clause: str,
    query_limit: int,
) -> str:
    metadata_columns = ""
    if include_metadata:
        metadata_columns = "recommendation_source, recommendation_contract_version, producer_version, producer_run_id, "
    return (
        "SELECT scanner_run_id, strategy_id, league, "
        + metadata_columns
        + "item_or_market_key, why_it_fired, buy_plan, max_buy, transform_plan, exit_plan, "
        + "execution_venue, expected_profit_chaos, expected_roi, expected_hold_time, "
        + "expected_hold_minutes, expected_profit_per_minute_chaos, confidence, evidence_snapshot, recorded_at "
        + "FROM ("
        + "SELECT scanner_run_id, strategy_id, league, "
        + metadata_columns
        + "item_or_market_key, why_it_fired, buy_plan, max_buy, transform_plan, exit_plan, execution_venue, expected_profit_chaos, expected_roi, expected_hold_time, confidence, evidence_snapshot, recorded_at, "
        + f"{expected_hold_minutes_sql} AS expected_hold_minutes, "
        + f"{expected_profit_per_minute_sql} AS expected_profit_per_minute_chaos "
        + "FROM poe_trade.scanner_recommendations"
        + ") "
        + f"{where_clause} "
        + f"ORDER BY {order_clause} "
        + f"LIMIT {query_limit} FORMAT JSONEachRow"
    )


def _is_missing_metadata_column_error(exc: ClickHouseClientError) -> bool:
    message = str(exc).lower()
    return "column" in message and ("unknown" in message or "missing" in message)


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


def _quote_sql_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def _first_query_param(query_params: Mapping[str, list[str]], key: str) -> str:
    values = query_params.get(key) or []
    if not values:
        return ""
    return str(values[0] or "").strip()


def _query_param_float(query_params: Mapping[str, list[str]], key: str) -> float | None:
    raw = _first_query_param(query_params, key)
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _query_param_int(
    query_params: Mapping[str, list[str]],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw = _first_query_param(query_params, key)
    if not raw:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _query_param_datetime(
    query_params: Mapping[str, list[str]], key: str
) -> str | None:
    raw = _first_query_param(query_params, key)
    if not raw:
        return None
    parsed = _parse_iso_utc(raw)
    if parsed is None:
        return None
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _search_item_label_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        "if("
        f"lowerUTF8(ifNull({prefix}rarity, '')) = 'unique' AND nullIf({prefix}item_name, '') IS NOT NULL, "
        f"nullIf({prefix}item_name, ''), {prefix}base_type"
        ")"
    )


def _search_item_kind_sql(alias: str = "") -> str:
    prefix = f"{alias}." if alias else ""
    return (
        "if("
        f"lowerUTF8(ifNull({prefix}rarity, '')) = 'unique' AND nullIf({prefix}item_name, '') IS NOT NULL, "
        "'unique_name', 'base_type'"
        ")"
    )


def _history_where_clause(
    *,
    query: str,
    league: str | None,
    price_min: float | None,
    price_max: float | None,
    time_from: str | None,
    time_to: str | None,
) -> str:
    label_expr = _search_item_label_sql()
    clauses = ["normalized_price_chaos IS NOT NULL", "normalized_price_chaos > 0"]
    compact_query = query.strip()
    if compact_query:
        clauses.append(
            f"positionCaseInsensitiveUTF8({label_expr}, {_quote_sql_string(compact_query)}) > 0"
        )
    compact_league = (league or "").strip()
    if compact_league and compact_league.lower() != "all":
        clauses.append(f"league = {_quote_sql_string(compact_league)}")
    if price_min is not None:
        clauses.append(f"normalized_price_chaos >= {price_min}")
    if price_max is not None:
        clauses.append(f"normalized_price_chaos <= {price_max}")
    if time_from is not None:
        clauses.append(f"as_of_ts >= toDateTime({_quote_sql_string(time_from)}, 'UTC')")
    if time_to is not None:
        clauses.append(f"as_of_ts <= toDateTime({_quote_sql_string(time_to)}, 'UTC')")
    return "WHERE " + " AND ".join(clauses)


def _normalize_sort_order(value: str, *, default: str = "asc") -> str:
    normalized = value.lower().strip() if value else default
    if normalized not in {"asc", "desc"}:
        return default
    return normalized


def _normalize_history_sort(value: str) -> str:
    if value in {"item_name", "league", "listed_price", "added_on"}:
        return value
    return "added_on"


def _history_order_sql(sort: str, order: str) -> str:
    column = {
        "item_name": "item_name",
        "league": "league",
        "listed_price": "listed_price",
        "added_on": "added_on",
    }.get(sort, "added_on")
    return f"{column} {order.upper()}"


def _history_price_bucket_size(min_price: float | None, max_price: float | None) -> str:
    if min_price is None or max_price is None or max_price <= min_price:
        return "1"
    bucket = max((max_price - min_price) / 20.0, 1.0)
    return _float_sql(bucket)


def _history_time_bucket_seconds(
    min_added_on: str | None, max_added_on: str | None
) -> int:
    if not min_added_on or not max_added_on:
        return 86400
    start = _parse_iso_utc(min_added_on)
    end = _parse_iso_utc(max_added_on)
    if start is None or end is None or end <= start:
        return 86400
    bucket = int((end - start).total_seconds() / 20.0)
    return max(3600, bucket)


def _normalize_outlier_sort(value: str) -> str:
    if value in {
        "item_name",
        "affix_analyzed",
        "p10",
        "median",
        "p90",
        "items_per_week",
        "items_total",
    }:
        return value
    return "items_total"


def _outlier_order_sql(sort: str, order: str) -> str:
    column = {
        "item_name": "item_name",
        "affix_analyzed": "affix_analyzed",
        "p10": "p10",
        "median": "median",
        "p90": "p90",
        "items_per_week": "items_per_week",
        "items_total": "items_total",
    }.get(sort, "items_total")
    return f"{column} {order.upper()}, item_name ASC"


def _outlier_league_clause(league: str | None) -> str:
    compact_league = (league or "").strip()
    if not compact_league or compact_league.lower() == "all":
        return "1"
    return f"d.league = {_quote_sql_string(compact_league)}"


def _float_sql(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _scanner_expected_hold_minutes_sql(
    *,
    evidence_snapshot_expr: str,
    expected_hold_time_expr: str,
) -> str:
    snapshot_numeric_minutes = (
        f"if(JSONExtractFloat({evidence_snapshot_expr}, 'expected_hold_minutes') > 0, "
        f"JSONExtractFloat({evidence_snapshot_expr}, 'expected_hold_minutes'), NULL)"
    )
    snapshot_string_minutes = (
        "if("
        f"toFloat64OrNull(JSONExtractString({evidence_snapshot_expr}, 'expected_hold_minutes')) > 0, "
        f"toFloat64OrNull(JSONExtractString({evidence_snapshot_expr}, 'expected_hold_minutes')), "
        "NULL)"
    )
    parsed_hold_amount = (
        f"toFloat64OrNull(extract(lowerUTF8(ifNull({expected_hold_time_expr}, '')), "
        "'([-+]?[0-9]+(?:\\.[0-9]+)?)'))"
    )
    parsed_hold_unit = (
        f"extract(lowerUTF8(ifNull({expected_hold_time_expr}, '')), '([mh])\\s*$')"
    )
    parsed_hold_minutes = (
        "multiIf("
        f"isNull({parsed_hold_amount}), NULL, "
        f"{parsed_hold_amount} <= 0, NULL, "
        f"{parsed_hold_unit} = 'h', {parsed_hold_amount} * 60.0, "
        f"{parsed_hold_unit} = 'm', {parsed_hold_amount}, "
        "NULL)"
    )
    return (
        "coalesce("
        f"{snapshot_numeric_minutes}, "
        f"{snapshot_string_minutes}, "
        f"{parsed_hold_minutes}"
        ")"
    )


def _scanner_expected_profit_per_minute_sql(
    *,
    expected_profit_expr: str,
    expected_hold_minutes_expr: str,
) -> str:
    return (
        "if("
        f"isNull({expected_profit_expr}) OR isNull({expected_hold_minutes_expr}) OR "
        f"{expected_hold_minutes_expr} <= 0, NULL, "
        f"{expected_profit_expr} / {expected_hold_minutes_expr}"
        ")"
    )


def _validate_scanner_sort(sort_by: str) -> dict[str, Any]:
    key = _SCANNER_SORT_SPECS.get(sort_by)
    if key is None:
        raise ValueError(f"invalid sort field: {sort_by}")
    return key


_SCANNER_CURSOR_TIE_BREAK_FIELDS = (
    "recordedAt",
    "scannerRunId",
    "strategyId",
    "itemOrMarketKey",
    "buyPlan",
    "transformPlan",
    "exitPlan",
    "executionVenue",
)


_SCANNER_SORT_SPECS: dict[str, dict[str, Any]] = {
    "recorded_at": {
        "name": "recorded_at",
        "response_key": "recordedAt",
        "cursor_type": "datetime",
        "sql_primary": "recorded_at",
        "sql_primary_rank": "if(isNull(recorded_at), 0, 1)",
        "sql_primary_value": "recorded_at",
        "order_by": [
            "if(isNull(recorded_at), 0, 1) DESC",
            "recorded_at DESC",
            "recorded_at DESC",
            "scanner_run_id DESC",
            "strategy_id DESC",
            "item_or_market_key DESC",
            "buy_plan DESC",
            "transform_plan DESC",
            "exit_plan DESC",
            "execution_venue DESC",
        ],
    },
    "expected_profit_chaos": {
        "name": "expected_profit_chaos",
        "response_key": "expectedProfitChaos",
        "cursor_type": "float",
        "sql_primary": "expected_profit_chaos",
        "sql_primary_rank": "if(isNull(expected_profit_chaos), 0, 1)",
        "sql_primary_value": "expected_profit_chaos",
        "order_by": [
            "if(isNull(expected_profit_chaos), 0, 1) DESC",
            "expected_profit_chaos DESC",
            "recorded_at DESC",
            "scanner_run_id DESC",
            "strategy_id DESC",
            "item_or_market_key DESC",
            "buy_plan DESC",
            "transform_plan DESC",
            "exit_plan DESC",
            "execution_venue DESC",
        ],
    },
    "expected_roi": {
        "name": "expected_roi",
        "response_key": "expectedRoi",
        "cursor_type": "float",
        "sql_primary": "expected_roi",
        "sql_primary_rank": "if(isNull(expected_roi), 0, 1)",
        "sql_primary_value": "expected_roi",
        "order_by": [
            "if(isNull(expected_roi), 0, 1) DESC",
            "expected_roi DESC",
            "recorded_at DESC",
            "scanner_run_id DESC",
            "strategy_id DESC",
            "item_or_market_key DESC",
            "buy_plan DESC",
            "transform_plan DESC",
            "exit_plan DESC",
            "execution_venue DESC",
        ],
    },
    "expected_profit_per_minute_chaos": {
        "name": "expected_profit_per_minute_chaos",
        "response_key": "expectedProfitPerMinuteChaos",
        "cursor_type": "float",
        "sql_primary": "expected_profit_per_minute_chaos",
        "sql_primary_rank": "if(isNull(expected_profit_per_minute_chaos), 0, 1)",
        "sql_primary_value": "expected_profit_per_minute_chaos",
        "order_by": [
            "if(isNull(expected_profit_per_minute_chaos), 0, 1) DESC",
            "expected_profit_per_minute_chaos DESC",
            "recorded_at DESC",
            "scanner_run_id DESC",
            "strategy_id DESC",
            "item_or_market_key DESC",
            "buy_plan DESC",
            "transform_plan DESC",
            "exit_plan DESC",
            "execution_venue DESC",
        ],
    },
    "confidence": {
        "name": "confidence",
        "response_key": "confidence",
        "cursor_type": "float",
        "sql_primary": "confidence",
        "sql_primary_rank": "if(isNull(confidence), 0, 1)",
        "sql_primary_value": "confidence",
        "order_by": [
            "if(isNull(confidence), 0, 1) DESC",
            "confidence DESC",
            "recorded_at DESC",
            "scanner_run_id DESC",
            "strategy_id DESC",
            "item_or_market_key DESC",
            "buy_plan DESC",
            "transform_plan DESC",
            "exit_plan DESC",
            "execution_venue DESC",
        ],
    },
    "freshness_minutes": {
        "name": "freshness_minutes",
        "response_key": "recordedAt",
        "cursor_type": "datetime",
        "sql_primary": "recorded_at",
        "sql_primary_rank": "if(isNull(recorded_at), 0, 1)",
        "sql_primary_value": "recorded_at",
        "order_by": [
            "if(isNull(recorded_at), 0, 1) DESC",
            "recorded_at DESC",
            "recorded_at DESC",
            "scanner_run_id DESC",
            "strategy_id DESC",
            "item_or_market_key DESC",
            "buy_plan DESC",
            "transform_plan DESC",
            "exit_plan DESC",
            "execution_venue DESC",
        ],
    },
}


def _scanner_cursor_signature(
    *,
    sort_by: str,
    league: str | None,
    strategy_id: str | None,
    min_confidence: float | None,
    limit: int,
) -> dict[str, Any]:
    return {
        "sort": sort_by,
        "league": league,
        "strategy_id": strategy_id,
        "min_confidence": min_confidence,
        "limit": limit,
    }


def _scanner_cursor_primary_value(
    sort_spec: dict[str, Any], recommendation: dict[str, Any]
) -> float | str | None:
    response_key = str(sort_spec["response_key"])
    value = recommendation.get(response_key)
    cursor_type = str(sort_spec["cursor_type"])
    if cursor_type == "float":
        return _coerce_float(value)
    if cursor_type == "datetime":
        if value is None:
            return None
        text = str(value)
        return text or None
    raise ValueError("unsupported scanner cursor type")


def _scanner_cursor_tuple(
    sort_spec: dict[str, Any], recommendation: dict[str, Any]
) -> dict[str, Any]:
    return {
        "primary": _scanner_cursor_primary_value(sort_spec, recommendation),
        "recorded_at": recommendation.get("recordedAt"),
        "scanner_run_id": recommendation.get("scannerRunId"),
        "strategy_id": recommendation.get("strategyId"),
        "item_or_market_key": recommendation.get("itemOrMarketKey"),
        "buy_plan": recommendation.get("buyPlan"),
        "transform_plan": recommendation.get("transformPlan"),
        "exit_plan": recommendation.get("exitPlan"),
        "execution_venue": recommendation.get("executionVenue"),
    }


def _encode_scanner_cursor(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_scanner_cursor(cursor: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(cursor.encode("ascii"), altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("invalid scanner cursor") from None
    if not isinstance(payload, dict):
        raise ValueError("invalid scanner cursor")
    if not isinstance(payload.get("signature"), dict):
        raise ValueError("invalid scanner cursor")
    if not isinstance(payload.get("tuple"), dict):
        raise ValueError("invalid scanner cursor")
    return payload


def _validate_scanner_cursor_signature(
    actual: object,
    expected: dict[str, Any],
) -> None:
    if not isinstance(actual, dict):
        raise ValueError("invalid scanner cursor")
    if actual != expected:
        raise ValueError("scanner cursor does not match active query")


def _scanner_datetime_literal(value: object) -> str:
    text = _as_iso_utc(value)
    if text is None:
        raise ValueError("invalid scanner cursor")
    parsed = _parse_iso_utc(text)
    if parsed is None:
        raise ValueError("invalid scanner cursor")
    normalized = parsed.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return f"toDateTime64({_quote_sql_string(normalized)}, 3, 'UTC')"


def _scanner_float_literal(value: object) -> str:
    parsed = _coerce_float(value)
    if parsed is None:
        raise ValueError("invalid scanner cursor")
    return repr(parsed)


def _scanner_string_literal(value: object) -> str:
    text = "" if value is None else str(value)
    return _quote_sql_string(text)


def _scanner_seek_predicate(sort_spec: dict[str, Any], raw_tuple: object) -> str:
    if not isinstance(raw_tuple, dict):
        raise ValueError("invalid scanner cursor")
    required_fields = {"primary"} | {
        key
        for key in (
            "recorded_at",
            "scanner_run_id",
            "strategy_id",
            "item_or_market_key",
            "buy_plan",
            "transform_plan",
            "exit_plan",
            "execution_venue",
        )
    }
    if set(raw_tuple.keys()) != required_fields:
        raise ValueError("invalid scanner cursor")

    primary = raw_tuple.get("primary")
    cursor_type = str(sort_spec["cursor_type"])
    if primary is None:
        primary_rank_literal = "0"
        primary_value_literal = "NULL"
    else:
        primary_rank_literal = "1"
        if cursor_type == "float":
            primary_value_literal = _scanner_float_literal(primary)
        elif cursor_type == "datetime":
            primary_value_literal = _scanner_datetime_literal(primary)
        else:
            raise ValueError("invalid scanner cursor")

    tuple_expr = (
        f"({sort_spec['sql_primary_rank']}, {sort_spec['sql_primary_value']}, "
        "recorded_at, scanner_run_id, strategy_id, item_or_market_key, buy_plan, "
        "transform_plan, exit_plan, execution_venue)"
    )
    tuple_cursor = (
        f"({primary_rank_literal}, {primary_value_literal}, "
        f"{_scanner_datetime_literal(raw_tuple.get('recorded_at'))}, "
        f"{_scanner_string_literal(raw_tuple.get('scanner_run_id'))}, "
        f"{_scanner_string_literal(raw_tuple.get('strategy_id'))}, "
        f"{_scanner_string_literal(raw_tuple.get('item_or_market_key'))}, "
        f"{_scanner_string_literal(raw_tuple.get('buy_plan'))}, "
        f"{_scanner_string_literal(raw_tuple.get('transform_plan'))}, "
        f"{_scanner_string_literal(raw_tuple.get('exit_plan'))}, "
        f"{_scanner_string_literal(raw_tuple.get('execution_venue'))})"
    )
    return f"{tuple_expr} < {tuple_cursor}"


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


def _optional_string(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _scanner_recommendation_source(row: dict[str, Any]) -> str:
    return (
        _optional_string(row.get("recommendation_source"))
        or constants.DEFAULT_RECOMMENDATION_SOURCE
    )


def _scanner_contract_version(row: dict[str, Any]) -> int:
    value = _as_int(row.get("recommendation_contract_version"))
    if value > 0:
        return value
    return constants.LEGACY_RECOMMENDATION_CONTRACT_VERSION


def _scanner_producer_run_id(row: dict[str, Any]) -> str | None:
    return _optional_string(row.get("producer_run_id")) or _optional_string(
        row.get("scanner_run_id")
    )


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


def _ml_influence_from_snapshot(
    evidence_snapshot: dict[str, Any] | str,
) -> tuple[float | None, str | None]:
    if not isinstance(evidence_snapshot, dict):
        return None, None
    score = _coerce_float(evidence_snapshot.get("ml_influence_score"))
    reason_raw = evidence_snapshot.get("ml_influence_reason")
    reason = reason_raw if isinstance(reason_raw, str) and reason_raw.strip() else None
    if score is not None:
        return score, reason or "ml_influence_score"
    confidence_signal = _coerce_float(evidence_snapshot.get("ml_confidence"))
    if confidence_signal is not None:
        return confidence_signal, reason or "ml_confidence"
    return None, None


def _effective_confidence(
    *,
    base_confidence: float | None,
    ml_influence_score: float | None,
) -> float | None:
    if base_confidence is None:
        return ml_influence_score
    if ml_influence_score is None:
        return base_confidence
    return round((base_confidence + ml_influence_score) / 2.0, 6)


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
