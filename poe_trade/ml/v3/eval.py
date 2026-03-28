from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, cast

from poe_trade.db import ClickHouseClient

from .sql import TRAINING_TABLE

ROUTE_EVAL_TABLE = "poe_trade.ml_v3_route_eval"
COHORT_EVAL_TABLE = "poe_trade.ml_v3_cohort_eval"
EVAL_RUNS_TABLE = "poe_trade.ml_v3_eval_runs"
PROMOTION_AUDIT_TABLE = "poe_trade.ml_v3_promotion_audit"
PREDICTIONS_TABLE = "poe_trade.ml_v3_price_predictions"


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _insert_json_rows(
    client: ClickHouseClient, table: str, rows: list[dict[str, Any]]
) -> None:
    if not rows:
        return
    body = "\n".join(json.dumps(row, separators=(",", ":")) for row in rows)
    client.execute(f"INSERT INTO {table} FORMAT JSONEachRow\n{body}")


def _support_bucket(sample_count: int) -> str:
    if sample_count >= 2000:
        return "xl"
    if sample_count >= 500:
        return "l"
    if sample_count >= 100:
        return "m"
    if sample_count >= 20:
        return "s"
    return "xs"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _is_missing_contract_value(value: Any) -> bool:
    normalized = str(value or "").strip()
    if not normalized:
        return True
    return normalized.startswith("__legacy_missing_")


def _weighted_average(rows: list[dict[str, Any]], metric_key: str) -> float | None:
    total_weight = 0
    weighted_sum = 0.0
    for row in rows:
        metric_value = _to_float(row.get(metric_key))
        sample_count = int(row.get("sample_count") or 0)
        if metric_value is None or sample_count <= 0:
            continue
        total_weight += sample_count
        weighted_sum += metric_value * sample_count
    if total_weight <= 0:
        return None
    return weighted_sum / total_weight


def _derive_stable_model_version(rows: list[dict[str, Any]], fallback: str) -> str:
    weighted_versions: dict[str, int] = {}
    for row in rows:
        raw_engine_version = str(row.get("engine_version") or "").strip()
        if not raw_engine_version or raw_engine_version == "ml_v3_unknown_engine":
            continue
        sample_count = int(row.get("sample_count") or 0)
        weighted_versions[raw_engine_version] = weighted_versions.get(
            raw_engine_version,
            0,
        ) + max(sample_count, 1)
    if not weighted_versions:
        return fallback
    return max(
        weighted_versions.items(),
        key=lambda item: (item[1], item[0]),
    )[0]


def _serving_path_parity_ok(
    rows: list[dict[str, Any]], *, stable_model_version: str
) -> bool:
    if not rows:
        return False
    if not stable_model_version or stable_model_version == "ml_v3_unknown_engine":
        return False
    observed_versions: set[str] = set()
    for row in rows:
        raw_engine_version = str(row.get("engine_version") or "").strip()
        if not raw_engine_version or raw_engine_version == "ml_v3_unknown_engine":
            return False
        observed_versions.add(raw_engine_version)
    return observed_versions == {stable_model_version}


def _consecutive_pass_windows(
    client: ClickHouseClient,
    *,
    league: str,
    model_version: str,
    split_kind: str,
) -> int | None:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT gate_passed, recorded_at",
                f"FROM {EVAL_RUNS_TABLE}",
                f"WHERE league = {_quote(league)}",
                f"AND model_version = {_quote(model_version)}",
                f"AND split_kind = {_quote(split_kind)}",
                "ORDER BY recorded_at DESC",
                "LIMIT 14",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    valid_rows = [row for row in rows if "gate_passed" in row]
    if not valid_rows:
        return None
    streak = 0
    for row in valid_rows:
        if int(row.get("gate_passed") or 0) != 1:
            break
        streak += 1
    return streak + 1


