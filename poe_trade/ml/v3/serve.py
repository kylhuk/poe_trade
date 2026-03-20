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
from .sql import TRAINING_TABLE


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _query_rows(client: ClickHouseClient, query: str) -> list[dict[str, Any]]:
    payload = client.execute(query).strip()
    if not payload:
        return []
    return [json.loads(line) for line in payload.splitlines() if line.strip()]


def _route_for_item(parsed: dict[str, Any]) -> str:
    category = str(parsed.get("category") or "other")
    rarity = str(parsed.get("rarity") or "")
    if category == "cluster_jewel":
        return "cluster_jewel_retrieval"
    if category in {"fossil", "scarab", "logbook"}:
        return "fungible_reference"
    if rarity == "Unique" and category in {"ring", "amulet", "belt", "jewel"}:
        return "structured_boosted_other"
    if rarity == "Unique":
        return "structured_boosted"
    if rarity == "Rare":
        return "sparse_retrieval"
    return "fallback_abstain"


def _load_bundle_if_present(
    *, model_dir: str, league: str, route: str
) -> dict[str, Any] | None:
    path = Path(model_dir) / "v3" / league / route / "bundle.joblib"
    if not path.exists():
        return None
    payload = joblib.load(path)
    if not isinstance(payload, dict):
        return None
    return payload


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


def predict_one_v3(
    client: ClickHouseClient,
    *,
    league: str,
    clipboard_text: str,
    model_dir: str = "artifacts/ml",
) -> dict[str, Any]:
    parsed = workflows._parse_clipboard_item(clipboard_text)
    route = _route_for_item(parsed)
    features = build_feature_row(parsed)
    base_type = str(parsed.get("base_type") or "")
    rarity = str(parsed.get("rarity") or "")
    bundle = _load_bundle_if_present(model_dir=model_dir, league=league, route=route)

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
    else:
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
        if sale_model is None:
            sale_prob = 0.5
        else:
            sale_prob = float(sale_model.predict_proba(X)[0][1])
        support = int((bundle.get("metadata") or {}).get("row_count") or 0)
        confidence = max(0.05, min(0.99, 0.2 + min(support, 5000) / 7000.0))
        multiplier = float(bundle.get("fallback_fast_sale_multiplier") or 0.9)
        fast_sale = max(0.1, p50 * multiplier)
        source = "v3_model"

    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    prediction_id = str(uuid.uuid4())
    uncertainty_tier = (
        "low" if confidence >= 0.7 else ("medium" if confidence >= 0.45 else "high")
    )
    fallback_reason = "" if source == "v3_model" else "v3_no_bundle"
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
        "ml_predicted": True,
        "price_recommendation_eligible": confidence >= 0.35,
        "predictedValue": p50,
        "interval": {"p10": p10, "p90": p90},
    }
