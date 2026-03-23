from __future__ import annotations

import json
from datetime import UTC, datetime
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import uuid

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from poe_trade.db import ClickHouseClient

from . import sql

MAX_ROWS_PER_ROUTE_DEFAULT = 60_000
EVAL_ROWS_PER_ROUTE_DEFAULT = 2_000


@dataclass(frozen=True)
class TrainRouteResult:
    league: str
    route: str
    row_count: int
    model_bundle_path: str
    status: str


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _load_training_rows(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    max_rows: int,
) -> list[dict[str, Any]]:
    count_rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT count() AS rows",
                f"FROM {sql.TRAINING_TABLE}",
                f"WHERE league = {_quote(league)} AND route = {_quote(route)}",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    total_rows = int((count_rows[0].get("rows") if count_rows else 0) or 0)
    bucket_threshold = 1000
    if max_rows > 0 and total_rows > max_rows:
        bucket_threshold = max(1, min(1000, int((max_rows * 1000) / total_rows)))

    query = " ".join(
        [
            "SELECT",
            "feature_vector_json,",
            "mod_features_json,",
            "target_price_chaos,",
            "target_fast_sale_24h_price,",
            "target_sale_probability_24h",
            f"FROM {sql.TRAINING_TABLE}",
            f"WHERE league = {_quote(league)} AND route = {_quote(route)}",
            "AND target_price_chaos > 0",
            f"AND split_bucket < {bucket_threshold}",
            f"LIMIT {max(1, max_rows)}",
            "FORMAT JSONEachRow",
        ]
    )
    return _query_rows(client, query)


def _feature_dict(row: dict[str, Any]) -> dict[str, float]:
    merged: dict[str, float] = {}
    for key in ("feature_vector_json", "mod_features_json"):
        raw = row.get(key)
        if raw is None:
            continue
        try:
            payload = json.loads(str(raw))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        for feature_name, value in payload.items():
            try:
                merged[str(feature_name)] = float(value)
            except (TypeError, ValueError):
                continue
    return merged


def apply_residual_cap(
    *,
    anchor_price: float,
    confidence: float,
    fair_residual: float,
    fast_residual: float,
) -> dict[str, float]:
    anchor = max(0.1, float(anchor_price))
    conf = max(0.0, min(1.0, float(confidence)))

    if conf <= 0.20:
        fair_cap_pct = 0.08
        fast_cap_pct = 0.06
    elif conf <= 0.50:
        fair_cap_pct = 0.12
        fast_cap_pct = 0.10
    else:
        fair_cap_pct = 0.18
        fast_cap_pct = 0.14

    fair_delta = max(-anchor * fair_cap_pct, min(anchor * fair_cap_pct, fair_residual))
    fast_delta = max(-anchor * fast_cap_pct, min(anchor * fast_cap_pct, fast_residual))

    return {
        "fair_value": max(0.1, anchor + fair_delta),
        "fast_sale": max(0.1, anchor + fast_delta),
    }


def _register_route_model(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    model_version: str,
    model_dir: str,
    row_count: int,
) -> None:
    recorded_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    row = {
        "league": league,
        "route": route,
        "model_version": model_version,
        "model_dir": model_dir,
        "promoted": 1,
        "promoted_at": recorded_at,
        "metadata_json": json.dumps(
            {
                "row_count": row_count,
                "source": "ml_v3_train",
            },
            separators=(",", ":"),
        ),
    }
    client.execute(
        "INSERT INTO poe_trade.ml_v3_model_registry FORMAT JSONEachRow\n"
        + json.dumps(row, separators=(",", ":"))
    )


def _load_bundle_for_route(
    *, model_dir: str, league: str, route: str
) -> dict[str, Any] | None:
    bundle_path = Path(model_dir) / "v3" / league / route / "bundle.joblib"
    if not bundle_path.exists():
        return None
    payload = joblib.load(bundle_path)
    if not isinstance(payload, dict):
        return None
    return payload


def _load_eval_rows(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    max_rows: int,
) -> list[dict[str, Any]]:
    query = " ".join(
        [
            "SELECT as_of_ts, item_id, identity_key, support_count_recent,",
            "feature_vector_json, mod_features_json",
            f"FROM {sql.TRAINING_TABLE}",
            f"WHERE league = {_quote(league)} AND route = {_quote(route)}",
            "AND target_price_chaos > 0",
            "AND split_bucket >= 900",
            "ORDER BY as_of_ts DESC",
            f"LIMIT {max(1, max_rows)}",
            "FORMAT JSONEachRow",
        ]
    )
    return _query_rows(client, query)