def _incumbent_baseline(
    client: ClickHouseClient,
    *,
    league: str,
    run_id: str,
) -> dict[str, Any]:
    baseline_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT run_id, global_fair_value_mdape, global_fast_sale_24h_hit_rate",
                f"FROM {EVAL_RUNS_TABLE}",
                f"WHERE league = {_quote(league)}",
                "AND gate_passed = 1",
                f"AND run_id != {_quote(run_id)}",
                "ORDER BY recorded_at DESC",
                "LIMIT 1",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    if not baseline_rows:
        return {
            "incumbent_fair_value_mdape": None,
            "incumbent_fast_sale_hit_rate": None,
            "incumbent_abstain_rate": None,
        }

    baseline_row = baseline_rows[0]
    incumbent_run_id = str(baseline_row.get("run_id") or "")
    incumbent_abstain_rate: float | None = None
    if incumbent_run_id:
        incumbent_route_rows = _query_rows(
            client,
            " ".join(
                [
                    "SELECT sample_count, abstain_rate",
                    f"FROM {ROUTE_EVAL_TABLE}",
                    f"WHERE league = {_quote(league)}",
                    f"AND run_id = {_quote(incumbent_run_id)}",
                    "FORMAT JSONEachRow",
                ]
            ),
        )
        incumbent_abstain_rate = _weighted_average(
            incumbent_route_rows,
            "abstain_rate",
        )

    return {
        "incumbent_fair_value_mdape": _to_float(
            baseline_row.get("global_fair_value_mdape")
        ),
        "incumbent_fast_sale_hit_rate": _to_float(
            baseline_row.get("global_fast_sale_24h_hit_rate")
        ),
        "incumbent_abstain_rate": incumbent_abstain_rate,
    }


def promotion_gate(
    *,
    sample_count: int | None = None,
    global_fair_value_mdape: float | None,
    incumbent_fair_value_mdape: float | None = None,
    global_fast_sale_hit_rate: float | None,
    incumbent_fast_sale_hit_rate: float | None = None,
    global_sale_probability_calibration_error: float | None,
    global_confidence_calibration_error: float | None = None,
    global_abstain_rate: float | None = None,
    incumbent_abstain_rate: float | None = None,
    consecutive_pass_windows: int | None = None,
    worst_slice_mdape: float | None,
    serving_path_parity_ok: bool | None = None,
) -> dict[str, Any]:
    reasons: list[str] = []
    abstain_absolute_cap = 0.05

    mdape_ok = global_fair_value_mdape is not None and global_fair_value_mdape <= 0.30
    fast_sale_ok = (
        global_fast_sale_hit_rate is not None and global_fast_sale_hit_rate >= 0.55
    )
    sale_calib_ok = (
        global_sale_probability_calibration_error is not None
        and global_sale_probability_calibration_error <= 0.20
    )
    confidence_calib_ok = (
        global_confidence_calibration_error is not None
        and global_confidence_calibration_error <= 0.20
    )
    worst_slice_ok = worst_slice_mdape is not None and worst_slice_mdape <= 0.45

    if not mdape_ok:
        reasons.append("global_mdape")
    if not fast_sale_ok:
        reasons.append("fast_sale_hit_rate")
    if not sale_calib_ok:
        reasons.append("sale_calibration")
    if not confidence_calib_ok:
        reasons.append("confidence_calibration")
    if not worst_slice_ok:
        reasons.append("worst_slice")

    if sample_count is None:
        reasons.append("sample_count_required")
    elif sample_count < 150:
        reasons.append("sample_count_below_candidate_min")

    if consecutive_pass_windows is None:
        reasons.append("consecutive_windows_required")
    elif consecutive_pass_windows < 3:
        reasons.append("insufficient_consecutive_windows")

    if serving_path_parity_ok is False:
        reasons.append("serving_path_parity")

    if global_fair_value_mdape is not None and incumbent_fair_value_mdape is not None:
        if incumbent_fair_value_mdape <= 0:
            reasons.append("incumbent_mdape_nonpositive")
        else:
            mdape_improvement_abs = incumbent_fair_value_mdape - global_fair_value_mdape
            mdape_improvement_rel = mdape_improvement_abs / incumbent_fair_value_mdape
            if mdape_improvement_abs < 0.05:
                reasons.append("mdape_abs_improvement")
            if mdape_improvement_rel < 0.10:
                reasons.append("mdape_rel_improvement")

    if (
        global_fast_sale_hit_rate is not None
        and incumbent_fast_sale_hit_rate is not None
        and (incumbent_fast_sale_hit_rate - global_fast_sale_hit_rate) > 0.02
    ):
        reasons.append("fast_sale_hit_rate_degradation")

    if global_abstain_rate is not None and global_abstain_rate > abstain_absolute_cap:
        reasons.append("abstain_rate_absolute_cap")

    if (
        global_abstain_rate is not None
        and incumbent_abstain_rate is not None
        and (global_abstain_rate - incumbent_abstain_rate) > 0.05
    ):
        reasons.append("abstain_rate_increase")

    if reasons:
        return {
            "passed": False,
            "decision": "reject",
            "auto_promotion_eligible": False,
            "manual_review_required": False,
            "reason": ",".join(reasons),
        }

    if sample_count is not None and 150 <= sample_count < 500:
        return {
            "passed": False,
            "decision": "candidate_manual",
            "auto_promotion_eligible": False,
            "manual_review_required": True,
            "reason": "candidate_manual_review",
        }

    return {
        "passed": True,
        "decision": "auto",
        "auto_promotion_eligible": True,
        "manual_review_required": False,
        "reason": "pass",
    }


