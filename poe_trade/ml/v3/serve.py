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
from .train import apply_residual_cap
from .sql import TRAINING_TABLE


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
    if not rows:
        return 1.0, 0
    p50 = float(rows[0].get("p50") or 1.0)
    support = int(rows[0].get("rows") or 0)
    return max(0.1, p50), max(0, support)


def _confidence_from_support_and_interval(
    *, support: int, p10: float, p50: float, p90: float
) -> float:
    support_score = min(max(support, 0), 4000) / 4000.0
    width_ratio = (max(p90, p10) - min(p90, p10)) / max(p50, 0.1)
    tightness_score = max(0.0, 1.0 - min(width_ratio, 1.5) / 1.5)
    confidence = 0.15 + (0.5 * support_score) + (0.35 * tightness_score)
    return max(0.05, min(0.99, confidence))


def _safe_multiplier(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.9


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


def predict_one_v3(
    client: ClickHouseClient,
    *,
    league: str,
    clipboard_text: str,
    model_dir: str = "artifacts/ml",
) -> dict[str, Any]:
    parsed = workflows._parse_clipboard_item(clipboard_text)
    route = routes.select_route(parsed)
    features = build_feature_row(parsed)
    parsed = {**parsed, **features}
    base_type = str(parsed.get("base_type") or "")
    rarity = str(parsed.get("rarity") or "")

    retrieval_rows = _query_rows(
        client,
        sql.build_retrieval_candidate_query(
            league=league,
            route=route,
            item_state_key=str(parsed.get("item_state_key") or ""),
            limit=2000,
        ),
    )
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
            vectorizer = bundle["vectorizer"]
            X = vectorizer.transform([features])
            models = bundle["models"]
            p10 = float(models["p10"].predict(X)[0])
            p50 = float(models["p50"].predict(X)[0])
            p90 = float(models["p90"].predict(X)[0])
            p10 = max(0.1, p10)
            p50 = max(p10, p50)
            p90 = max(p50, p90)
            sale_model = models.get("sale_probability")
            sale_predict_proba = getattr(sale_model, "predict_proba", None)
            if not callable(sale_predict_proba):
                sale_prob = 0.5
            else:
                try:
                    sale_result: Any = sale_predict_proba(X)
                    sale_prob = float(sale_result[0][1])
                except Exception:
                    sale_prob = 0.5
            support = int((bundle.get("metadata") or {}).get("row_count") or 0)
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
                    fast_sale = max(0.1, float(fast_sale_result[0]))
                except Exception:
                    fast_sale = max(0.1, p50 * multiplier)
            source = "v3_model"

            if search.stage > 0 and anchor.anchor_price is not None:
                fair_residual_model = bundle.get("fair_value_residual_model")
                fast_residual_model = bundle.get("fast_sale_residual_model")
                fair_residual_predict = getattr(fair_residual_model, "predict", None)
                fast_residual_predict = getattr(fast_residual_model, "predict", None)
                fair_residual = 0.0
                fast_residual = 0.0
                if callable(fair_residual_predict):
                    try:
                        fair_residual = float(fair_residual_predict(X)[0])
                    except Exception:
                        fair_residual = 0.0
                if callable(fast_residual_predict):
                    try:
                        fast_residual = float(fast_residual_predict(X)[0])
                    except Exception:
                        fast_residual = 0.0
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
        fast_sale = max(0.1, p50 * 0.9)

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
        "uncertainty_tier": uncertainty_tier,
        "fallback_reason": fallback_reason,
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
