from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..etl.models import ListingCanonical


@dataclass(frozen=True)
class StashPriceSuggestion:
    snapshot_id: str
    item_uid: str
    league: str
    est_price_chaos: float
    list_price_chaos: float
    confidence: float
    reason_codes: tuple[str, ...]
    details: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_row(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "item_uid": self.item_uid,
            "league": self.league,
            "est_price_chaos": self.est_price_chaos,
            "list_price_chaos": self.list_price_chaos,
            "confidence": self.confidence,
            "reason_codes": list(self.reason_codes),
            "details": self.details,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class StashPricer:
    @staticmethod
    def estimate_confidence(est_price: float, list_price: float) -> float:
        if est_price <= 0:
            return 0.0
        diff = max(est_price - list_price, 0.0)
        ratio = diff / est_price
        return round(min(1.0, ratio), 3)

    @staticmethod
    def suggest_prices(
        snapshot_id: str,
        listings: Sequence[ListingCanonical],
        stats: Mapping[str, float],
        min_chaos: float = 10.0,
    ) -> list[StashPriceSuggestion]:
        est_price = stats.get("p50", 0.0)
        suggestions: list[StashPriceSuggestion] = []
        sorted_listings = sorted(listings, key=lambda listing: (listing.league, listing.item_uid, listing.listing_uid))
        for listing in sorted_listings:
            list_price = listing.price_chaos if listing.price_chaos > 0 else listing.price_amount
            if list_price < min_chaos:
                continue
            reason_codes = []
            if list_price < est_price:
                reason_codes.append("below_estimate")
            else:
                reason_codes.append("at_or_above_estimate")
            confidence = StashPricer.estimate_confidence(est_price, list_price)
            if confidence >= 0.5:
                reason_codes.append("high_confidence")
            details = f"est={est_price:.2f}, list={list_price:.2f}, gap={est_price - list_price:.2f}"
            suggestions.append(
                StashPriceSuggestion(
                    snapshot_id=snapshot_id,
                    item_uid=listing.item_uid,
                    league=listing.league,
                    est_price_chaos=est_price,
                    list_price_chaos=list_price,
                    confidence=confidence,
                    reason_codes=tuple(reason_codes),
                    details=details,
                )
            )
        return suggestions