def depromotion_gate(
    *,
    current_fair_value_mdape: float | None,
    incumbent_fair_value_mdape: float | None,
    current_fast_sale_hit_rate: float | None,
    incumbent_fast_sale_hit_rate: float | None,
    trailing_7d_sample_count: int,
    mdape_regression_consecutive_windows: int,
    fast_sale_degradation_consecutive_windows: int,
    latency_budget_breached: bool = False,
    error_budget_breached: bool = False,
) -> dict[str, Any]:
    reasons: list[str] = []

    mdape_regression_triggered = bool(
        current_fair_value_mdape is not None
        and incumbent_fair_value_mdape is not None
        and (current_fair_value_mdape - incumbent_fair_value_mdape) >= 0.05
        and mdape_regression_consecutive_windows >= 2
    )
    if mdape_regression_triggered:
        reasons.append("mdape_regression")

    fast_sale_hit_rate_degradation_triggered = bool(
        current_fast_sale_hit_rate is not None
        and incumbent_fast_sale_hit_rate is not None
        and (incumbent_fast_sale_hit_rate - current_fast_sale_hit_rate) >= 0.03
        and fast_sale_degradation_consecutive_windows >= 2
    )
    if fast_sale_hit_rate_degradation_triggered:
        reasons.append("fast_sale_hit_rate_degradation")

    trailing_7d_sample_breach = trailing_7d_sample_count < 100
    if trailing_7d_sample_breach:
        reasons.append("trailing_7d_sample_count")

    if latency_budget_breached:
        reasons.append("latency_budget_breach")
    if error_budget_breached:
        reasons.append("error_budget_breach")

    return {
        "triggered": bool(reasons),
        "reason": ",".join(reasons) if reasons else "pass",
        "mdape_regression_triggered": mdape_regression_triggered,
        "fast_sale_hit_rate_degradation_triggered": fast_sale_hit_rate_degradation_triggered,
        "trailing_7d_sample_breach": trailing_7d_sample_breach,
        "latency_budget_breached": latency_budget_breached,
        "error_budget_breached": error_budget_breached,
    }


