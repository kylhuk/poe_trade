from __future__ import annotations

import math
import json
from dataclasses import dataclass, field
from datetime import datetime
from statistics import pstdev
from typing import Iterable, Mapping, Sequence


def percentile(values: Sequence[float], cutoff: float) -> float:
    if not values:
        return 0.0
    idx = min(len(values) - 1, max(0, math.ceil(cutoff / 100 * len(values)) - 1))
    return values[idx]


def compute_price_stats(prices: Iterable[float]) -> dict[str, float]:
    buffer = [float(value) for value in prices]
    normalized = sorted(buffer)
    if not normalized:
        return {
            "p10": 0.0,
            "p25": 0.0,
            "p50": 0.0,
            "p75": 0.0,
            "p90": 0.0,
            "spread": 0.0,
            "volatility": 0.0,
            "listing_count": 0,
            "liquidity_score": 0.0,
        }
    p10 = percentile(normalized, 10)
    p25 = percentile(normalized, 25)
    p50 = percentile(normalized, 50)
    p75 = percentile(normalized, 75)
    p90 = percentile(normalized, 90)
    spread = normalized[-1] - normalized[0]
    volatility = pstdev(normalized) if len(normalized) > 1 else 0.0
    listing_count = len(normalized)
    liquidity_score = float(listing_count)
    return {
        "p10": p10,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "p90": p90,
        "spread": spread,
        "volatility": volatility,
        "listing_count": listing_count,
        "liquidity_score": liquidity_score,
    }


@dataclass(frozen=True)
class PriceStatsRow:
    league: str
    fp_loose: str
    time_bucket: datetime
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float
    listing_count: int
    spread: float
    volatility: float
    liquidity_score: float
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_prices(
        cls,
        league: str,
        fp_loose: str,
        time_bucket: datetime,
        prices: Iterable[float],
        metadata: Mapping[str, object] | None = None,
    ) -> "PriceStatsRow":
        stats = compute_price_stats(prices)
        return cls(
            league=league,
            fp_loose=fp_loose,
            time_bucket=time_bucket,
            p10=stats["p10"],
            p25=stats["p25"],
            p50=stats["p50"],
            p75=stats["p75"],
            p90=stats["p90"],
            listing_count=int(stats["listing_count"]),
            spread=stats["spread"],
            volatility=stats["volatility"],
            liquidity_score=stats["liquidity_score"],
            metadata=metadata or {},
        )

    def to_row(self) -> dict[str, object]:
        return {
            "league": self.league,
            "fp_loose": self.fp_loose,
            "time_bucket": self.time_bucket,
            "median_price": self.p50,
            "p10": self.p10,
            "p25": self.p25,
            "p50": self.p50,
            "p75": self.p75,
            "p90": self.p90,
            "listing_count": self.listing_count,
            "spread": self.spread,
            "volatility": self.volatility,
            "liquidity_score": self.liquidity_score,
            "metadata": json.dumps(
                dict(self.metadata), sort_keys=True, separators=(",", ":")
            ),
        }
