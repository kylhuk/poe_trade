from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AnchorResult:
    anchor_price: float | None
    anchor_low: float | None
    anchor_high: float | None
    candidate_count: int
    effective_support: int


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _weighted_quantile(
    values: list[float], weights: list[float], q: float
) -> float | None:
    if not values or not weights or len(values) != len(weights):
        return None
    pairs = sorted(zip(values, weights, strict=True), key=lambda pair: pair[0])
    total_weight = sum(weight for _, weight in pairs)
    if total_weight <= 0:
        return None
    target = total_weight * q
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= target:
            return value
    return pairs[-1][0]


def build_anchor(candidates: list[dict[str, Any]]) -> AnchorResult:
    prices: list[float] = []
    weights: list[float] = []
    for row in candidates:
        price = _to_float(row.get("price", row.get("candidate_price_chaos")))
        score = _to_float(row.get("score", row.get("distance_score")))
        if price is None or price <= 0:
            continue
        if score is None:
            score = 0.0
        if score <= 0:
            continue
        prices.append(price)
        weights.append(score)

    return AnchorResult(
        anchor_price=_weighted_quantile(prices, weights, 0.5),
        anchor_low=_weighted_quantile(prices, weights, 0.1),
        anchor_high=_weighted_quantile(prices, weights, 0.9),
        candidate_count=len(candidates),
        effective_support=len(prices),
    )
