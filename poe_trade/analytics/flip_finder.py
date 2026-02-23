from __future__ import annotations

import json

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from ..etl.fingerprints import fp_exact
from ..etl.models import ListingCanonical


@dataclass(frozen=True)
class FlipOpportunity:
    detected_at: datetime
    league: str
    query_key: str
    buy_max: float
    sell_min: float
    expected_profit: float
    liquidity_score: float
    expiry_ts: datetime
    metadata: Mapping[str, object]

    def to_row(self) -> dict[str, object]:
        return {
            "detected_at": self.detected_at,
            "league": self.league,
            "query_key": self.query_key,
            "buy_max": self.buy_max,
            "sell_min": self.sell_min,
            "expected_profit": self.expected_profit,
            "liquidity_score": self.liquidity_score,
            "expiry_ts": self.expiry_ts,
            "metadata": json.dumps(dict(self.metadata), separators=(",", ":"), sort_keys=True),
        }


def find_flip_opportunities(
    listings: Sequence[ListingCanonical],
    stats: Mapping[str, float],
    threshold_pct: float = 0.9,
    expiry_hours: int = 2,
    price_overrides: Mapping[str, float] | None = None,
    reference_ts: datetime | None = None,
) -> list[FlipOpportunity]:
    detected: list[FlipOpportunity] = []
    seen: set[str] = set()
    now = reference_ts or datetime.now(timezone.utc)
    expiry_cutoff = now - timedelta(hours=expiry_hours)
    overrides = price_overrides or {}
    price_cutoff = stats.get("p25", 0.0) * threshold_pct
    selling_floor = stats.get("p75", stats.get("p50", 0.0))
    liquidity_score = float(stats.get("liquidity_score", 1.0))
    sorted_listings = sorted(listings, key=lambda listing: (listing.league, listing.listing_uid))

    for listing in sorted_listings:
        if listing.last_seen_at < expiry_cutoff:
            continue
        fingerprint = fp_exact({
            "listing_uid": listing.listing_uid,
            "fp_loose": listing.fp_loose,
        })
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        price = overrides.get(listing.listing_uid, listing.price_chaos or listing.price_amount)
        if price <= 0:
            continue
        if price > price_cutoff:
            continue
        detected_at = now
        sell_min = max(selling_floor, stats.get("p50", price))
        expected_profit = max(0.0, sell_min - price)
        expiry_ts = detected_at + timedelta(hours=expiry_hours)
        metadata = {
            "listing_uid": listing.listing_uid,
            "fp_loose": listing.fp_loose,
            "seller_id": listing.seller_id,
        }
        detected.append(
            FlipOpportunity(
                detected_at=detected_at,
                league=listing.league,
                query_key=fingerprint,
                buy_max=price,
                sell_min=sell_min,
                expected_profit=expected_profit,
                liquidity_score=liquidity_score,
                expiry_ts=expiry_ts,
                metadata=metadata,
            )
        )
    return detected