def _insert_eval_predictions(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    run_id: str,
    rows: list[dict[str, Any]],
    bundle: dict[str, Any],
) -> int:
    if not rows:
        return 0
    vectorizer = bundle.get("vectorizer")
    models = bundle.get("models") or {}
    if vectorizer is None or not isinstance(models, dict):
        return 0
    model_p10 = models.get("p10")
    model_p50 = models.get("p50")
    model_p90 = models.get("p90")
    model_fast = models.get("fast_sale_24h")
    model_sale = models.get("sale_probability")
    if model_p10 is None or model_p50 is None or model_p90 is None:
        return 0

    feature_rows = [_feature_dict(row) for row in rows]
    X = vectorizer.transform(feature_rows)
    pred_p10 = model_p10.predict(X)
    pred_p50 = model_p50.predict(X)
    pred_p90 = model_p90.predict(X)
    if model_fast is not None:
        pred_fast = model_fast.predict(X)
    else:
        multiplier = float(bundle.get("fallback_fast_sale_multiplier") or 0.9)
        pred_fast = pred_p50 * multiplier
    if model_sale is not None:
        pred_sale = model_sale.predict_proba(X)[:, 1]
    else:
        pred_sale = [0.5 for _ in rows]

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    payload_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        p10 = max(0.1, float(pred_p10[idx]))
        p50 = max(p10, float(pred_p50[idx]))
        p90 = max(p50, float(pred_p90[idx]))
        fast_sale = max(0.1, float(pred_fast[idx]))
        sale_prob = float(pred_sale[idx])
        support_count = int(row.get("support_count_recent") or 0)
        confidence = min(0.99, max(0.05, 0.25 + min(support_count, 4000) / 8000.0))
        payload_rows.append(
            {
                "prediction_id": str(uuid.uuid4()),
                "run_id": run_id,
                "prediction_as_of_ts": row.get("as_of_ts") or now,
                "league": league,
                "route": route,
                "item_id": row.get("item_id"),
                "identity_key": str(row.get("identity_key") or ""),
                "fair_value_p10": p10,
                "fair_value_p50": p50,
                "fair_value_p90": p90,
                "fast_sale_24h_price": fast_sale,
                "sale_probability_24h": sale_prob,
                "confidence": confidence,
                "support_count_recent": support_count,
                "prediction_source": "ml_v3_train_eval",
                "uncertainty_tier": "medium" if confidence >= 0.45 else "high",
                "fallback_reason": "",
                "prediction_explainer_json": "{}",
                "recorded_at": now,
            }
        )
    body = "\n".join(json.dumps(row, separators=(",", ":")) for row in payload_rows)
    client.execute(
        "INSERT INTO poe_trade.ml_v3_price_predictions FORMAT JSONEachRow\n" + body
    )
    return len(payload_rows)


def record_eval_predictions_for_run(
    client: ClickHouseClient,
    *,
    league: str,
    model_dir: str,
    routes: list[str],
    run_id: str,
    max_rows_per_route: int = EVAL_ROWS_PER_ROUTE_DEFAULT,
) -> int:
    total = 0
    for route in routes:
        bundle = _load_bundle_for_route(model_dir=model_dir, league=league, route=route)
        if bundle is None:
            continue
        rows = _load_eval_rows(
            client,
            league=league,
            route=route,
            max_rows=max_rows_per_route,
        )
        total += _insert_eval_predictions(
            client,
            league=league,
            route=route,
            run_id=run_id,
            rows=rows,
            bundle=bundle,
        )
    return total