def evaluate_run(
    client: ClickHouseClient,
    *,
    league: str,
    run_id: str,
    split_kind: str = "forward",
) -> dict[str, Any]:
    strategy_expr = (
        "ifNull(nullIf(nullIf(pred.strategy_family, ''), '__legacy_missing_strategy_family__'), "
        "targets.strategy_family)"
    )
    cohort_expr = (
        "ifNull(nullIf(nullIf(pred.cohort_key, ''), '__legacy_missing_cohort_key__'), "
        "targets.cohort_key)"
    )
    parent_cohort_expr = (
        "ifNull(nullIf(nullIf(pred.parent_cohort_key, ''), '__legacy_missing_parent_cohort_key__'), "
        f"concat({strategy_expr}, '|__legacy_missing_material_state_signature__'))"
    )
    rows = _query_rows(
        client,
        " ".join(
            [
                "WITH targets AS (",
                "SELECT league, identity_key,",
                "argMax(target_price_chaos, as_of_ts) AS target_price_chaos,",
                "argMax(target_fast_sale_24h_price, as_of_ts) AS target_fast_sale_24h_price,",
                "argMax(target_sale_probability_24h, as_of_ts) AS target_sale_probability_24h,",
                "argMax(strategy_family, as_of_ts) AS strategy_family,",
                "argMax(cohort_key, as_of_ts) AS cohort_key",
                f"FROM {TRAINING_TABLE}",
                f"WHERE league = {_quote(league)}",
                "GROUP BY league, identity_key",
                ")",
                "SELECT",
                "pred.route AS route,",
                f"{strategy_expr} AS strategy_family,",
                f"{cohort_expr} AS cohort_key,",
                f"argMax({parent_cohort_expr}, pred.prediction_as_of_ts) AS parent_cohort_key,",
                "argMax(ifNull(nullIf(pred.engine_version, ''), 'ml_v3_unknown_engine'), pred.prediction_as_of_ts) AS engine_version,",
                "argMax(ifNull(pred.fallback_depth, toUInt8(0)), pred.prediction_as_of_ts) AS fallback_depth,",
                "argMax(ifNull(pred.incumbent_flag, toUInt8(0)), pred.prediction_as_of_ts) AS incumbent_flag,",
                "count() AS sample_count,",
                "quantileTDigest(0.5)(abs(pred.fair_value_p50 - targets.target_price_chaos) / greatest(targets.target_price_chaos, 0.01)) AS fair_value_mdape,",
                "avg(abs(pred.fair_value_p50 - targets.target_price_chaos) / greatest(targets.target_price_chaos, 0.01)) AS fair_value_wape,",
                "avg(if(targets.target_fast_sale_24h_price IS NULL OR targets.target_fast_sale_24h_price <= 0, 0.0, if(pred.fast_sale_24h_price <= targets.target_fast_sale_24h_price, 1.0, 0.0))) AS fast_sale_24h_hit_rate,",
                "avg(if(targets.target_fast_sale_24h_price IS NULL OR targets.target_fast_sale_24h_price <= 0, 0.0, abs(pred.fast_sale_24h_price - targets.target_fast_sale_24h_price) / greatest(targets.target_fast_sale_24h_price, 0.01))) AS fast_sale_24h_mdape,",
                "avg(abs(ifNull(pred.sale_probability_24h, 0.5) - ifNull(targets.target_sale_probability_24h, 0.5))) AS sale_probability_calibration_error,",
                "avg(abs(ifNull(pred.confidence, 0.5) - if(abs(pred.fair_value_p50 - targets.target_price_chaos) / greatest(targets.target_price_chaos, 0.01) <= 0.2, 1.0, 0.0))) AS confidence_calibration_error",
                f"FROM {PREDICTIONS_TABLE} AS pred",
                "INNER JOIN targets ON targets.league = pred.league AND targets.identity_key = pred.identity_key",
                f"WHERE pred.league = {_quote(league)} AND pred.run_id = {_quote(run_id)}",
                "GROUP BY pred.route, strategy_family, cohort_key",
                "ORDER BY sample_count DESC, route ASC, strategy_family ASC, cohort_key ASC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    stable_model_version = _derive_stable_model_version(rows, fallback=run_id)
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    cohort_rows: list[dict[str, Any]] = []
    for row in rows:
        route = str(row.get("route") or "fallback_abstain")
        raw_strategy_family = row.get("strategy_family")
        if _is_missing_contract_value(raw_strategy_family):
            strategy_family = route
        else:
            strategy_family = str(raw_strategy_family)
        raw_cohort_key = row.get("cohort_key")
        if _is_missing_contract_value(raw_cohort_key):
            cohort_key = (
                f"{strategy_family}|__legacy_missing_material_state_signature__"
            )
        else:
            cohort_key = str(raw_cohort_key)
        sample_count = int(row.get("sample_count") or 0)
        cohort_rows.append(
            {
                "run_id": run_id,
                "league": league,
                "route": route,
                "strategy_family": strategy_family,
                "cohort_key": cohort_key,
                "family": strategy_family,
                "support_bucket": _support_bucket(sample_count),
                "split_kind": split_kind,
                "sample_count": sample_count,
                "fair_value_mdape": _to_float(row.get("fair_value_mdape")),
                "fair_value_wape": _to_float(row.get("fair_value_wape")),
                "fast_sale_24h_hit_rate": _to_float(row.get("fast_sale_24h_hit_rate")),
                "fast_sale_24h_mdape": _to_float(row.get("fast_sale_24h_mdape")),
                "sale_probability_calibration_error": _to_float(
                    row.get("sale_probability_calibration_error")
                ),
                "confidence_calibration_error": _to_float(
                    row.get("confidence_calibration_error")
                ),
                "abstain_rate": 0.0,
                "recorded_at": now,
            }
        )

    route_agg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in cohort_rows:
        route = str(row.get("route") or "fallback_abstain")
        route_agg[route].append(row)

    route_rows: list[dict[str, Any]] = []
    for route, grouped_rows in sorted(
        route_agg.items(),
        key=lambda item: (
            -sum(int(row.get("sample_count") or 0) for row in item[1]),
            item[0],
        ),
    ):
        sample_count = sum(int(row.get("sample_count") or 0) for row in grouped_rows)
        route_rows.append(
            {
                "run_id": run_id,
                "league": league,
                "route": route,
                "family": route,
                "support_bucket": _support_bucket(sample_count),
                "split_kind": split_kind,
                "sample_count": sample_count,
                "fair_value_mdape": _weighted_average(grouped_rows, "fair_value_mdape"),
                "fair_value_wape": _weighted_average(grouped_rows, "fair_value_wape"),
                "fast_sale_24h_hit_rate": _weighted_average(
                    grouped_rows, "fast_sale_24h_hit_rate"
                ),
                "sale_probability_calibration_error": _weighted_average(
                    grouped_rows, "sale_probability_calibration_error"
                ),
                "confidence_calibration_error": _weighted_average(
                    grouped_rows, "confidence_calibration_error"
                ),
                "abstain_rate": 0.0,
                "recorded_at": now,
            }
        )

    _insert_json_rows(client, ROUTE_EVAL_TABLE, route_rows)
    _insert_json_rows(client, COHORT_EVAL_TABLE, cohort_rows)

    total_sample = sum(int(row.get("sample_count") or 0) for row in cohort_rows)
    if total_sample == 0:
        summary = {
            "run_id": run_id,
            "league": league,
            "status": "no_rows",
        }
        return summary

    global_mdape = _weighted_average(cohort_rows, "fair_value_mdape")
    global_fast_sale = _weighted_average(cohort_rows, "fast_sale_24h_hit_rate")
    global_sale_calibration = _weighted_average(
        cohort_rows, "sale_probability_calibration_error"
    )
    global_fast_sale_mdape = _weighted_average(cohort_rows, "fast_sale_24h_mdape")
    global_conf_calibration = _weighted_average(
        cohort_rows, "confidence_calibration_error"
    )
    global_abstain_rate = _weighted_average(cohort_rows, "abstain_rate")
    mdape_rows = [
        row for row in cohort_rows if _to_float(row.get("fair_value_mdape")) is not None
    ]
    worst_slice: float | None = None
    worst_slice_route = ""
    if mdape_rows:
        worst_slice_row = max(
            mdape_rows,
            key=lambda row: float(_to_float(row.get("fair_value_mdape")) or 0.0),
        )
        worst_slice = _to_float(worst_slice_row.get("fair_value_mdape"))
        worst_slice_route = str(worst_slice_row.get("route") or "")

    consecutive_windows = _consecutive_pass_windows(
        client,
        league=league,
        model_version=stable_model_version,
        split_kind=split_kind,
    )
    incumbent_baseline = _incumbent_baseline(client, league=league, run_id=run_id)

    gate = promotion_gate(
        sample_count=total_sample,
        global_fair_value_mdape=global_mdape,
        incumbent_fair_value_mdape=incumbent_baseline["incumbent_fair_value_mdape"],
        global_fast_sale_hit_rate=global_fast_sale,
        incumbent_fast_sale_hit_rate=incumbent_baseline["incumbent_fast_sale_hit_rate"],
        global_sale_probability_calibration_error=global_sale_calibration,
        global_confidence_calibration_error=global_conf_calibration,
        global_abstain_rate=global_abstain_rate,
        incumbent_abstain_rate=incumbent_baseline["incumbent_abstain_rate"],
        consecutive_pass_windows=consecutive_windows,
        worst_slice_mdape=worst_slice,
        serving_path_parity_ok=_serving_path_parity_ok(
            rows, stable_model_version=stable_model_version
        ),
    )

    eval_row = {
        "run_id": run_id,
        "league": league,
        "model_version": stable_model_version,
        "split_kind": split_kind,
        "total_sample_count": total_sample,
        "global_fair_value_mdape": global_mdape,
        "global_fast_sale_24h_hit_rate": global_fast_sale,
        "global_sale_probability_calibration_error": global_sale_calibration,
        "global_confidence_calibration_error": global_conf_calibration,
        "worst_slice_mdape": worst_slice,
        "worst_slice_route": worst_slice_route,
        "serving_path_parity_ok": 1
        if _serving_path_parity_ok(rows, stable_model_version=stable_model_version)
        else 0,
        "gate_passed": 1 if gate["passed"] else 0,
        "gate_reason": gate["reason"],
        "recorded_at": now,
    }
    _insert_json_rows(client, EVAL_RUNS_TABLE, [eval_row])
    return {
        "run_id": run_id,
        "league": league,
        "route_rows": route_rows,
        "summary": eval_row,
        "metrics": {
            "global_fair_value_mdape": global_mdape,
            "global_fast_sale_24h_hit_rate": global_fast_sale,
            "global_fast_sale_24h_mdape": global_fast_sale_mdape,
            "global_sale_probability_calibration_error": global_sale_calibration,
            "global_confidence_calibration_error": global_conf_calibration,
        },
    }


def format_pricing_benchmark_report(report: dict[str, Any]) -> str:
    benchmark_module = cast(Any, import_module("poe_trade.ml.v3.benchmark"))
    _format_benchmark_report = benchmark_module.format_benchmark_report

    return _format_benchmark_report(report)


def rank_pricing_benchmark_candidates(report: dict[str, Any]) -> list[dict[str, Any]]:
    ranking = report.get("ranking")
    if isinstance(ranking, list):
        return [row for row in ranking if isinstance(row, dict)]
    return []
