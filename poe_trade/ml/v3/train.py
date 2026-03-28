from __future__ import annotations

import json
import hashlib
from importlib import import_module
from datetime import UTC, datetime
from dataclasses import asdict, dataclass
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict, cast
import uuid

import joblib
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.feature_extraction import DictVectorizer

from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows

from .features import build_feature_row
from .routes import assign_cohort
from . import sql

MAX_ROWS_PER_ROUTE_DEFAULT = 60_000
EVAL_ROWS_PER_ROUTE_DEFAULT = 2_000


class _PredictionBundleCache(TypedDict):
    vectorizer: DictVectorizer
    models: dict[str, Any]
    prediction_space: str
    price_unit: str
    fallback_fast_sale_multiplier: float


class _CohortGroup(TypedDict):
    strategy_family: str
    cohort_key: str
    rows: list[dict[str, Any]]


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


def _forward_split_row_limits(total_rows: int, max_rows: int) -> tuple[int, int]:
    if total_rows <= 0:
        return 1, 1
    if max_rows <= 0:
        return 1, 1
    train_limit = max(1, min(max_rows, int(total_rows * 0.8)))
    eval_limit = max(1, min(max_rows, max(total_rows - train_limit, 1)))
    return train_limit, eval_limit


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
    train_limit, _ = _forward_split_row_limits(total_rows, max_rows)

    query = " ".join(
        [
            "SELECT",
            "as_of_ts,",
            "route,",
            "category,",
            "base_type,",
            "item_name,",
            "item_type_line,",
            "rarity,",
            "ilvl,",
            "stack_size,",
            "corrupted,",
            "fractured,",
            "synthesised,",
            "listing_episode_id,",
            "first_seen,",
            "last_seen,",
            "snapshot_count,",
            "latest_price,",
            "min_price,",
            "support_count_recent,",
            "label_weight,",
            "sale_confidence_flag,",
            "strategy_family,",
            "cohort_key,",
            "material_state_signature,",
            "feature_vector_json,",
            "mod_features_json,",
            "target_price_chaos,",
            "target_fast_sale_24h_price,",
            "target_sale_probability_24h",
            f"FROM {sql.TRAINING_TABLE}",
            f"WHERE league = {_quote(league)} AND route = {_quote(route)}",
            "AND target_price_chaos > 0",
            f"ORDER BY as_of_ts ASC, identity_key ASC",
            f"LIMIT {train_limit}",
            "FORMAT JSONEachRow",
        ]
    )
    return _query_rows(client, query)


def _feature_dict(row: dict[str, Any]) -> dict[str, Any]:
    return build_feature_row(row)


def _select_prediction_bundle(
    bundle: dict[str, Any], *, row: dict[str, Any], route: str
) -> dict[str, Any]:
    cohort_bundles = bundle.get("cohort_bundles")
    if not isinstance(cohort_bundles, dict) or not cohort_bundles:
        return bundle

    cohort_identity = assign_cohort({**row, "route": route})
    strategy_family = str(cohort_identity.get("strategy_family") or route).strip()
    cohort_key = str(cohort_identity.get("cohort_key") or "").strip()
    parent_cohort_key = str(cohort_identity.get("parent_cohort_key") or "").strip()

    for selected_key in (
        f"{strategy_family}::{cohort_key}" if strategy_family and cohort_key else "",
        f"{strategy_family}::{parent_cohort_key}"
        if strategy_family and parent_cohort_key
        else "",
    ):
        selected_bundle = cohort_bundles.get(selected_key)
        if isinstance(selected_bundle, dict):
            return selected_bundle

    return bundle


def _prediction_space_to_price(value: float, *, prediction_space: str) -> float:
    if prediction_space == "log1p_price":
        return max(0.1, float(np.expm1(value)))
    return max(0.1, float(value))


def _fx_chaos_per_divine(row: Mapping[str, Any]) -> float:
    try:
        return max(0.1, float(row.get("fx_chaos_per_divine") or 1.0))
    except (TypeError, ValueError):
        return 1.0


def _row_float(row: Mapping[str, Any], key: str, default: float = 0.0) -> float:
    try:
        value = row.get(key)
        return float(default if value is None else value)
    except (TypeError, ValueError):
        return default


def _cohort_identity_from_row(*, row: dict[str, Any], route: str) -> tuple[str, str]:
    strategy_family = str(row.get("strategy_family") or "").strip() or route
    cohort_key = str(row.get("cohort_key") or "").strip()
    if not cohort_key:
        cohort_key = f"{strategy_family}|__legacy_missing_material_state_signature__"
    return strategy_family, cohort_key