def train_route_v3(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    model_dir: str,
    max_rows: int = MAX_ROWS_PER_ROUTE_DEFAULT,
) -> dict[str, Any]:
    rows = _load_training_rows(
        client,
        league=league,
        route=route,
        max_rows=max_rows,
    )
    if not rows:
        return asdict(
            TrainRouteResult(
                league=league,
                route=route,
                row_count=0,
                model_bundle_path="",
                status="no_data",
            )
        )

    feature_rows = [_feature_dict(row) for row in rows]
    vectorizer = DictVectorizer(sparse=True)
    X = vectorizer.fit_transform(feature_rows)
    y_p50 = np.array([float(row.get("target_price_chaos") or 0.0) for row in rows])

    model_p10 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.1,
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    model_p50 = GradientBoostingRegressor(
        loss="absolute_error",
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    model_p90 = GradientBoostingRegressor(
        loss="quantile",
        alpha=0.9,
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    model_p10.fit(X, y_p50)
    model_p50.fit(X, y_p50)
    model_p90.fit(X, y_p50)

    sale_targets = np.array(
        [float(row.get("target_sale_probability_24h") or 0.0) >= 0.5 for row in rows],
        dtype=np.int8,
    )
    unique_classes = np.unique(sale_targets)
    sale_model: LogisticRegression | None = None
    if unique_classes.size >= 2:
        sale_model = LogisticRegression(max_iter=1000, random_state=42)
        sale_model.fit(X, sale_targets)

    fast_sale_targets = np.array(
        [float(row.get("target_fast_sale_24h_price") or 0.0) for row in rows]
    )
    fallback_multiplier = 0.9
    positive_mask = (y_p50 > 0) & (fast_sale_targets > 0)
    if positive_mask.any():
        fallback_multiplier = float(
            np.clip(
                np.median(fast_sale_targets[positive_mask] / y_p50[positive_mask]),
                0.5,
                1.0,
            )
        )
    effective_fast_sale = np.where(
        fast_sale_targets > 0,
        fast_sale_targets,
        np.maximum(0.1, y_p50 * fallback_multiplier),
    )
    model_fast_sale = GradientBoostingRegressor(
        loss="absolute_error",
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    model_fast_sale.fit(X, effective_fast_sale)

    bundle = {
        "vectorizer": vectorizer,
        "models": {
            "p10": model_p10,
            "p50": model_p50,
            "p90": model_p90,
            "fast_sale_24h": model_fast_sale,
            "sale_probability": sale_model,
        },
        "search_config": {
            "max_candidates": 64,
            "stage_support_targets": {"1": 8, "2": 12, "3": 18, "4": 24},
        },
        "route_family_priors": {},
        "fair_value_residual_model": model_p50,
        "fast_sale_residual_model": model_fast_sale,
        "fallback_fast_sale_multiplier": fallback_multiplier,
        "metadata": {
            "league": league,
            "route": route,
            "row_count": len(rows),
            "has_fast_sale_target": bool((fast_sale_targets > 0).any()),
            "feature_schema": {
                "fields": sorted(vectorizer.feature_names_),
                "field_count": len(vectorizer.feature_names_),
            },
        },
    }

    target_dir = Path(model_dir) / "v3" / league / route
    target_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = target_dir / "bundle.joblib"
    joblib.dump(bundle, bundle_path)
    model_version = f"v3-{league.lower()}-{route}"
    _register_route_model(
        client,
        league=league,
        route=route,
        model_version=model_version,
        model_dir=model_dir,
        row_count=len(rows),
    )

    return asdict(
        TrainRouteResult(
            league=league,
            route=route,
            row_count=len(rows),
            model_bundle_path=str(bundle_path),
            status="trained",
        )
    )


def train_all_routes_v3(
    client: ClickHouseClient,
    *,
    league: str,
    model_dir: str,
    max_rows_per_route: int = MAX_ROWS_PER_ROUTE_DEFAULT,
) -> dict[str, Any]:
    rows = _query_rows(
        client,
        " ".join(
            [
                "SELECT route, count() AS rows",
                f"FROM {sql.TRAINING_TABLE}",
                f"WHERE league = {_quote(league)}",
                "GROUP BY route",
                "ORDER BY rows DESC",
                "FORMAT JSONEachRow",
            ]
        ),
    )
    routes = [
        str(row.get("route") or "") for row in rows if str(row.get("route") or "")
    ]
    run_id = f"v3-train-{league.lower()}-{int(datetime.now(UTC).timestamp())}"
    results = [
        train_route_v3(
            client,
            league=league,
            route=route,
            model_dir=model_dir,
            max_rows=max_rows_per_route,
        )
        for route in routes
    ]
    trained_routes = [
        str(row.get("route") or "")
        for row in results
        if str(row.get("status") or "") == "trained" and str(row.get("route") or "")
    ]
    eval_prediction_rows = record_eval_predictions_for_run(
        client,
        league=league,
        model_dir=model_dir,
        routes=trained_routes,
        run_id=run_id,
    )
    return {
        "run_id": run_id,
        "league": league,
        "routes": routes,
        "results": results,
        "trained_count": sum(1 for row in results if row.get("status") == "trained"),
        "eval_prediction_rows": eval_prediction_rows,
    }
