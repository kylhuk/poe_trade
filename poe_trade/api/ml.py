from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from poe_trade.config.settings import Settings
from poe_trade.db import ClickHouseClient
from poe_trade.db.clickhouse import ClickHouseClientError
from poe_trade.ml import workflows
from poe_trade.ml.v3 import serve as v3_serve


class BackendUnavailable(RuntimeError):
    pass


_MIRAGE_ROLLOUT_LEAGUE = "Mirage"
_AUTOMATION_DATASET_TABLE = "poe_trade.ml_price_dataset_v2"


def _v3_serving_enabled() -> bool:
    flag = str(os.getenv("POE_ML_V3_SERVING_ENABLED", "0")).strip().lower()
    return flag in {"1", "true", "yes", "on"}


def contract_payload(settings: Settings) -> dict[str, Any]:
    return {
        "version": "v1",
        "auth_mode": "bearer_operator_token",
        "allowed_leagues": list(settings.api_league_allowlist),
        "routes": {
            "healthz": "/healthz",
            "ml_contract": "/api/v1/ml/contract",
            "ml_status": "/api/v1/ml/leagues/{league}/status",
            "ml_predict_one": "/api/v1/ml/leagues/{league}/predict-one",
            "ml_rollout": "/api/v1/ml/leagues/{league}/rollout",
            "ml_automation_status": "/api/v1/ml/leagues/{league}/automation/status",
            "ml_automation_history": "/api/v1/ml/leagues/{league}/automation/history",
        },
        "non_goals": [
            "no_train_loop_route",
            "no_evaluate_route",
            "no_report_route",
            "no_predict_batch_route",
        ],
    }


def ensure_allowed_league(league: str, settings: Settings) -> None:
    if league not in settings.api_league_allowlist:
        raise ValueError(f"league {league!r} is not allowed")


