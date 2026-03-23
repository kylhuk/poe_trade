from __future__ import annotations

from typing import Any


def build_hybrid_response(
    *,
    fair_value: dict[str, float],
    fast_sale_24h_price: float,
    sale_probability_24h: float,
    confidence: float,
    estimate_trust: str,
    search: dict[str, Any],
    comparables: dict[str, Any],
) -> dict[str, Any]:
    stage = int(search.get("stage") or 0)
    payload = {
        "fairValue": {
            "p10": float(fair_value.get("p10") or 0.0),
            "p50": float(fair_value.get("p50") or 0.0),
            "p90": float(fair_value.get("p90") or 0.0),
        },
        "fastSale24hPrice": float(fast_sale_24h_price),
        "saleProbability24h": float(sale_probability_24h),
        "confidence": float(confidence),
        "estimateTrust": str(estimate_trust),
        "searchDiagnostics": {
            "stage": stage,
            "candidateCount": int(search.get("candidate_count") or 0),
            "effectiveSupport": int(search.get("effective_support") or 0),
            "droppedAffixes": list(search.get("dropped_affixes") or []),
            "degradationReason": search.get("degradation_reason"),
        },
        "comparablesSummary": {
            "anchorPrice": comparables.get("anchor_price"),
            "anchorLow": comparables.get("anchor_low"),
            "anchorHigh": comparables.get("anchor_high"),
        },
        "valueDrivers": {
            "positive": ["affix_overlap"] if stage > 0 else [],
            "negative": [] if stage > 0 else ["no_relevant_comparables"],
        },
        "scenarioPrices": {
            "weakerRolls": [] if stage == 0 else [float(fair_value.get("p10") or 0.0)],
            "strongerRolls": []
            if stage == 0
            else [float(fair_value.get("p90") or 0.0)],
        },
    }
    return payload
