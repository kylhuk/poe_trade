from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from poe_trade.db import ClickHouseClient

from .sql import TRAINING_TABLE

ROUTE_EVAL_TABLE = "poe_trade.ml_v3_route_eval"
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


def promotion_gate(
    *,
    global_fair_value_mdape: float | None,
    global_fast_sale_hit_rate: float | None,
    global_sale_probability_calibration_error: float | None,
    worst_slice_mdape: float | None,
) -> dict[str, Any]:
    mdape_ok = global_fair_value_mdape is not None and global_fair_value_mdape <= 0.30
    fast_sale_ok = (
        global_fast_sale_hit_rate is not None and global_fast_sale_hit_rate >= 0.55
    )
    sale_calib_ok = (
        global_sale_probability_calibration_error is not None
        and global_sale_probability_calibration_error <= 0.20
    )
    worst_slice_ok = worst_slice_mdape is not None and worst_slice_mdape <= 0.45
    passed = bool(mdape_ok and fast_sale_ok and sale_calib_ok and worst_slice_ok)
    reason = "pass"
    if not passed:
        reasons: list[str] = []
        if not mdape_ok:
            reasons.append("global_mdape")
        if not fast_sale_ok:
            reasons.append("fast_sale_hit_rate")
        if not sale_calib_ok:
            reasons.append("sale_calibration")
        if not worst_slice_ok:
            reasons.append("worst_slice")
        reason = ",".join(reasons)
    return {
        "passed": passed,
        "reason": reason,
    }


def evaluate_run(
    client: ClickHouseClient,
    *,
    league: str,
    run_id: str,
    split_kind: str = "rolling",
) -> dict[str, Any]:
    rows = _query_rows(
        client,
        " ".join(
            [
                "WITH targets AS (",
                "SELECT league, identity_key,",
                "argMax(target_price_chaos, as_of_ts) AS target_price_chaos,",
                "argMax(target_fast_sale_24h_price, as_of_ts) AS target_fast_sale_24h_price,",
                "argMax(target_sale_probability_24h, as_of_ts) AS target_sale_probability_24h",
                f"FROM {TRAINING_TABLE}",
                f"WHERE league = {_quote(league)}",
                "GROUP BY league, identity_key",
                ")",
                "SELECT",
                "pred.route AS route,",
                "count() AS sample_count,",
                "quantileTDigest(0.5)(abs(pred.fair_value_p50 - targets.target_price_chaos) / greatest(targets.target_price_chaos, 0.01)) AS fair_value_mdape,",
                "avg(abs(pred.fair_value_p50 - targets.target_price_chaos) / greatest(targets.target_price_chaos, 0.01)) AS fair_value_wape,",
                "avg(if(targets.target_fast_sale_24h_price IS NULL OR targets.target_fast_sale_24h_price <= 0, 0.0, if(pred.fast_sale_24h_price <= targets.target_fast_sale_24h_price, 1.0, 0.0))) AS fast_sale_24h_hit_rate,",
                "avg(abs(ifNull(pred.sale_probability_24h, 0.5) - ifNull(targets.target_sale_probability_24h, 0.5))) AS sale_probability_calibration_error,",
                "avg(abs(ifNull(pred.confidence, 0.5) - if(abs(pred.fair_value_p50 - targets.target_price_chaos) / greatest(targets.target_price_chaos, 0.01) <= 0.2, 1.0, 0.0))) AS confidence_calibration_error",
                f"FROM {PREDICTIONS_TABLE} AS pred",
                "INNER JOIN targets ON targets.league = pred.league AND targets.identity_key = pred.identity_key",
                f"WHERE pred.league = {_quote(league)} AND pred.run_id = {_quote(run_id)}",
                "GROUP BY pred.route",
                "ORDER BY sample_count DESC, route ASC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    route_rows: list[dict[str, Any]] = []
    for row in rows:
        route = str(row.get("route") or "fallback_abstain")
        sample_count = int(row.get("sample_count") or 0)
        mdape = row.get("fair_value_mdape")
        route_rows.append(
            {
                "run_id": run_id,
                "league": league,
                "route": route,
                "family": route,
                "support_bucket": _support_bucket(sample_count),
                "split_kind": split_kind,
                "sample_count": sample_count,
                "fair_value_mdape": float(mdape) if mdape is not None else None,
                "fair_value_wape": float(row.get("fair_value_wape") or 0.0),
                "fast_sale_24h_hit_rate": float(
                    row.get("fast_sale_24h_hit_rate") or 0.0
                ),
                "sale_probability_calibration_error": float(
                    row.get("sale_probability_calibration_error") or 0.0
                ),
                "confidence_calibration_error": float(
                    row.get("confidence_calibration_error") or 0.0
                ),
                "abstain_rate": 0.0,
                "recorded_at": now,
            }
        )
    _insert_json_rows(client, ROUTE_EVAL_TABLE, route_rows)

    total_sample = sum(int(row.get("sample_count") or 0) for row in route_rows)
    if total_sample == 0:
        summary = {
            "run_id": run_id,
            "league": league,
            "status": "no_rows",
        }
        return summary

    global_mdape = sum(
        (float(row.get("fair_value_mdape") or 0.0) * int(row.get("sample_count") or 0))
        for row in route_rows
    ) / max(total_sample, 1)
    global_fast_sale = sum(
        (
            float(row.get("fast_sale_24h_hit_rate") or 0.0)
            * int(row.get("sample_count") or 0)
        )
        for row in route_rows
    ) / max(total_sample, 1)
    global_sale_calibration = sum(
        (
            float(row.get("sale_probability_calibration_error") or 0.0)
            * int(row.get("sample_count") or 0)
        )
        for row in route_rows
    ) / max(total_sample, 1)
    global_conf_calibration = sum(
        (
            float(row.get("confidence_calibration_error") or 0.0)
            * int(row.get("sample_count") or 0)
        )
        for row in route_rows
    ) / max(total_sample, 1)
    worst_slice = max(float(row.get("fair_value_mdape") or 0.0) for row in route_rows)
    worst_slice_route = max(
        route_rows,
        key=lambda row: float(row.get("fair_value_mdape") or 0.0),
    ).get("route")

    gate = promotion_gate(
        global_fair_value_mdape=global_mdape,
        global_fast_sale_hit_rate=global_fast_sale,
        global_sale_probability_calibration_error=global_sale_calibration,
        worst_slice_mdape=worst_slice,
    )

    eval_row = {
        "run_id": run_id,
        "league": league,
        "model_version": run_id,
        "split_kind": split_kind,
        "total_sample_count": total_sample,
        "global_fair_value_mdape": global_mdape,
        "global_fast_sale_24h_hit_rate": global_fast_sale,
        "global_sale_probability_calibration_error": global_sale_calibration,
        "global_confidence_calibration_error": global_conf_calibration,
        "worst_slice_mdape": worst_slice,
        "worst_slice_route": str(worst_slice_route or ""),
        "serving_path_parity_ok": 1,
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
    }