def fetch_status(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    try:
        payload = workflows.status(client, league=league, run="latest")
    except ClickHouseClientError as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    except Exception as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    return map_status_payload(league=league, payload=payload)


def fetch_predict_one(
    client: ClickHouseClient,
    *,
    league: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    clipboard = validate_predict_one_request(request_payload)
    try:
        if _v3_serving_enabled():
            v3_payload = v3_serve.predict_one_v3(
                client,
                league=league,
                clipboard_text=clipboard,
            )
            return normalize_predict_one_payload(league=league, payload=v3_payload)

        if league != _MIRAGE_ROLLOUT_LEAGUE:
            raw = workflows.predict_one(client, league=league, clipboard_text=clipboard)
            return normalize_predict_one_payload(league=league, payload=raw)

        try:
            rollout = workflows.rollout_controls(client, league=league)
        except ClickHouseClientError:
            rollout = {
                "league": league,
                "shadow_mode": False,
                "cutover_enabled": False,
                "candidate_model_version": None,
                "incumbent_model_version": None,
                "effective_serving_model_version": None,
                "updated_at": None,
                "last_action": "fallback_no_rollout_state",
            }
        serving_model_version = _opt_model_version(
            rollout.get("effective_serving_model_version")
        )
        if serving_model_version:
            serving_raw = workflows.predict_one(
                client,
                league=league,
                clipboard_text=clipboard,
                model_version=serving_model_version,
            )
        else:
            serving_raw = workflows.predict_one(
                client,
                league=league,
                clipboard_text=clipboard,
            )
        response = normalize_predict_one_payload(league=league, payload=serving_raw)
        response["rollout"] = _rollout_payload(rollout)
        response["servingModelVersion"] = serving_model_version

        shadow_mode = bool(rollout.get("shadow_mode", False))
        candidate_model_version = _opt_model_version(
            rollout.get("candidate_model_version")
        )
        incumbent_model_version = _opt_model_version(
            rollout.get("incumbent_model_version")
        )
        if (
            shadow_mode
            and candidate_model_version
            and incumbent_model_version
            and candidate_model_version != incumbent_model_version
        ):
            if serving_model_version == candidate_model_version:
                candidate_raw = serving_raw
            else:
                candidate_raw = workflows.predict_one(
                    client,
                    league=league,
                    clipboard_text=clipboard,
                    model_version=candidate_model_version,
                )
            if serving_model_version == incumbent_model_version:
                incumbent_raw = serving_raw
            else:
                incumbent_raw = workflows.predict_one(
                    client,
                    league=league,
                    clipboard_text=clipboard,
                    model_version=incumbent_model_version,
                )
            response["shadowComparison"] = {
                "candidateModelVersion": candidate_model_version,
                "incumbentModelVersion": incumbent_model_version,
                "candidate": _shadow_prediction_payload(candidate_raw),
                "incumbent": _shadow_prediction_payload(incumbent_raw),
            }
        return response
    except ValueError:
        raise
    except workflows.ActiveModelUnavailableError as exc:
        raise BackendUnavailable(f"predict backend unavailable: {exc.reason}") from exc
    except ClickHouseClientError as exc:
        raise BackendUnavailable("predict backend unavailable") from exc
    except Exception as exc:
        raise BackendUnavailable("predict backend unavailable") from exc


def fetch_rollout_controls(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    if league != _MIRAGE_ROLLOUT_LEAGUE:
        raise ValueError("rollout controls are currently Mirage-only")
    try:
        payload = workflows.rollout_controls(client, league=league)
    except ClickHouseClientError as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    except Exception as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    return _rollout_payload(payload)


def update_rollout_controls(
    client: ClickHouseClient,
    *,
    league: str,
    request_payload: dict[str, Any],
) -> dict[str, Any]:
    if league != _MIRAGE_ROLLOUT_LEAGUE:
        raise ValueError("rollout controls are currently Mirage-only")
    allowed_keys = {"shadowMode", "cutoverEnabled", "rollbackToIncumbent"}
    extra = set(request_payload) - allowed_keys
    if extra:
        raise ValueError("unexpected request field")
    shadow_mode = _optional_bool(request_payload.get("shadowMode"), "shadowMode")
    cutover_enabled = _optional_bool(
        request_payload.get("cutoverEnabled"), "cutoverEnabled"
    )
    rollback_to_incumbent = _optional_bool(
        request_payload.get("rollbackToIncumbent"),
        "rollbackToIncumbent",
    )
    if rollback_to_incumbent is None:
        rollback_to_incumbent = False
    try:
        payload = workflows.update_rollout_controls(
            client,
            league=league,
            shadow_mode=shadow_mode,
            cutover_enabled=cutover_enabled,
            rollback_to_incumbent=rollback_to_incumbent,
        )
    except ValueError:
        raise
    except ClickHouseClientError as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    except Exception as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    return _rollout_payload(payload)


def fetch_automation_status(client: ClickHouseClient, *, league: str) -> dict[str, Any]:
    status_payload = fetch_status(client, league=league)
    history_rows = workflows.train_run_history(client, league=league, limit=1)
    latest = history_rows[0] if history_rows else {}
    active_model_version = _opt_model_version(latest.get("active_model_version"))
    if active_model_version is None:
        active_model_version = _opt_model_version(
            status_payload.get("active_model_version")
        )
    return {
        "league": league,
        "status": status_payload.get("status"),
        "activeModelVersion": active_model_version,
        "latestRun": {
            "runId": latest.get("run_id"),
            "status": latest.get("status"),
            "stopReason": latest.get("stop_reason"),
            "updatedAt": str(latest.get("updated_at") or "").replace(" ", "T") + "Z"
            if latest.get("updated_at")
            else None,
        }
        if latest
        else None,
        "promotionVerdict": status_payload.get("promotion_verdict"),
        "routeHotspots": status_payload.get("route_hotspots") or [],
    }


def fetch_automation_history(
    client: ClickHouseClient, *, league: str, limit: int = 20
) -> dict[str, Any]:
    run_rows = workflows.train_run_history(client, league=league, limit=limit)
    eval_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, avg(mdape) AS avg_mdape, avg(interval_80_coverage) AS avg_cov, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_eval_runs",
                f"WHERE league = {_quote(league)}",
                "GROUP BY run_id",
                "ORDER BY recorded_at DESC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    promotion_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT candidate_run_id, verdict, candidate_model_version, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_promotion_audit_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY candidate_run_id, verdict, candidate_model_version",
                "ORDER BY recorded_at DESC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    model_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT model_version, max(promoted_at) AS promoted_at",
                "FROM poe_trade.ml_model_registry_v1",
                f"WHERE league = {_quote(league)} AND promoted = 1",
                "GROUP BY model_version",
                "ORDER BY promoted_at DESC",
                f"LIMIT {max(1, limit)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    route_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, sum(sample_count) AS sample_count, avg(mdape) AS avg_mdape, avg(interval_80_coverage) AS avg_cov, avg(abstain_rate) AS avg_abstain_rate, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY route",
                "ORDER BY sample_count DESC, route ASC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    route_run_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, route, sum(sample_count) AS sample_count, avg(mdape) AS avg_mdape, avg(interval_80_coverage) AS avg_cov, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY run_id, route",
                "ORDER BY recorded_at DESC, route ASC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    dataset_route_rows = _query_rows(
        client,
        " ".join(
            [
                "WITH multiIf(category IN ('essence'), 'fallback_abstain', category IN ('fossil','scarab','logbook'), 'fungible_reference', ifNull(rarity, '') = 'Unique' AND multiIf(category = 'ring', 'ring', category = 'amulet', 'amulet', category = 'belt', 'belt', category = 'jewel', 'jewel', match(lowerUTF8(base_type), '(^|\\W)ring(\\W|$)'), 'ring', match(lowerUTF8(base_type), '(^|\\W)amulet(\\W|$)'), 'amulet', match(lowerUTF8(base_type), '(^|\\W)belt(\\W|$)'), 'belt', match(lowerUTF8(base_type), '(^|\\W)(cluster\\s+)?jewel(\\W|$)'), 'jewel', 'other') != 'other', 'structured_boosted_other', ifNull(rarity, '') = 'Unique', 'structured_boosted', category = 'cluster_jewel', 'cluster_jewel_retrieval', ifNull(rarity, '') = 'Rare', 'sparse_retrieval', 'fallback_abstain') AS route",
                "SELECT route, count() AS rows",
                f"FROM {_AUTOMATION_DATASET_TABLE}",
                f"WHERE league = {_quote(league)}",
                "GROUP BY route",
                "ORDER BY rows DESC, route ASC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    dataset_totals = _query_rows(
        client,
        " ".join(
            [
                "SELECT count() AS total_rows, uniqExact(base_type) AS base_type_count",
                f"FROM {_AUTOMATION_DATASET_TABLE}",
                f"WHERE league = {_quote(league)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    route_family_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, family, support_bucket, sum(sample_count) AS sample_count, avg(mdape) AS avg_mdape, avg(interval_80_coverage) AS avg_cov, max(recorded_at) AS recorded_at",
                "FROM poe_trade.ml_route_eval_v1",
                f"WHERE league = {_quote(league)}",
                "GROUP BY route, family, support_bucket",
                "ORDER BY route ASC, family ASC, support_bucket ASC",
                "FORMAT JSONEachRow",
            ]
        ),
    )

    eval_by_run = {str(row.get("run_id") or ""): row for row in eval_rows}
    promotion_by_run = {
        str(row.get("candidate_run_id") or ""): row for row in promotion_rows
    }

    history: list[dict[str, Any]] = []
    for row in run_rows:
        eval_run_id = (
            _opt_str(row.get("eval_run_id")) or _opt_str(row.get("run_id")) or ""
        )
        eval_row = eval_by_run.get(eval_run_id, {})
        promotion_row = promotion_by_run.get(eval_run_id, {})
        history.append(
            {
                "runId": row.get("run_id"),
                "status": row.get("status"),
                "stopReason": row.get("stop_reason"),
                "activeModelVersion": _opt_model_version(
                    row.get("active_model_version")
                ),
                "tuningConfigId": row.get("tuning_config_id"),
                "evalRunId": row.get("eval_run_id"),
                "updatedAt": _as_iso_utc(row.get("updated_at")),
                "rowsProcessed": _opt_int(row.get("rows_processed")),
                "avgMdape": _opt_float(eval_row.get("avg_mdape")),
                "avgIntervalCoverage": _opt_float(eval_row.get("avg_cov")),
                "verdict": _opt_str(promotion_row.get("verdict")),
            }
        )

    quality_trend = [
        {
            "runId": row.get("runId"),
            "updatedAt": row.get("updatedAt"),
            "avgMdape": row.get("avgMdape"),
            "avgIntervalCoverage": row.get("avgIntervalCoverage"),
            "verdict": row.get("verdict"),
            "activeModelVersion": row.get("activeModelVersion"),
        }
        for row in sorted(history, key=lambda item: str(item.get("updatedAt") or ""))
        if row.get("avgMdape") is not None
    ]

    route_metric_map: dict[str, dict[str, Any]] = {}
    for row in route_rows:
        route = _opt_str(row.get("route")) or "unknown"
        route_metric_map[route] = {
            "route": route,
            "sampleCount": _opt_int(row.get("sample_count")) or 0,
            "avgMdape": _opt_float(row.get("avg_mdape")),
            "avgIntervalCoverage": _opt_float(row.get("avg_cov")),
            "avgAbstainRate": _opt_float(row.get("avg_abstain_rate")),
            "recordedAt": _as_iso_utc(row.get("recorded_at")),
        }
    for route in workflows.ROUTES:
        route_metric_map.setdefault(
            route,
            {
                "route": route,
                "sampleCount": 0,
                "avgMdape": None,
                "avgIntervalCoverage": None,
                "avgAbstainRate": None,
                "recordedAt": None,
            },
        )
    route_metrics = [route_metric_map[route] for route in workflows.ROUTES]
    run_by_id: dict[str, dict[str, Any]] = {}
    for row in history:
        run_id = _opt_str(row.get("runId") or row.get("run_id")) or ""
        eval_run_id = _opt_str(row.get("evalRunId") or row.get("eval_run_id")) or ""
        if run_id:
            run_by_id[run_id] = row
        if eval_run_id:
            run_by_id[eval_run_id] = row
    per_model_history = [
        {
            "runId": _opt_str(row.get("run_id")),
            "route": _opt_str(row.get("route")),
            "activeModelVersion": _opt_model_version(
                (run_by_id.get(_opt_str(row.get("run_id")) or "") or {}).get(
                    "activeModelVersion"
                )
            ),
            "rowsProcessed": _opt_int(
                (run_by_id.get(_opt_str(row.get("run_id")) or "") or {}).get(
                    "rowsProcessed"
                )
            ),
            "sampleCount": _opt_int(row.get("sample_count")),
            "avgMdape": _opt_float(row.get("avg_mdape")),
            "avgIntervalCoverage": _opt_float(row.get("avg_cov")),
            "recordedAt": _as_iso_utc(row.get("recorded_at")),
        }
        for row in route_run_rows
        if _opt_str(row.get("run_id"))
    ]
    latest_per_model: dict[str, dict[str, Any]] = {}
    for row in per_model_history:
        route = _opt_str(row.get("route")) or "unknown"
        if route in latest_per_model:
            continue
        latest_per_model[route] = row
    model_metrics: list[dict[str, Any]] = []
    for route in workflows.ROUTES:
        row = latest_per_model.get(route)
        if row is not None:
            model_metrics.append(row)
            continue
        model_metrics.append(
            {
                "runId": None,
                "route": route,
                "activeModelVersion": None,
                "rowsProcessed": history[0].get("rowsProcessed") if history else None,
                "sampleCount": 0,
                "avgMdape": None,
                "avgIntervalCoverage": None,
                "recordedAt": None,
            }
        )

    total_rows = (
        _opt_int((dataset_totals[0] if dataset_totals else {}).get("total_rows")) or 0
    )
    dataset_routes = [
        {
            "route": _opt_str(row.get("route")),
            "rows": _opt_int(row.get("rows")) or 0,
            "share": ((_opt_int(row.get("rows")) or 0) / total_rows)
            if total_rows > 0
            else 0.0,
        }
        for row in dataset_route_rows
    ]
    supported_rows = sum(_opt_int(route.get("rows")) or 0 for route in dataset_routes)
    route_families = [
        {
            "route": _opt_str(row.get("route")),
            "family": _opt_str(row.get("family")),
            "supportBucket": _opt_str(row.get("support_bucket")),
            "sampleCount": _opt_int(row.get("sample_count")) or 0,
            "avgMdape": _opt_float(row.get("avg_mdape")),
            "avgIntervalCoverage": _opt_float(row.get("avg_cov")),
            "recordedAt": _as_iso_utc(row.get("recorded_at")),
        }
        for row in route_family_rows
    ]

    promotions = [
        {
            "modelVersion": _opt_model_version(row.get("model_version")),
            "promotedAt": _as_iso_utc(row.get("promoted_at")),
        }
        for row in model_rows
        if _opt_model_version(row.get("model_version"))
    ]

    anchor = _latest_history_timestamp(history)
    previous_mdape = (
        _opt_float(quality_trend[-2].get("avgMdape"))
        if len(quality_trend) >= 2
        else None
    )
    latest_mdape = (
        _opt_float(quality_trend[-1].get("avgMdape")) if quality_trend else None
    )
    mdape_delta = None
    if previous_mdape is not None and latest_mdape is not None:
        mdape_delta = round(float(previous_mdape) - float(latest_mdape), 6)
    mdape_values: list[float] = []
    for row in quality_trend:
        value = _opt_float(row.get("avgMdape"))
        if value is not None:
            mdape_values.append(value)

    return {
        "league": league,
        "history": history,
        "summary": {
            "activeModelVersion": history[0].get("activeModelVersion")
            if history
            else None,
            "lastRunAt": history[0].get("updatedAt") if history else None,
            "lastPromotedAt": promotions[0].get("promotedAt") if promotions else None,
            "runsLast7d": _count_runs_since(history, anchor, days=7),
            "runsLast30d": _count_runs_since(history, anchor, days=30),
            "medianHoursBetweenRuns": _median_run_gap_hours(history),
            "latestAvgMdape": latest_mdape,
            "latestAvgIntervalCoverage": quality_trend[-1].get("avgIntervalCoverage")
            if quality_trend
            else None,
            "bestAvgMdape": min(mdape_values) if mdape_values else None,
            "mdapeDeltaVsPrevious": mdape_delta,
            "trendDirection": _trend_direction(mdape_delta),
        },
        "qualityTrend": quality_trend,
        "trainingCadence": _training_cadence_series(history),
        "routeMetrics": route_metrics,
        "modelMetrics": model_metrics,
        "modelHistory": per_model_history,
        "routeFamilies": route_families,
        "datasetCoverage": {
            "totalRows": total_rows,
            "supportedRows": supported_rows,
            "coverageRatio": (supported_rows / total_rows) if total_rows > 0 else 0.0,
            "baseTypeCount": _opt_int(
                (dataset_totals[0] if dataset_totals else {}).get("base_type_count")
            ),
            "routes": dataset_routes,
        },
        "promotions": promotions,
    }


def map_status_payload(*, league: str, payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("status") == "no_runs":
        return {
            "league": league,
            "run": None,
            "status": "no_runs",
            "promotion_verdict": None,
            "stop_reason": None,
            "active_model_version": None,
            "latest_avg_mdape": None,
            "latest_avg_interval_coverage": None,
            "candidate_vs_incumbent": {},
            "route_hotspots": [],
            "warmup": _as_dict(payload.get("warmup")),
            "route_decisions": [],
        }
    return {
        "league": league,
        "run": _opt_str(payload.get("run_id")),
        "status": _opt_str(payload.get("status")),
        "promotion_verdict": _opt_str(payload.get("promotion_verdict")),
        "promotion_policy": _as_dict(payload.get("promotion_policy")),
        "stop_reason": _opt_str(payload.get("stop_reason")),
        "active_model_version": _opt_model_version(payload.get("active_model_version")),
        "latest_avg_mdape": _opt_float(payload.get("latest_avg_mdape")),
        "latest_avg_interval_coverage": _opt_float(
            payload.get("latest_avg_interval_coverage")
        ),
        "candidate_vs_incumbent": _as_dict(payload.get("candidate_vs_incumbent")),
        "route_hotspots": _as_list(payload.get("route_hotspots")),
        "warmup": _as_dict(payload.get("warmup")),
        "route_decisions": _as_list(payload.get("route_decisions")),
    }


def validate_predict_one_request(payload: dict[str, Any]) -> str:
    allowed_keys = {"input_format", "payload", "output_mode", "clipboard", "itemText"}
    extra = set(payload) - allowed_keys
    if extra:
        raise ValueError("unexpected request field")

    clipboard = payload.get("clipboard")
    if isinstance(clipboard, str) and clipboard.strip():
        return clipboard.strip()

    item_text = payload.get("itemText")
    if isinstance(item_text, str) and item_text.strip():
        return item_text.strip()

    input_format = payload.get("input_format")
    if input_format is not None and input_format != "poe-clipboard":
        raise ValueError("input_format must be poe-clipboard")
    output_mode = payload.get("output_mode")
    if output_mode is not None and output_mode != "json":
        raise ValueError("output_mode must be json")
    raw_payload = payload.get("payload")
    if not isinstance(raw_payload, str) or not raw_payload.strip():
        raise ValueError("payload must be a non-empty string")
    return raw_payload.strip()


def normalize_predict_one_payload(
    *, league: str, payload: dict[str, Any]
) -> dict[str, Any]:
    price_p10 = _opt_float(payload.get("price_p10"))
    price_p50 = _opt_float(payload.get("price_p50"))
    price_p90 = _opt_float(payload.get("price_p90"))
    predicted_value = _opt_float(payload.get("predictedValue"))
    if predicted_value is None:
        predicted_value = price_p50
    confidence = _opt_float(payload.get("confidence"))
    if confidence is None:
        confidence = _opt_float(payload.get("confidence_percent"))
    sale_probability_percent = _opt_float(payload.get("saleProbabilityPercent"))
    if sale_probability_percent is None:
        sale_probability_percent = _opt_float(payload.get("sale_probability_percent"))
    price_recommendation_eligible = bool(
        payload.get("priceRecommendationEligible")
        if "priceRecommendationEligible" in payload
        else payload.get("price_recommendation_eligible", False)
    )
    fallback_reason = str(
        payload.get("fallbackReason") or payload.get("fallback_reason") or ""
    )
    ml_predicted = bool(
        payload.get("mlPredicted")
        if "mlPredicted" in payload
        else payload.get("ml_predicted", True)
    )
    prediction_source = str(
        payload.get("predictionSource")
        or payload.get("prediction_source")
        or ("ml" if ml_predicted else "static_fallback")
    )
    estimate_trust = str(
        payload.get("estimateTrust")
        or payload.get("estimate_trust")
        or ("normal" if ml_predicted else "low")
    )
    explicit_warning = payload.get("estimateWarning")
    if explicit_warning is None:
        explicit_warning = payload.get("estimate_warning")
    estimate_warning = (
        explicit_warning
        if explicit_warning is not None
        else (
            None
            if ml_predicted
            else (
                "ML could not predict this item (insufficient/unseen data). "
                "This is a static fallback estimate and may be inaccurate."
            )
        )
    )
    currency = str(payload.get("currency") or "chaos")

    return {
        "league": league,
        "route": str(payload.get("route") or "fallback_abstain"),
        "predictedValue": predicted_value,
        "currency": currency,
        "confidence": confidence,
        "interval": {
            "p10": price_p10,
            "p90": price_p90,
        },
        "saleProbabilityPercent": sale_probability_percent,
        "priceRecommendationEligible": price_recommendation_eligible,
        "fallbackReason": fallback_reason,
        "mlPredicted": ml_predicted,
        "predictionSource": prediction_source,
        "estimateTrust": estimate_trust,
        "estimateWarning": estimate_warning,
        # Backward-compatible fields for existing clients.
        "price_p10": price_p10,
        "price_p50": price_p50,
        "price_p90": price_p90,
        "confidence_percent": confidence,
        "sale_probability_percent": sale_probability_percent,
        "price_recommendation_eligible": price_recommendation_eligible,
        "fallback_reason": fallback_reason,
        "ml_predicted": ml_predicted,
        "prediction_source": prediction_source,
        "estimate_trust": estimate_trust,
        "estimate_warning": estimate_warning,
    }


def _rollout_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "league": _opt_str(payload.get("league")) or _MIRAGE_ROLLOUT_LEAGUE,
        "shadowMode": bool(payload.get("shadow_mode", False)),
        "cutoverEnabled": bool(payload.get("cutover_enabled", False)),
        "candidateModelVersion": _opt_model_version(
            payload.get("candidate_model_version")
        ),
        "incumbentModelVersion": _opt_model_version(
            payload.get("incumbent_model_version")
        ),
        "effectiveServingModelVersion": _opt_model_version(
            payload.get("effective_serving_model_version")
        ),
        "updatedAt": _as_iso_utc(payload.get("updated_at")),
        "lastAction": _opt_str(payload.get("last_action")),
    }


def _optional_bool(value: Any, field_name: str) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ValueError(f"{field_name} must be a boolean")


def _shadow_prediction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "route": _opt_str(payload.get("route")) or "fallback_abstain",
        "price_p10": _opt_float(payload.get("price_p10")),
        "price_p50": _opt_float(payload.get("price_p50")),
        "price_p90": _opt_float(payload.get("price_p90")),
        "confidence_percent": _opt_float(payload.get("confidence_percent")),
        "sale_probability_percent": _opt_float(payload.get("sale_probability_percent")),
    }


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_model_version(value: Any) -> str | None:
    normalized = _opt_str(value)
    if normalized is None:
        return None
    compact = normalized.strip()
    if not compact:
        return None
    if compact.lower() in {"none", "null", "no_model"}:
        return None
    return compact


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_iso_utc(value: Any) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return raw.replace(" ", "T") + (
            "Z" if "T" in raw and not raw.endswith("Z") else ""
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.isoformat().replace("+00:00", "Z")


def _history_datetimes(history: list[dict[str, Any]]) -> list[datetime]:
    values: list[datetime] = []
    for row in history:
        iso = row.get("updatedAt")
        if not iso:
            continue
        try:
            values.append(datetime.fromisoformat(str(iso).replace("Z", "+00:00")))
        except ValueError:
            continue
    return sorted(values)


def _latest_history_timestamp(history: list[dict[str, Any]]) -> datetime | None:
    values = _history_datetimes(history)
    return values[-1] if values else None


def _count_runs_since(
    history: list[dict[str, Any]], anchor: datetime | None, *, days: int
) -> int:
    values = _history_datetimes(history)
    if not values:
        return 0
    reference = anchor or values[-1]
    cutoff = reference.timestamp() - (days * 86400)
    return sum(1 for value in values if value.timestamp() >= cutoff)


def _median_run_gap_hours(history: list[dict[str, Any]]) -> float | None:
    values = _history_datetimes(history)
    if len(values) < 2:
        return None
    gaps = []
    for earlier, later in zip(values, values[1:]):
        gaps.append((later - earlier).total_seconds() / 3600.0)
    ordered = sorted(gaps)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(float(ordered[mid]), 3)
    return round(float((ordered[mid - 1] + ordered[mid]) / 2.0), 3)


def _training_cadence_series(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, int] = {}
    for row in history:
        iso = row.get("updatedAt")
        if not iso:
            continue
        day = str(iso)[:10]
        buckets[day] = buckets.get(day, 0) + 1
    return [{"date": day, "runs": buckets[day]} for day in sorted(buckets)]


def _trend_direction(mdape_delta: float | None) -> str:
    if mdape_delta is None:
        return "unknown"
    if mdape_delta > 0.005:
        return "improving"
    if mdape_delta < -0.005:
        return "regressing"
    return "flat"


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    try:
        payload = client.execute(query).strip()
    except ClickHouseClientError as exc:
        raise BackendUnavailable("status backend unavailable") from exc
    if not payload:
        return []
    rows: list[dict[str, Any]] = []
    for line in payload.splitlines():
        parsed = json.loads(line)
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"
