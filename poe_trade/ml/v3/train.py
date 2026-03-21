from __future__ import annotations

import json
from datetime import UTC, datetime
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression

from poe_trade.db import ClickHouseClient

from . import sql

MAX_ROWS_PER_ROUTE_DEFAULT = 60_000


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
    y_p10 = np.array([max(0.1, value * 0.85) for value in y_p50])
    y_p90 = np.array([max(0.1, value * 1.15) for value in y_p50])

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
    model_p10.fit(X, y_p10)
    model_p50.fit(X, y_p50)
    model_p90.fit(X, y_p90)

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

    bundle = {
        "vectorizer": vectorizer,
        "models": {
            "p10": model_p10,
            "p50": model_p50,
            "p90": model_p90,
            "sale_probability": sale_model,
        },
        "fallback_fast_sale_multiplier": fallback_multiplier,
        "metadata": {
            "league": league,
            "route": route,
            "row_count": len(rows),
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
    return {
        "league": league,
        "routes": routes,
        "results": results,
        "trained_count": sum(1 for row in results if row.get("status") == "trained"),
    }
