from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib

from poe_trade.db import ClickHouseClient
from poe_trade.ml import workflows

from .features import build_feature_row
from . import routes
from . import sql
from . import hybrid_search
from .hybrid_anchor import build_anchor
from .train import apply_residual_cap, _prediction_space_to_price
from .sql import ROLLOUT_STATE_TABLE, TRAINING_TABLE


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _load_bundle_if_present(
    *, model_dir: str, league: str, route: str
) -> dict[str, Any] | None:
    path = Path(model_dir) / "v3" / league / route / "bundle.joblib"
    if not path.exists():
        return None
    try:
        payload = joblib.load(path)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _is_valid_bundle_schema(bundle: dict[str, Any] | None) -> bool:
    if not isinstance(bundle, dict):
        return False
    vectorizer = bundle.get("vectorizer")
    if not callable(getattr(vectorizer, "transform", None)):
        return False
    models = bundle.get("models")
    if not isinstance(models, dict):
        return False
    for key in ("p10", "p50", "p90"):
        model = models.get(key)
        if not callable(getattr(model, "predict", None)):
            return False
    return True


def _median_fallback(
    client: ClickHouseClient,
    *,
    league: str,
    route: str,
    base_type: str,
    rarity: str,
) -> tuple[float, int]:
    try:
        query = " ".join(
            [
                "SELECT quantileTDigest(0.5)(target_price_chaos) AS p50, count() AS rows",
                f"FROM {TRAINING_TABLE}",
                f"WHERE league = {_quote(league)}",
                f"AND route = {_quote(route)}",
                f"AND base_type = {_quote(base_type)}",
                f"AND rarity = {_quote(rarity)}",
                "FORMAT JSONEachRow",
            ]
        )
        rows = _query_rows(client, query)
    except Exception:
        return 1.0, 0
    if not rows:
        return 1.0, 0
    try:
        p50 = float(rows[0].get("p50") or 1.0)
        support = int(rows[0].get("rows") or 0)
    except (TypeError, ValueError):
        return 1.0, 0
    return max(0.1, p50), max(0, support)


def _confidence_from_support_and_interval(
    *, support: int, p10: float, p50: float, p90: float
) -> float:
    support_score = min(max(support, 0), 4000) / 4000.0
    width_ratio = (max(p90, p10) - min(p90, p10)) / max(p50, 0.1)
    tightness_score = max(0.0, 1.0 - min(width_ratio, 1.5) / 1.5)
    confidence = 0.05 + (0.25 * support_score) + (0.2 * tightness_score)
    return max(0.05, min(0.99, confidence))