def _derive_cohort_metadata(
    *, strategy_family: str, cohort_key: str, route_compatibility_alias: str
) -> dict[str, str]:
    default_material_state_signature = "__legacy_missing_material_state_signature__"
    parent_cohort_key = f"{strategy_family}|{default_material_state_signature}"
    material_state_signature = default_material_state_signature

    parts = cohort_key.split("|", 2)
    if len(parts) == 3:
        material_state_signature = parts[2] or default_material_state_signature
        parent_cohort_key = f"{strategy_family}|{material_state_signature}"

    return {
        "strategy_family": strategy_family,
        "cohort_key": cohort_key,
        "parent_cohort_key": parent_cohort_key,
        "material_state_signature": material_state_signature,
        "route_compatibility_alias": route_compatibility_alias,
    }


def _train_bundle_for_rows(
    *,
    league: str,
    route: str,
    strategy_family: str,
    cohort_key: str,
    rows: list[dict[str, Any]],
    model_scope: str = "cohort",
) -> dict[str, Any]:
    feature_rows = [_feature_dict(row) for row in rows]
    vectorizer = DictVectorizer(sparse=True)
    X = vectorizer.fit_transform(feature_rows)
    use_divine_targets = all(
        _row_float(row, "target_price_divine") > 0
        and _row_float(row, "target_fast_sale_24h_price_divine") > 0
        for row in rows
    )
    y_p50 = np.array(
        [
            _row_float(
                row,
                "target_price_divine"
                if use_divine_targets and row.get("target_price_divine") is not None
                else "target_price_chaos",
            )
            for row in rows
        ]
    )
    y_p50_log = np.log1p(np.maximum(y_p50, 0.0))
    sample_weights = np.array(
        [max(0.1, float(row.get("label_weight") or 0.25)) for row in rows]
    )

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
    model_p10.fit(X, y_p50_log)
    model_p50.fit(X, y_p50_log)
    model_p90.fit(X, y_p50_log)

    sale_targets = np.array(
        [float(row.get("target_sale_probability_24h") or 0.0) for row in rows]
    )
    sale_model = GradientBoostingRegressor(
        loss="absolute_error",
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    sale_model.fit(X, np.clip(sale_targets, 0.0, 1.0), sample_weight=sample_weights)

    fast_sale_targets = np.array(
        [
            _row_float(
                row,
                "target_fast_sale_24h_price_divine"
                if use_divine_targets
                and row.get("target_fast_sale_24h_price_divine") is not None
                else "target_fast_sale_24h_price",
            )
            for row in rows
        ]
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
    effective_fast_sale_log = np.log1p(np.maximum(effective_fast_sale, 0.0))
    model_fast_sale = GradientBoostingRegressor(
        loss="absolute_error",
        n_estimators=120,
        learning_rate=0.05,
        max_depth=3,
        random_state=42,
    )
    model_fast_sale.fit(X, effective_fast_sale_log, sample_weight=sample_weights)

    identity_metadata = _derive_cohort_metadata(
        strategy_family=strategy_family,
        cohort_key=cohort_key,
        route_compatibility_alias=route,
    )
    return {
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
            **identity_metadata,
            "model_scope": model_scope,
            "row_count": len(rows),
            "has_fast_sale_target": bool((fast_sale_targets > 0).any()),
            "prediction_space": "log1p_price",
            "price_unit": "divine" if use_divine_targets else "chaos",
            "feature_schema": {
                "fields": sorted(vectorizer.feature_names_),
                "field_count": len(vectorizer.feature_names_),
                "fingerprint": hashlib.sha256(
                    json.dumps(
                        sorted(vectorizer.feature_names_), separators=(",", ":")
                    ).encode("utf-8")
                ).hexdigest(),
            },
        },
    }


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
    train_limit, eval_limit = _forward_split_row_limits(total_rows, max_rows)
    query = " ".join(
        [
            "SELECT as_of_ts, item_id, identity_key, listing_episode_id, first_seen, last_seen, snapshot_count, latest_price, min_price, latest_price_divine, min_price_divine, fx_hour, fx_source, fx_chaos_per_divine, route, category, base_type,",
            "item_name, item_type_line, rarity, ilvl, stack_size, corrupted, fractured, synthesised,",
            "support_count_recent, sale_confidence_flag, feature_vector_json, mod_features_json",
            f"FROM {sql.TRAINING_TABLE}",
            f"WHERE league = {_quote(league)} AND route = {_quote(route)}",
            "AND target_price_chaos > 0",
            f"ORDER BY as_of_ts ASC, identity_key ASC",
            f"LIMIT {eval_limit} OFFSET {train_limit}",
            "FORMAT JSONEachRow",
        ]
    )
    return _query_rows(client, query)


def _insert_eval_predictions(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    model_version: str,
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

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    payload_rows: list[dict[str, Any]] = []
    bundle_cache: dict[int, _PredictionBundleCache] = {}
    for row in rows:
        cohort_identity = assign_cohort({**row, "route": route})
        selected_bundle = _select_prediction_bundle(
            bundle, row={**row, **cohort_identity}, route=route
        )
        selected_bundle_id = id(selected_bundle)
        cached_bundle = bundle_cache.get(selected_bundle_id)
        if cached_bundle is None:
            selected_vectorizer = cast(
                DictVectorizer | None, selected_bundle.get("vectorizer")
            )
            selected_models = cast(dict[str, Any], selected_bundle.get("models") or {})
            if selected_vectorizer is None or not isinstance(selected_models, dict):
                selected_bundle = bundle
                selected_bundle_id = id(bundle)
                cached_bundle = bundle_cache.get(selected_bundle_id)
                if cached_bundle is None:
                    selected_metadata = bundle.get("metadata") or {}
                    cached_bundle = cast(
                        _PredictionBundleCache,
                        cast(
                            object,
                            {
                                "vectorizer": vectorizer,
                                "models": models,
                                "prediction_space": str(
                                    selected_metadata.get("prediction_space") or "price"
                                ),
                                "price_unit": str(
                                    selected_metadata.get("price_unit") or "chaos"
                                ),
                                "fallback_fast_sale_multiplier": float(
                                    bundle.get("fallback_fast_sale_multiplier") or 0.9
                                ),
                            },
                        ),
                    )
                    bundle_cache[selected_bundle_id] = cached_bundle
                selected_vectorizer = cached_bundle["vectorizer"]
                selected_models = cached_bundle["models"]
            else:
                selected_metadata = selected_bundle.get("metadata") or {}
                selected_prediction_space = str(
                    selected_metadata.get("prediction_space") or "price"
                )
                cached_bundle = cast(
                    _PredictionBundleCache,
                    cast(
                        object,
                        {
                            "vectorizer": selected_vectorizer,
                            "models": selected_models,
                            "prediction_space": selected_prediction_space,
                            "price_unit": str(
                                selected_metadata.get("price_unit") or "chaos"
                            ),
                            "fallback_fast_sale_multiplier": float(
                                selected_bundle.get("fallback_fast_sale_multiplier")
                                or 0.9
                            ),
                        },
                    ),
                )
                bundle_cache[selected_bundle_id] = cached_bundle

        feature_input = {**row, **cohort_identity}
        feature_rows = [_feature_dict(feature_input)]
        X = cached_bundle["vectorizer"].transform(feature_rows)
        selected_models = cast(dict[str, Any], cached_bundle["models"])
        pred_p10 = selected_models["p10"].predict(X)
        pred_p50 = selected_models["p50"].predict(X)
        pred_p90 = selected_models["p90"].predict(X)
        if selected_models.get("fast_sale_24h") is not None:
            pred_fast = selected_models["fast_sale_24h"].predict(X)
        else:
            pred_fast = pred_p50 * cached_bundle["fallback_fast_sale_multiplier"] * 0.95
        sale_model = selected_models.get("sale_probability")
        sale_predict_proba = cast(Any, getattr(sale_model, "predict_proba", None))
        sale_predict = cast(Any, getattr(sale_model, "predict", None))
        if callable(sale_predict_proba):
            try:
                sale_probability_values = cast(Any, sale_predict_proba(X))
                pred_sale = cast(Any, sale_probability_values[:, 1])
            except Exception:
                pred_sale = [0.5]
        elif callable(sale_predict):
            try:
                pred_sale = cast(Any, sale_predict(X))
            except Exception:
                pred_sale = [0.5]
        else:
            pred_sale = [0.5]

        p10 = _prediction_space_to_price(
            float(pred_p10[0]),
            prediction_space=cast(str, cached_bundle["prediction_space"]),
        )
        p50 = max(
            p10,
            _prediction_space_to_price(
                float(pred_p50[0]),
                prediction_space=cast(str, cached_bundle["prediction_space"]),
            ),
        )
        p90 = max(
            p50,
            _prediction_space_to_price(
                float(pred_p90[0]),
                prediction_space=cast(str, cached_bundle["prediction_space"]),
            ),
        )
        fast_sale = _prediction_space_to_price(
            float(pred_fast[0]),
            prediction_space=cast(str, cached_bundle["prediction_space"]),
        )
        fast_sale = max(0.1, fast_sale * 0.95)
        if cached_bundle["price_unit"] == "divine":
            fx_rate = _fx_chaos_per_divine(row)
            p10 *= fx_rate
            p50 *= fx_rate
            p90 *= fx_rate
            fast_sale *= fx_rate
        sale_prob = max(0.0, min(1.0, float(cast(Any, pred_sale)[0])))
        support_count = int(row.get("support_count_recent") or 0)
        support_score = min(max(support_count, 0), 4000) / 4000.0
        width_ratio = (max(p90, p10) - min(p90, p10)) / max(p50, 0.1)
        tightness_score = max(0.0, 1.0 - min(width_ratio, 1.5) / 1.5)
        confidence = min(
            0.99,
            max(0.05, 0.05 + (0.25 * support_score) + (0.2 * tightness_score)),
        )
        payload_rows.append(
            {
                "prediction_id": str(uuid.uuid4()),
                "run_id": run_id,
                "engine_version": model_version,
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
        metadata = bundle.get("metadata") if isinstance(bundle, dict) else None
        model_version = str(
            (metadata or {}).get("model_version") or f"v3-{league.lower()}-{route}"
        )
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
            model_version=model_version,
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

    grouped_rows: dict[str, _CohortGroup] = {}
    for row in rows:
        strategy_family, cohort_key = _cohort_identity_from_row(row=row, route=route)
        cohort_bundle_key = f"{strategy_family}::{cohort_key}"
        entry = cast(_CohortGroup | None, grouped_rows.get(cohort_bundle_key))
        if entry is None:
            entry = cast(
                _CohortGroup,
                cast(
                    object,
                    {
                        "strategy_family": strategy_family,
                        "cohort_key": cohort_key,
                        "rows": [],
                    },
                ),
            )
            grouped_rows[cohort_bundle_key] = entry
        entry["rows"].append(row)

    ordered_group_keys = list(grouped_rows)
    bundle = _train_bundle_for_rows(
        league=league,
        route=route,
        strategy_family="__route_wide__",
        cohort_key="__route_wide__",
        rows=rows,
        model_scope="route_wide",
    )
    if len(grouped_rows) == 1:
        only_key = ordered_group_keys[0]
        only_group = grouped_rows[only_key]
        cohort_bundle = dict(bundle)
        cohort_bundle_metadata = dict((bundle.get("metadata") or {}))
        cohort_bundle_identity = _derive_cohort_metadata(
            strategy_family=str(only_group["strategy_family"]),
            cohort_key=str(only_group["cohort_key"]),
            route_compatibility_alias=route,
        )
        cohort_bundle_metadata.update(cohort_bundle_identity)
        cohort_bundle_metadata["model_scope"] = "cohort"
        cohort_bundle["metadata"] = cohort_bundle_metadata
        bundle["cohort_bundles"] = {only_key: cohort_bundle}
    else:
        bundle["cohort_bundles"] = {
            cohort_bundle_key: _train_bundle_for_rows(
                league=league,
                route=route,
                strategy_family=str(group["strategy_family"]),
                cohort_key=str(group["cohort_key"]),
                rows=list(group["rows"]),
                model_scope="cohort",
            )
            for cohort_bundle_key, group in grouped_rows.items()
        }
    metadata = bundle.get("metadata")
    if isinstance(metadata, dict):
        metadata["cohort_count"] = len(grouped_rows)
        metadata["cohort_bundle_keys"] = ordered_group_keys
        metadata["model_version"] = f"v3-{league.lower()}"

    cohort_bundles = bundle.get("cohort_bundles")
    if isinstance(cohort_bundles, dict):
        for cohort_bundle in cohort_bundles.values():
            if not isinstance(cohort_bundle, dict):
                continue
            child_metadata = cohort_bundle.get("metadata")
            if isinstance(child_metadata, dict):
                child_metadata["model_version"] = f"v3-{league.lower()}"

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
    workflows.audit_ring_parser_invariants(client, league=league)
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


def run_pricing_benchmark(
    rows: list[dict[str, Any]],
    *,
    split_kind: str = "forward",
) -> dict[str, Any]:
    benchmark_module = cast(Any, import_module("poe_trade.ml.v3.benchmark"))
    _run_pricing_benchmark = benchmark_module.run_pricing_benchmark

    return _run_pricing_benchmark(rows, split_kind=split_kind)
