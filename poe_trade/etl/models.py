from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


@dataclass(frozen=True)
class ItemCanonical:
    item_uid: str
    source: str
    captured_at: datetime
    league: str
    base_type: str
    rarity: str
    ilvl: int
    corrupted: bool
    quality: int
    sockets: int
    links: int
    influences: Sequence[str]
    modifier_ids: Sequence[str]
    modifier_tiers: Sequence[int]
    flags: Sequence[str]
    fp_exact: str
    fp_loose: str
    payload_json: str


@dataclass(frozen=True)
class ListingCanonical:
    listing_uid: str
    item_uid: str
    listed_at: datetime
    league: str
    price_amount: float
    price_currency: str
    price_chaos: float
    seller_id: str
    seller_meta: str
    last_seen_at: datetime
    fp_loose: str
    payload_json: str


@dataclass(frozen=True)
class CurrencySnapshot:
    currency: str
    chaos_value: float
    timestamp: datetime

    def value_in_chaos(self, amount: float) -> float:
        return amount * self.chaos_value