def _safe_multiplier(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.9


def _latest_fx_rate(client: ClickHouseClient, *, league: str) -> float:
    query = " ".join(
        [
            "SELECT chaos_equivalent AS rate",
            "FROM poe_trade.ml_fx_hour_latest_v2",
            f"WHERE league = {_quote(league)}",
            "AND currency = 'divine'",
            "ORDER BY hour_ts DESC",
            "LIMIT 1",
            "FORMAT JSONEachRow",
        ]
    )
    try:
        rows = _query_rows(client, query)
    except Exception:
        return 1.0
    if not rows:
        return 1.0
    try:
        return max(0.1, float(rows[0].get("rate") or 1.0))
    except (TypeError, ValueError):
        return 1.0


def _coerce_mod_payload(raw: Any) -> dict[str, float]:
    if isinstance(raw, dict):
        payload = raw
    elif isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(payload, dict):
            return {}
    else:
        return {}
    output: dict[str, float] = {}
    for key, value in payload.items():
        try:
            output[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return output


def _ranked_affixes_for_item(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    payload = _coerce_mod_payload(parsed.get("mod_features_json"))
    ranked = sorted(payload.items(), key=lambda item: (-abs(item[1]), item[0]))
    return [
        {
            "affix": affix,
            "importance": max(0.5, abs(value)),
            "support": 1,
            "source": "target_item",
        }
        for affix, value in ranked
    ]


def _bundle_key(strategy_family: str, cohort_key: str) -> str:
    return f"{strategy_family}::{cohort_key}"


def _engine_family_for_strategy(strategy_family: str) -> str:
    normalized = strategy_family.strip().lower()
    if normalized in {"fallback_abstain", "abstain"}:
        return "abstain"
    if "reference" in normalized:
        return "reference"
    if "retrieval" in normalized:
        return "retrieval"
    return "ml"


def _retrieval_strategy_for_target(cohort_key: str) -> str:
    if cohort_key.startswith("cluster_jewel_retrieval|"):
        return "cluster_jewel_retrieval"
    if "|cluster_jewel|" in cohort_key:
        return "cluster_jewel_retrieval"
    return "sparse_retrieval"


def _rewrite_cohort_for_strategy(strategy_family: str, cohort_key: str) -> str:
    if "|" not in cohort_key:
        return strategy_family
    _, suffix = cohort_key.split("|", 1)
    return f"{strategy_family}|{suffix}"


def _is_promoted_row(row: dict[str, Any]) -> bool:
    raw = row.get("promoted")
    if raw is None:
        return True
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"", "0", "false", "f", "no", "off"}:
            return False
        return True
    try:
        return int(raw) != 0
    except (TypeError, ValueError):
        return False


def _normalize_promoted_rollout_rows(
    promoted_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    normalized_rows: list[dict[str, str]] = []
    for row in promoted_rows:
        if not _is_promoted_row(row):
            continue
        strategy_family = str(row.get("strategy_family") or "").strip()
        cohort_key = str(row.get("cohort_key") or "").strip()
        if not strategy_family or not cohort_key:
            continue
        normalized_rows.append(
            {
                "strategy_family": strategy_family,
                "cohort_key": cohort_key,
            }
        )
    normalized_rows.sort(key=lambda row: (row["cohort_key"], row["strategy_family"]))
    return normalized_rows


def _resolve_rollout_bundle_key(
    *,
    strategy_family: str,
    cohort_key: str,
    parent_cohort_key: str,
    promoted_rows: list[dict[str, Any]],
    available_bundle_keys: set[str],
) -> str | None:
    normalized_rows = _normalize_promoted_rollout_rows(promoted_rows)
    promoted_by_cohort: dict[str, list[dict[str, str]]] = {}
    for row in normalized_rows:
        promoted_by_cohort.setdefault(row["cohort_key"], []).append(row)

    def _pick_candidate(
        rows_for_cohort: list[dict[str, str]], *, preferred_strategy_family: str
    ) -> dict[str, str] | None:
        if not rows_for_cohort:
            return None
        if len(rows_for_cohort) == 1:
            return rows_for_cohort[0]
        preferred = [
            row
            for row in rows_for_cohort
            if row["strategy_family"] == preferred_strategy_family
        ]
        if len(preferred) == 1:
            return preferred[0]
        return None

    exact_promoted = _pick_candidate(
        promoted_by_cohort.get(cohort_key, []),
        preferred_strategy_family=strategy_family,
    )
    if exact_promoted is not None:
        exact_key = _bundle_key(
            exact_promoted["strategy_family"], exact_promoted["cohort_key"]
        )
        if exact_key in available_bundle_keys:
            return exact_key

    parent_promoted = _pick_candidate(
        promoted_by_cohort.get(parent_cohort_key, []),
        preferred_strategy_family=strategy_family,
    )
    if parent_promoted is not None:
        parent_key = _bundle_key(
            parent_promoted["strategy_family"], parent_promoted["cohort_key"]
        )
        if parent_key in available_bundle_keys:
            return parent_key

    target_family = _engine_family_for_strategy(strategy_family)
    if target_family == "abstain":
        return None

    if target_family == "reference":
        reference_parent = _rewrite_cohort_for_strategy(
            "fungible_reference", parent_cohort_key
        )
        reference_parent_key = _bundle_key("fungible_reference", reference_parent)
        if reference_parent_key in available_bundle_keys:
            return reference_parent_key
        return None

    retrieval_strategy = _retrieval_strategy_for_target(cohort_key)
    retrieval_parent = _rewrite_cohort_for_strategy(
        retrieval_strategy, parent_cohort_key
    )
    retrieval_parent_key = _bundle_key(retrieval_strategy, retrieval_parent)

    if target_family == "retrieval":
        if retrieval_parent_key in available_bundle_keys:
            return retrieval_parent_key
        return None

    retrieval_same = _rewrite_cohort_for_strategy(retrieval_strategy, cohort_key)
    retrieval_same_promoted = _pick_candidate(
        promoted_by_cohort.get(retrieval_same, []),
        preferred_strategy_family=retrieval_strategy,
    )
    if retrieval_same_promoted is not None:
        retrieval_same_key = _bundle_key(
            retrieval_same_promoted["strategy_family"],
            retrieval_same_promoted["cohort_key"],
        )
        if retrieval_same_key in available_bundle_keys:
            return retrieval_same_key

    if retrieval_parent_key in available_bundle_keys:
        return retrieval_parent_key
    return None


def _load_promoted_rollout_rows(
    client: ClickHouseClient, *, league: str
) -> list[dict[str, Any]]:
    query = " ".join(
        [
            "SELECT strategy_family, cohort_key, promoted",
            f"FROM {ROLLOUT_STATE_TABLE}",
            f"WHERE league = {_quote(league)} AND promoted = 1",
            "ORDER BY strategy_family ASC, cohort_key ASC",
            "FORMAT JSONEachRow",
        ]
    )
    try:
        return _query_rows(client, query)
    except Exception:
        return []


def _select_serving_bundle(
    *,
    bundle: dict[str, Any],
    strategy_family: str,
    cohort_key: str,
    parent_cohort_key: str,
    promoted_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    cohort_bundles = bundle.get("cohort_bundles")
    if not isinstance(cohort_bundles, dict) or not cohort_bundles:
        return bundle
    available_bundle_keys = {
        str(key)
        for key, value in cohort_bundles.items()
        if isinstance(key, str) and isinstance(value, dict)
    }
    selected_key = _resolve_rollout_bundle_key(
        strategy_family=strategy_family,
        cohort_key=cohort_key,
        parent_cohort_key=parent_cohort_key,
        promoted_rows=promoted_rows,
        available_bundle_keys=available_bundle_keys,
    )
    if selected_key is None:
        return bundle
    selected_bundle = cohort_bundles.get(selected_key)
    if not isinstance(selected_bundle, dict):
        return bundle
    return selected_bundle


def predict_one_v3(
    client: ClickHouseClient,
    *,
    league: str,
    clipboard_text: str,
    model_dir: str = "artifacts/ml",
) -> dict[str, Any]:
    parsed = workflows._parse_clipboard_item(clipboard_text)
    route = routes.select_route(parsed)
    cohort_identity = routes.assign_cohort(parsed)
    strategy_family = str(cohort_identity.get("strategy_family") or route)
    cohort_key = str(
        cohort_identity.get("cohort_key")
        or f"{strategy_family}|__legacy_missing_material_state_signature__"
    )
    parent_cohort_key = str(
        cohort_identity.get("parent_cohort_key")
        or f"{strategy_family}|__legacy_missing_material_state_signature__"
    )
    feature_input = {**parsed, **cohort_identity}
    features = build_feature_row(feature_input)
    parsed = {**feature_input, **features}
    base_type = str(parsed.get("base_type") or "")
    rarity = str(parsed.get("rarity") or "")

    retrieval_rows: list[dict[str, Any]] = []
    try:
        retrieval_query = sql.build_retrieval_candidate_query(
            league=league,
            route=route,
            item_state_key=str(parsed.get("item_state_key") or ""),
            limit=2000,
        )
        retrieval_rows = _query_rows(client, retrieval_query)
    except Exception:
        retrieval_rows = []
    search = hybrid_search.run_search(
        parsed_item=parsed,
        candidate_rows=retrieval_rows,
        ranked_affixes=_ranked_affixes_for_item(parsed),
        max_candidates=64,
    )
    anchor = build_anchor(list(search.candidates))

    bundle = _load_bundle_if_present(model_dir=model_dir, league=league, route=route)
    if not _is_valid_bundle_schema(bundle):
        bundle = None
    elif isinstance(bundle, dict):
        promoted_rows = _load_promoted_rollout_rows(client, league=league)
        bundle = _select_serving_bundle(
            bundle=bundle,
            strategy_family=strategy_family,
            cohort_key=cohort_key,
            parent_cohort_key=parent_cohort_key,
            promoted_rows=promoted_rows,
        )
        if not _is_valid_bundle_schema(bundle):
            bundle = None
    p10 = 0.1
    p50 = 0.1
    p90 = 0.1
    sale_prob = 0.5
    support = 0
    confidence = 0.25
    source = "v3_median_fallback"
    fast_sale = 0.1

    if bundle is not None:
        try:
            metadata = bundle.get("metadata") or {}
            prediction_space = str(metadata.get("prediction_space") or "price")
            price_unit = str(metadata.get("price_unit") or "chaos")
            features = dict(features)
            features["support_count_recent"] = int(metadata.get("row_count") or 0)
            vectorizer = bundle["vectorizer"]
            X = vectorizer.transform([features])
            models = bundle["models"]
            raw_p10 = float(models["p10"].predict(X)[0])
            raw_p50 = float(models["p50"].predict(X)[0])
            raw_p90 = float(models["p90"].predict(X)[0])
            p10 = _prediction_space_to_price(raw_p10, prediction_space=prediction_space)
            p50 = _prediction_space_to_price(raw_p50, prediction_space=prediction_space)
            p90 = _prediction_space_to_price(raw_p90, prediction_space=prediction_space)
            p10 = max(0.1, p10)
            p50 = max(p10, p50)
            p90 = max(p50, p90)
            fx_rate = (
                _latest_fx_rate(client, league=league)
                if price_unit == "divine"
                else 1.0
            )
            if price_unit == "divine":
                p10 *= fx_rate
                p50 *= fx_rate
                p90 *= fx_rate
            sale_model = models.get("sale_probability")
            sale_predict_proba = getattr(sale_model, "predict_proba", None)
            sale_predict = getattr(sale_model, "predict", None)
            if callable(sale_predict_proba):
                try:
                    sale_result: Any = sale_predict_proba(X)
                    sale_prob = float(sale_result[0][1])
                except Exception:
                    sale_prob = 0.5
            elif callable(sale_predict):
                try:
                    sale_result = sale_predict(X)
                    sale_prob = float(sale_result[0])
                except Exception:
                    sale_prob = 0.5
            else:
                sale_prob = 0.5
            sale_prob = max(0.0, min(1.0, sale_prob))
            support = int(features.get("support_count_recent") or 0)
            confidence = _confidence_from_support_and_interval(
                support=support,
                p10=p10,
                p50=p50,
                p90=p90,
            )
            multiplier = _safe_multiplier(
                bundle.get("fallback_fast_sale_multiplier") or 0.9
            )
            fast_sale_model = models.get("fast_sale_24h")
            fast_sale_predict = getattr(fast_sale_model, "predict", None)
            if not callable(fast_sale_predict):
                fast_sale = max(0.1, p50 * multiplier)
            else:
                try:
                    fast_sale_result: Any = fast_sale_predict(X)
                    fast_sale = _prediction_space_to_price(
                        float(fast_sale_result[0]), prediction_space=prediction_space
                    )
                except Exception:
                    fast_sale = max(0.1, p50 * multiplier)
            if price_unit == "divine":
                fast_sale *= fx_rate
            fast_sale = max(0.1, fast_sale * 0.95)
            source = "v3_model"

            if search.stage > 0 and anchor.anchor_price is not None:
                fair_residual = p50 - float(anchor.anchor_price)
                fast_residual = fast_sale - float(anchor.anchor_price)
                capped = apply_residual_cap(
                    anchor_price=anchor.anchor_price,
                    confidence=confidence,
                    fair_residual=fair_residual,
                    fast_residual=fast_residual,
                )
                p50 = max(0.1, float(capped["fair_value"]))
                p10 = max(0.1, p50 * 0.85)
                p90 = max(p50, p50 * 1.15)
                fast_sale = max(0.1, float(capped["fast_sale"]))
                source = "v3_hybrid"
        except Exception:
            bundle = None

    if bundle is None:
        p50, support = _median_fallback(
            client,
            league=league,
            route=route,
            base_type=base_type,
            rarity=rarity,
        )
        p10 = max(0.1, p50 * 0.85)
        p90 = max(p50, p50 * 1.15)
        confidence = 0.25 if support < 20 else 0.45
        sale_prob = 0.35 if support < 20 else 0.55
        source = "v3_median_fallback"
        fast_sale = max(0.1, p50 * 0.9 * 0.95)

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prediction_id = str(uuid.uuid4())
    fallback_reason = "" if source in {"v3_model", "v3_hybrid"} else "v3_no_bundle"
    if source != "v3_model":
        confidence = max(0.05, confidence - 0.1)
    uncertainty_tier = (
        "low" if confidence >= 0.7 else ("medium" if confidence >= 0.45 else "high")
    )
    if search.stage == 0:
        confidence = 0.10
        uncertainty_tier = "high"

    estimate_trust = (
        "high" if confidence >= 0.75 else ("normal" if confidence >= 0.35 else "low")
    )
    anchor_price = anchor.anchor_price if anchor.anchor_price is not None else p50
    anchor_low = anchor.anchor_low if anchor.anchor_low is not None else p10
    anchor_high = anchor.anchor_high if anchor.anchor_high is not None else p90

    return {
        "prediction_id": prediction_id,
        "prediction_as_of_ts": now,
        "route": route,
        "strategy_family": strategy_family,
        "cohort_key": cohort_key,
        "parent_cohort_key": parent_cohort_key,
        "price_p10": p10,
        "price_p50": p50,
        "price_p90": p90,
        "fair_value_p10": p10,
        "fair_value_p50": p50,
        "fair_value_p90": p90,
        "fast_sale_24h_price": fast_sale,
        "sale_probability_24h": sale_prob,
        "sale_probability_percent": round(sale_prob * 100, 2),
        "confidence": confidence,
        "confidence_percent": round(confidence * 100, 2),
        "support_count_recent": support,
        "prediction_source": source,
        "engine_version": "ml_v3",
        "uncertainty_tier": uncertainty_tier,
        "fallback_reason": fallback_reason,
        "fallback_depth": int(search.stage),
        "incumbent_flag": 1,
        "estimate_trust": estimate_trust,
        "ml_predicted": True,
        "price_recommendation_eligible": confidence >= 0.35,
        "predictedValue": p50,
        "interval": {"p10": p10, "p90": p90},
        "retrieval_stage": search.stage,
        "retrievalStage": search.stage,
        "retrieval_candidate_count": search.candidate_count,
        "retrievalCandidateCount": search.candidate_count,
        "retrieval_effective_support": search.effective_support,
        "retrieval_effectiveSupport": search.effective_support,
        "retrieval_dropped_affixes": search.dropped_affixes,
        "retrievalDroppedAffixes": search.dropped_affixes,
        "retrieval_degradation_reason": search.degradation_reason,
        "searchDiagnostics": {
            "stage": search.stage,
            "candidateCount": search.candidate_count,
            "effectiveSupport": search.effective_support,
            "droppedAffixes": search.dropped_affixes,
            "degradationReason": search.degradation_reason,
        },
        "comparablesSummary": {
            "anchorPrice": anchor_price,
            "anchorLow": anchor_low,
            "anchorHigh": anchor_high,
        },
    }
